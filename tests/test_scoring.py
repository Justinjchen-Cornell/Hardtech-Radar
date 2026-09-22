# -*- coding: utf-8 -*-
"""评分引擎单元测试 v0.2。运行：python -m unittest discover -s tests -v"""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import scoring, fetch_news, weekly_digest  # noqa: E402

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>test</title>
<item><title>西部超导签署聚变磁体大单 - 上海证券报</title>
<link>https://example.com/a</link><pubDate>Mon, 21 Sep 2026 08:00:00 +0800</pubDate>
<source>上海证券报</source></item>
<item><title>no-date item</title><link>https://example.com/b</link></item>
<item><title>broken</title></item>
</channel></rss>""".encode("utf-8")


def fake_company(**kw):
    base = {"name": "测试公司", "market": "A股", "ticker": "000000", "industry": "可控核聚变",
            "segment": "超导材料", "role": "卖铲人", "key_data": "测试数据", "note": "", "as_of": "2026-09"}
    base.update(kw)
    return base


class ScoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = scoring.load_config()
        cls.companies = scoring.load_companies()
        cls.milestones = scoring.load_milestones()
        cls.scored = scoring.score_all(cls.companies, cls.cfg, scoring.load_events(), cls.milestones)
        cls.by_name = {c["name"]: c for c in cls.scored}

    def test_every_company_scored_in_range(self):
        self.assertEqual(len(self.scored), len(self.companies))
        for c in self.scored:
            self.assertTrue(0 <= c["score"] <= 100, c["name"])
            for d, v in c["dimensions"].items():
                self.assertTrue(0 <= v <= 100, (c["name"], d))

    def test_all_companies_have_as_of(self):
        for c in self.companies:
            self.assertTrue((c.get("as_of") or "").strip(), c["name"])

    def test_scoring_is_deterministic(self):
        again = scoring.score_all(self.companies, self.cfg, scoring.load_events(), self.milestones)
        self.assertEqual([(c["name"], c["score"]) for c in self.scored],
                         [(c["name"], c["score"]) for c in again])

    def test_works_without_events_file(self):
        """断网/无事件文件时优雅降级：仍能完成评分。"""
        empty = scoring.index_events([])
        scored = scoring.score_all(self.companies[:10], self.cfg, empty, self.milestones)
        self.assertEqual(len(scored), 10)

    def test_shovel_detected(self):
        self.assertEqual(self.by_name["西部超导"]["class"], "shovel")

    def test_option_detected(self):
        self.assertEqual(self.by_name["Commonwealth Fusion Systems (CFS)"]["class"], "option")

    def test_shovel_certainty_beats_option(self):
        shovels = [c["dimensions"]["certainty"] for c in self.scored if c["class"] == "shovel"]
        options = [c["dimensions"]["certainty"] for c in self.scored if c["class"] == "option"]
        self.assertGreater(min(shovels), max(options))

    def test_listed_liquidity_beats_unlisted(self):
        listed = [c["dimensions"]["liquidity"] for c in self.scored if c["market"] in ("A股", "港股", "美股")]
        unlisted = [c["dimensions"]["liquidity"] for c in self.scored if c["market"].startswith("未上市")]
        self.assertGreater(min(listed), max(unlisted))

    def test_events_raise_catalyst(self):
        """同一公司：有近30天新闻事件者，事件热度分与总分更高（事件驱动核心验证）。"""
        cfg = self.cfg
        today = date(2026, 9, 22)
        events = scoring.index_events([
            {"type": "company", "target": "甲公司", "title": "t1", "url": "u", "published": "2026-09-20"},
            {"type": "company", "target": "甲公司", "title": "t2", "url": "u", "published": "2026-09-15"},
        ])
        a = scoring.score_company(fake_company(name="甲公司"), cfg, events, self.milestones, today)
        b = scoring.score_company(fake_company(name="乙公司"), cfg, events, self.milestones, today)
        self.assertGreater(a["dimensions"]["catalyst"], b["dimensions"]["catalyst"])
        self.assertGreater(a["score"], b["score"])

    def test_old_events_ignored(self):
        """超出回看窗口的旧事件不计入。"""
        rules = self.cfg["event_rules"]
        events = scoring.index_events([
            {"type": "company", "target": "甲公司", "title": "old", "url": "u", "published": "2025-01-01"},
        ])
        ev = scoring.filter_recent(events["company"]["甲公司"], rules["event_lookback_days"], date(2026, 9, 22))
        self.assertEqual(len(ev), 0)

    def test_milestone_status_hits_window(self):
        """人工标记 slipped/missed 的里程碑会拉低对应行业的窗口分。"""
        today = date(2026, 9, 22)
        base = scoring.score_company(fake_company(), self.cfg, None, self.milestones, today)
        slipped = [dict(m, status="slipped") for m in self.milestones if m["sector"] == "可控核聚变"] + \
                  [m for m in self.milestones if m["sector"] != "可控核聚变"]
        after = scoring.score_company(fake_company(), self.cfg, None, slipped, today)
        self.assertGreater(base["dimensions"]["window"], after["dimensions"]["window"])
        self.assertGreater(base["score"], after["score"])

    def test_milestone_proximity_raises_catalyst(self):
        """临近里程碑给事件热度加成。"""
        near = [{"date": "2026-10-15", "sector": "可控核聚变", "event": "x", "status": "on_track"}]
        far = [{"date": "2035-12-31", "sector": "可控核聚变", "event": "x", "status": "on_track"}]
        a = scoring.score_company(fake_company(), self.cfg, scoring.index_events([]), near, date(2026, 9, 22))
        b = scoring.score_company(fake_company(), self.cfg, scoring.index_events([]), far, date(2026, 9, 22))
        self.assertGreater(a["dimensions"]["catalyst"], b["dimensions"]["catalyst"])

    def test_tier_labels_assigned(self):
        for c in self.scored:
            self.assertIn(c["tier"], ["核心观察", "重点观察", "一般跟踪", "背景资料"])

    def test_milestones_sorted_with_countdown(self):
        self.assertGreaterEqual(len(self.milestones), 5)
        dates = [m["date"] for m in self.milestones]
        self.assertEqual(dates, sorted(dates))
        view = scoring.milestone_view(self.milestones, date(2026, 9, 22))
        sparc = next(m for m in view if "SPARC" in m["event"] and m["date"] == "2026-12-31")
        self.assertGreater(sparc["days_left"], 0)

    def test_milestone_status_view(self):
        slipped = [dict(self.milestones[0], status="slipped")]
        view = scoring.milestone_view(slipped, date(2026, 9, 22))
        self.assertEqual(view[0]["status_view"], "延期")
        self.assertTrue(view[0]["alert"])

    def test_compute_diff(self):
        current = [{"name": "A", "score": 60.0, "industry": "半导体"},
                   {"name": "B", "score": 50.0, "industry": "半导体"},
                   {"name": "C", "score": 40.0, "industry": "半导体"}]
        previous = {"scores": {"A": 55.0, "B": 53.0, "C": 40.0}}
        diff = scoring.compute_diff(current, previous)
        self.assertEqual(diff["deltas"]["A"], 5.0)
        self.assertEqual(diff["movers_up"][0]["name"], "A")
        self.assertEqual(diff["movers_down"][0]["name"], "B")
        self.assertNotIn("C", diff["deltas"])

    def test_parse_rss(self):
        items = fetch_news.parse_rss_bytes(SAMPLE_RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["published"], "2026-09-21")
        self.assertEqual(items[0]["source"], "上海证券报")
        self.assertIsNone(items[1]["published"])

    def test_weights_are_normalized_positive(self):
        w = self.cfg["dimension_weights"]
        self.assertTrue(all(v > 0 for v in w.values()))
        self.assertAlmostEqual(sum(w[d] for d in scoring.DIMENSIONS), sum(w.values()), places=6)

    def test_company_display_name(self):
        self.assertEqual(fetch_news.company_display_name("智谱AI（XtalPi）"), "智谱AI")
        self.assertEqual(fetch_news.company_display_name("西部超导"), "西部超导")

    def test_all_picks_match_pool(self):
        """精选池里的每个短名称都必须能匹配到底池（'实实在在挑出好公司'的兜底）。"""
        picks = scoring.load_picks()
        self.assertGreaterEqual(len(picks), 30)
        unmatched = [p["name"] for p in picks if not scoring.match_company(p["name"], self.companies)]
        self.assertEqual(unmatched, [])

    def test_picks_have_thesis_and_bucket(self):
        for p in scoring.load_picks():
            self.assertIn(p["bucket"], ("core", "option", "watch"), p["name"])
            self.assertTrue((p.get("thesis") or "").strip(), p["name"])

    def test_digest_picks_with_events_first(self):
        """精选标的有近7天事件 → 排在提醒最前，类型为精选动态。"""
        today = date(2026, 9, 22)
        scored = [
            dict(fake_company(name="西部超导", market="A股", ticker="688122", industry="可控核聚变"),
                 recent_events=[{"title": "新订单", "url": "u", "published": "2026-09-20"}]),
        ]
        picks_view = [{"name": "西部超导", "bucket": "core", "thesis": "t"}]
        diff = {"deltas": {}, "movers_up": [], "movers_down": []}
        items, alerts, upcoming = weekly_digest.build_digest(scored, picks_view, [], diff, today)
        self.assertEqual(items[0]["type"], "pick_event")
        self.assertEqual(items[0]["name"], "西部超导")
        self.assertTrue(items[0]["links"])

    def test_digest_caps_at_10_and_dedupes(self):
        today = date(2026, 9, 22)
        scored, picks_view = [], []
        for i in range(15):
            n = "公司%02d" % i
            scored.append(dict(fake_company(name=n, market="A股", ticker="%06d" % i, industry="半导体"),
                               recent_events=[{"title": "t%d" % i, "url": "u", "published": "2026-09-21"}]))
            picks_view.append({"name": n, "bucket": "core", "thesis": "t"})
            if i > 0:
                picks_view[-1] = {"name": n, "bucket": "watch", "thesis": "t"}
        diff = {"deltas": {}, "movers_up": [], "movers_down": []}
        items, _, _ = weekly_digest.build_digest(scored, picks_view, [], diff, today)
        self.assertLessEqual(len(items), 10)
        self.assertEqual(len({i["name"] for i in items}), len(items))

    def test_digest_quiet_week_is_honest(self):
        """没有事件、没有异动的周：输出为空且里程碑窗口提醒仍在（不硬凑公司）。"""
        today = date(2026, 9, 22)
        scored = [dict(fake_company(name="甲"), recent_events=[])]
        ms = [{"date": "2026-10-01", "sector": "可控核聚变", "event": "窗口测试",
               "status": "on_track", "days_left": 9, "status_view": "跟踪中", "alert": False}]
        diff = {"deltas": {}, "movers_up": [], "movers_down": []}
        items, alerts, upcoming = weekly_digest.build_digest(scored, [], ms, diff, today)
        self.assertEqual(items, [])
        self.assertEqual(upcoming[0]["event"], "窗口测试")
        text = weekly_digest.render_markdown(items, alerts, upcoming, "2026-09-22", has_events=True)
        self.assertIn("本周无显著变化", text)

    def test_digest_renders_links_and_alerts(self):
        today = date(2026, 9, 22)
        scored = [dict(fake_company(name="甲", ticker="000001"), recent_events=[])]
        picks_view = [{"name": "甲", "bucket": "core", "thesis": "t"}]
        diff = {"deltas": {"甲": 2.5}, "movers_up": [{"name": "甲", "delta": 2.5, "score": 60, "industry": "半导体"}],
                "movers_down": []}
        items, _, _ = weekly_digest.build_digest(scored, picks_view, [], diff, today)
        text = weekly_digest.render_markdown(items, [], [], "2026-09-22", True)
        self.assertIn("甲", text)
        self.assertIn("2026-09-22", text)


if __name__ == "__main__":
    unittest.main()
