# -*- coding: utf-8 -*-
"""硬科技雷达 · 每周提醒引擎 v0.2

从以下信号中挑出"本周有进展或变化"的公司（最多 10 家，按变化强度排序）：
  1. 精选池标的出现近 7 天新闻事件（最强信号：首选组合有进展）
  2. 周度分数升降（事件驱动的结果）
  3. 非精选标的的高分+新事件（底池雷达）
  4. 证伪预警（里程碑被人工标记 slipped/missed）
附：临近里程碑窗口提醒（≤30 天，不占 5-10 家名额）。
没有料的周会诚实输出"本周无显著变化"——绝不硬凑。
"""
import json
import os
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TYPE_LABELS = {
    "pick_event": "精选动态",
    "mover": "分数异动",
    "pool_event": "底池雷达",
    "falsify": "证伪预警",
}
BUCKET_LABELS = {"core": "核心仓", "option": "期权仓", "watch": "观察哨"}


def _week_filter(events, today, days=7):
    cutoff = (today - timedelta(days=days)).isoformat()
    return [e for e in events if (e.get("published") or "") >= cutoff]


def build_digest(scored, picks_view, ms_view, diff, today, max_items=10):
    """返回 (items, alerts, upcoming)。
    items: [{type, type_label, name, ticker, sector, summary, links, delta}]
    alerts: 证伪预警里程碑列表；upcoming: ≤30 天临近里程碑列表。
    """
    pick_by_name = {p["name"]: p for p in picks_view}
    items = []

    def add_item(item):
        if item["name"] in {i["name"] for i in items}:
            return
        items.append(item)

    # 1) 精选池动态：近 7 天有新闻事件的精选标的
    for c in scored:
        p = pick_by_name.get(c["name"])
        if not p:
            continue
        evs = _week_filter(c.get("recent_events", []), today)
        if not evs:
            continue
        bucket = BUCKET_LABELS.get(p["bucket"], p["bucket"])
        add_item({
            "type": "pick_event", "type_label": TYPE_LABELS["pick_event"],
            "name": c["name"], "ticker": c.get("ticker", ""), "sector": c["industry"],
            "summary": "%s（%s）本周新进展：%s" % (bucket, p["thesis"], evs[0]["title"]),
            "links": [{"title": e["title"], "url": e["url"]} for e in evs[:3]],
            "delta": diff["deltas"].get(c["name"]),
        })

    # 2) 分数异动（事件驱动的结果），按绝对变动排序
    movers = sorted(diff["movers_up"] + diff["movers_down"], key=lambda m: -abs(m["delta"]))
    by_name = {c["name"]: c for c in scored}
    for m in movers:
        if len(items) >= max_items:
            break
        c = by_name.get(m["name"], {})
        add_item({
            "type": "mover", "type_label": TYPE_LABELS["mover"],
            "name": m["name"], "ticker": c.get("ticker", ""), "sector": m.get("industry", ""),
            "summary": "周分数变动 %+.1f（现 %.1f，%s）" % (m["delta"], m["score"], c.get("tier", "")),
            "links": [], "delta": m["delta"],
        })

    # 3) 底池雷达：非精选、已上市、有近 7 天事件，按得分取强者
    for c in scored:
        if len(items) >= max_items:
            break
        if c["name"] in pick_by_name or c["market"] not in ("A股", "港股", "美股"):
            continue
        evs = _week_filter(c.get("recent_events", []), today)
        if not evs:
            continue
        add_item({
            "type": "pool_event", "type_label": TYPE_LABELS["pool_event"],
            "name": c["name"], "ticker": c.get("ticker", ""), "sector": c["industry"],
            "summary": "底池异动（%s，%.1f 分）：%s" % (c["tier"], c["score"], evs[0]["title"]),
            "links": [{"title": e["title"], "url": e["url"]} for e in evs[:2]],
            "delta": diff["deltas"].get(c["name"]),
        })

    items = items[:max_items]

    # 4) 证伪预警与临近窗口（独立于 5-10 家名额）
    alerts = [m for m in ms_view if m.get("alert")]
    upcoming = [m for m in ms_view
                if 0 <= m["days_left"] <= 30 and m.get("status") not in ("hit", "missed")]
    return items, alerts, upcoming


def render_markdown(items, alerts, upcoming, generated, has_events):
    lines = []
    if not items:
        lines.append("本周无显著变化。" if has_events
                     else "本周事件池为空（抓取未运行或网络受限），无法判断是否有变化。")
    for i, it in enumerate(items, 1):
        head = "**%d. %s**（%s）｜%s" % (i, it["name"], it["ticker"] or "未上市", it["type_label"])
        lines.append(head)
        lines.append("- " + it["summary"])
        for lk in it["links"]:
            lines.append("- 新闻：[%s](%s)" % (lk["title"][:80], lk["url"]))
    for m in alerts:
        lines.append("- ⚠️ 证伪预警：%s「%s」被标记为 **%s**" % (m["sector"], m["event"], m["status_view"]))
    for m in upcoming:
        lines.append("- ⏳ 距离「%s」（%s）还有 %d 天" % (m["event"], m["sector"], m["days_left"]))
    lines.append("")
    lines.append("> 生成日期 %s。以上为研究观察信号，不构成投资建议。" % generated)
    return "\n".join(lines)


def render_table_rows(items):
    """给 REPORT/Dashboard 用的紧凑行。"""
    return [{
        "type": it["type"], "type_label": it["type_label"], "name": it["name"],
        "ticker": it["ticker"], "sector": it["sector"], "summary": it["summary"],
        "links": it["links"], "delta": it["delta"],
    } for it in items]


def build_and_render(scored, picks_view, ms_view, diff, today, has_events, max_items=10):
    items, alerts, upcoming = build_digest(scored, picks_view, ms_view, diff, today, max_items)
    return {
        "items": render_table_rows(items),
        "alerts": [{"sector": m["sector"], "event": m["event"], "status_view": m["status_view"]}
                   for m in alerts],
        "upcoming": [{"sector": m["sector"], "event": m["event"], "days_left": m["days_left"]}
                     for m in upcoming],
        "markdown": render_markdown(items, alerts, upcoming, today.isoformat(), has_events),
    }


if __name__ == "__main__":  # 自检入口：python engine/weekly_digest.py（无精选视图的降级自检）
    import sys
    sys.path.insert(0, ROOT)
    from engine import scoring
    cfg = scoring.load_config()
    ms = scoring.milestone_view(scoring.load_milestones())
    scored = scoring.score_all(scoring.load_companies(), cfg, scoring.load_events(), ms)
    scored.sort(key=lambda c: c["score"], reverse=True)
    prev_path = os.path.join(ROOT, "data", "snapshots", "previous.json")
    prev = json.load(open(prev_path, encoding="utf-8")) if os.path.exists(prev_path) else None
    diff = scoring.compute_diff(scored, prev)
    out = build_and_render(scored, [], ms, diff, date.today(), bool(scoring.load_events()["meta"].get("count")))
    print(out["markdown"])
