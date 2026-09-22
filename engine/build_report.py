# -*- coding: utf-8 -*-
"""硬科技雷达 · 构建脚本 v0.2

  python engine/build_report.py

生成：
  site/data.js                 —— Dashboard 数据（含周度 diff、里程碑状态、最近动态）
  REPORT.md                    —— 研究观察报告（证伪预警 + 升降榜 + 排名表）
  data/snapshots/previous.json —— 本次得分快照（供下次构建做周度 diff）
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import scoring  # noqa: E402
from engine import weekly_digest  # noqa: E402

ROOT = scoring.ROOT
LISTED = ("A股", "港股", "美股")
SNAPSHOT_PATH = os.path.join(ROOT, "data", "snapshots", "previous.json")
DIGEST_LATEST_PATH = os.path.join(ROOT, "data", "snapshots", "digest_latest.json")
DIGEST_HISTORY_PATH = os.path.join(ROOT, "data", "snapshots", "digest_history.json")
DIGEST_MD_PATH = os.path.join(ROOT, "DIGEST.md")
FEED_PATH = os.path.join(ROOT, "site", "feed.xml")
FEED_MAX_ENTRIES = 30


def build():
    cfg = scoring.load_config()
    companies = scoring.load_companies()
    milestones = scoring.load_milestones()
    events = scoring.load_events()
    today = date.today()
    generated = today.isoformat()

    scored = scoring.score_all(companies, cfg, events, milestones, today)
    scored.sort(key=lambda c: c["score"], reverse=True)
    ms_view = scoring.milestone_view(milestones, today)

    previous = None
    if os.path.exists(SNAPSHOT_PATH):
        try:
            previous = json.load(open(SNAPSHOT_PATH, encoding="utf-8"))
        except Exception:
            previous = None
    diff = scoring.compute_diff(scored, previous)

    # 精选池：人工名单 × 实时评分（"实实在在挑出好公司"的落地）
    picks = scoring.load_picks()
    picks_view = build_picks_view(picks, scored, companies, diff)

    # 每周提醒：精选动态/分数异动/底池雷达/证伪预警（≤10 家）+ 临近窗口
    has_events = bool(events["meta"].get("count"))
    digest = weekly_digest.build_and_render(scored, picks_view, ms_view, diff, today, has_events)
    digest_title = "📡 雷达周报 %s" % today.isoformat()
    os.makedirs(os.path.dirname(DIGEST_LATEST_PATH), exist_ok=True)
    json.dump({"title": digest_title, "generated": today.isoformat(), "markdown": digest["markdown"]},
              open(DIGEST_LATEST_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(DIGEST_MD_PATH, "w", encoding="utf-8") as f:
        f.write("# %s\n\n%s\n\n---\n\n> 由 [hardtech-radar](https://github.com/) 评分引擎自动生成。"
                "RadarScore 为研究观察分，仅供排序，不构成投资建议。\n" % (digest_title, digest["markdown"]))
    write_feed(generated, digest_title, digest["markdown"])

    # 写本次快照（供下次 diff）
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    json.dump({"generated_at": today.isoformat(),
               "scores": {c["name"]: c["score"] for c in scored}},
              open(SNAPSHOT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    stats = build_stats(scored, ms_view)

    payload = {
        "generated_at": generated,
        "version": cfg["version"],
        "dimension_names": cfg["dimension_names"],
        "dimension_weights": cfg["dimension_weights"],
        "events_meta": {"fetched_at": events["meta"].get("fetched_at"),
                        "count": events["meta"].get("count", 0)},
        "has_diff": previous is not None,
        "movers_up": diff["movers_up"],
        "movers_down": diff["movers_down"],
        "digest": {"items": digest["items"], "alerts": digest["alerts"],
                   "upcoming": digest["upcoming"], "markdown": digest["markdown"]},
        "picks": picks_view,
        "stats": stats,
        "milestones": ms_view,
        "companies": scored,
    }
    data_js_path = os.path.join(ROOT, "site", "data.js")
    with open(data_js_path, "w", encoding="utf-8") as f:
        f.write("// 由 engine/build_report.py 自动生成，请勿手改\n")
        f.write("window.RADAR_DATA = ")
        f.write(json.dumps(payload, ensure_ascii=False))
        f.write(";\n")

    report = render_report(cfg, scored, ms_view, diff, stats, generated,
                           previous is not None, events["meta"].get("count", 0), picks_view, digest)
    report_path = os.path.join(ROOT, "REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print("companies scored:", len(scored), "| events in index:", events["meta"].get("count", 0))
    print("diff vs previous:", "yes" if previous else "first run (no previous snapshot)")
    print("movers up/down:", len(diff["movers_up"]), "/", len(diff["movers_down"]))
    print("written:", os.path.relpath(data_js_path, ROOT))
    print("written:", os.path.relpath(report_path, ROOT))
    return payload


def write_feed(generated, title, markdown):
    """维护周报历史并生成 Atom 订阅源 site/feed.xml。"""
    history = []
    if os.path.exists(DIGEST_HISTORY_PATH):
        try:
            history = json.load(open(DIGEST_HISTORY_PATH, encoding="utf-8"))
        except Exception:
            history = []
    if not history or history[0].get("date") != generated:
        history.insert(0, {"date": generated, "title": title, "markdown": markdown})
    history = history[:FEED_MAX_ENTRIES]
    json.dump(history, open(DIGEST_HISTORY_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    entries = []
    for h in history:
        html = esc(h["markdown"]).replace("\n", "<br/>")
        entries.append(
            "<entry><title>%s</title><id>hardtech-radar-digest-%s</id>"
            "<updated>%sT00:00:00Z</updated>"
            '<content type="html">%s</content></entry>'
            % (esc(h["title"]), h["date"], h["date"], html))
    feed = ('<?xml version="1.0" encoding="utf-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>硬科技雷达周报</title>"
            "<id>hardtech-radar-weekly-digest</id>"
            "<updated>%sT00:00:00Z</updated>"
            "<link rel=\"self\" href=\"feed.xml\"/>"
            "<subtitle>六大赛道精选池动态 · 分数异动 · 证伪预警（研究观察，非投资建议）</subtitle>%s</feed>"
            % (generated, "".join(entries)))
    with open(FEED_PATH, "w", encoding="utf-8") as f:
        f.write(feed)


def build_stats(companies, ms_view):
    from collections import Counter

    upcoming = [m for m in ms_view if m["days_left"] >= 0 and m["status_view"] not in ("兑现", "落空")]
    alerts = [m for m in ms_view if m["alert"]]
    return {
        "total": len(companies),
        "by_industry": dict(Counter(c["industry"] for c in companies)),
        "by_market": dict(Counter(c["market"] for c in companies)),
        "by_class": dict(Counter(c["class_label"] for c in companies)),
        "listed": sum(1 for c in companies if c["market"] in LISTED),
        "next_milestone": upcoming[0] if upcoming else None,
        "alerts": len(alerts),
    }


def build_picks_view(picks, scored, companies, diff):
    """精选池 × 实时评分。返回带实时分/层级/排名百分位/事件的精选列表。"""
    by_name = {c["name"]: c for c in scored}
    n = len(scored)
    view, unmatched = [], []
    for p in picks:
        target = scoring.match_company(p["name"], companies)
        if not target:
            unmatched.append(p["name"])
            continue
        c = by_name[target["name"]]
        rank = scored.index(c) + 1
        listed = target.get("market") in LISTED
        view.append({
            "sector": p["sector"], "bucket": p["bucket"], "name": target["name"],
            "ticker": target.get("ticker", ""), "market": target.get("market", ""),
            "thesis": p["thesis"], "score": c["score"], "tier": c["tier"],
            "rank_pct": round(rank / n * 100, 1) if listed else None,
            "delta": diff["deltas"].get(target["name"]),
            "recent_events": c.get("recent_events", []),
        })
    view.sort(key=lambda x: (x["sector"], {"core": 0, "option": 1, "watch": 2}.get(x["bucket"], 3), -x["score"]))
    if unmatched:
        print("[warn] picks 未匹配到底池:", unmatched, file=sys.stderr)
    return view


def render_report(cfg, companies, ms_view, diff, stats, generated, has_diff, events_count, picks_view, digest):
    has_events = events_count > 0
    lines = []
    add = lines.append
    add("# 硬科技雷达 · 研究观察报告")
    add("")
    add(f"> 生成日期：{generated} ｜ 配置版本：v{cfg['version']} ｜ 标的池：{stats['total']} 家 ｜ "
        f"事件池：{events_count} 条 ｜ {stats['alerts']} 项证伪预警")
    add(">")
    add("> ⚠️ 本报告由开源评分引擎自动生成。RadarScore 为**研究观察分，仅供排序**，")
    add("> 不是质量评级，更不构成任何投资建议。公司基础数据截至 2026-09 口径。")
    add("")

    # 证伪预警
    alerts = [m for m in ms_view if m["alert"]]
    add("## 📡 本周提醒（≤10 家有进展或变化的公司）")
    add("")
    if digest["items"]:
        add("| 类型 | 公司 | 变化 |")
        add("| --- | --- | --- |")
        for it in digest["items"]:
            add(f"| {it['type_label']} | **{it['name']}**（{it['ticker'] or '未上市'}） | {it['summary']} |")
    else:
        add("本周无显著变化" + ("（事件池为空，抓取未运行或网络受限）。" if not has_events else "。"))
    for a in digest["alerts"]:
        add("")
        add(f"- ⚠️ 证伪预警：{a['sector']}「{a['event']}」→ **{a['status_view']}**")
    for u in digest["upcoming"]:
        add("")
        add(f"- ⏳ 距离「{u['event']}」（{u['sector']}）还有 **{u['days_left']} 天**")
    add("")
    add("> 订阅方式：Watch 本仓库（Issue 周报）· Atom 源 `feed.xml` · 或配置 Secrets 推送到微信/钉钉/TG（见 README）。")
    add("")

    add("## 一、精选池校验（人工名单 × 实时监控）")
    add("")
    add("方法论：好公司来自深度研究的'首选组合'，雷达负责持续监控——精选股分数异动时提示复核论点。")
    add("")
    add("| 赛道 | 仓位 | 公司 | 市场 | 论点 | 现分 | 周变动 | 层级 | 总榜百分位 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for p in picks_view:
        delta = "—" if p["delta"] is None else ("+" + str(p["delta"]) if p["delta"] > 0 else str(p["delta"]))
        bucket = {"core": "核心仓", "option": "期权仓", "watch": "观察哨"}.get(p["bucket"], p["bucket"])
        pct = "—" if p["rank_pct"] is None else f"{p['rank_pct']}%"
        add(f"| {p['sector']} | {bucket} | {p['name']} | {p['market']} | {p['thesis']} "
            f"| {p['score']} | {delta} | {p['tier']} | {pct} |")
    low = [p for p in picks_view
           if p["rank_pct"] is not None and p["rank_pct"] > 60 and p["bucket"] in ("core", "option")]
    if low:
        add("")
        add("> 🔍 **复核提示**：" + "、".join(p["name"] for p in low)
            + " 总榜百分位已低于 60%，建议复核入选论点是否仍成立（未上市标的不参与百分位比较）。")
    add("")

    add("## 二、证伪预警（人工复核的里程碑状态）")
    add("")
    if alerts:
        add("| 状态 | 赛道 | 里程碑 | 复核日期 | 备注 |")
        add("| --- | --- | --- | --- | --- |")
        for m in alerts:
            add(f"| **{m['status_view']}** | {m['sector']} | {m['event']} | {m.get('checked_at', '—')} | {m.get('note') or '—'} |")
    else:
        add("当前全部里程碑状态为 on_track（跟踪中），无预警。")
    add("")

    add("## 三、兑现窗口（证伪清单日历）")
    add("")
    add("方法论：用硬验证点替代叙事。状态由人工季度复核（`data/milestones.json`），延期/落空自动拉低对应行业窗口分。")
    add("")
    add("| 距今 | 日期 | 赛道 | 状态 | 事件 | 证伪条件 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for m in ms_view:
        if m["days_left"] < 0 and m["status_view"] == "跟踪中":
            countdown = f"已过 {-m['days_left']} 天"
        elif m["days_left"] < 0:
            countdown = f"-{-m['days_left']} 天"
        else:
            countdown = f"{m['days_left']} 天"
        add(f"| {countdown} | {m['date']} | {m['sector']} | {m['status_view']} | {m['event']} | {m['falsifier']} |")
    add("")

    # 周度变动
    add("## 四、本周雷达变动")
    add("")
    if not has_diff:
        add("> 首次构建，无上期快照可比。下次构建将自动生成本周升降榜。")
    else:
        add("### ↑ 升幅 Top10")
        add("")
        if diff["movers_up"]:
            add("| 公司 | 行业 | 现分 | 变动 |")
            add("| --- | --- | --- | --- |")
            for m in diff["movers_up"]:
                add(f"| {m['name']} | {m['industry']} | {m['score']} | **+{m['delta']}** |")
        else:
            add("无。")
        add("")
        add("### ↓ 跌幅 Top10")
        add("")
        if diff["movers_down"]:
            add("| 公司 | 行业 | 现分 | 变动 |")
            add("| --- | --- | --- | --- |")
            for m in diff["movers_down"]:
                add(f"| {m['name']} | {m['industry']} | {m['score']} | **{m['delta']}** |")
        else:
            add("无。")
    add("")

    add("## 五、组合观察名单（非投资建议）")
    add("")
    core = [c for c in companies if c["class"] == "shovel" and c["market"] in LISTED][:10]
    option = [c for c in companies if c["class"] == "option" or c["market"].startswith("未上市")][:10]
    add("### 核心仓观察（已上市卖铲人 Top10，确定性优先）")
    add("")
    add("| 排名 | 公司 | 代码 | 行业 | RadarScore | 层级 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for i, c in enumerate(core, 1):
        add(f"| {i} | {c['name']} | {c['ticker'] or '—'} | {c['industry']} | {c['score']} | {c['tier']} |")
    add("")
    add("### 卫星仓观察（期权型/未上市 Top10，高赔率优先）")
    add("")
    add("| 排名 | 公司 | 市场 | 行业 | RadarScore | 层级 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for i, c in enumerate(option, 1):
        add(f"| {i} | {c['name']} | {c['market']} | {c['industry']} | {c['score']} | {c['tier']} |")
    add("")

    add("## 六、标的池总排名")
    add("")
    dn = cfg["dimension_names"]
    add("| 排名 | 公司 | 代码 | 市场 | 行业 | 类型 | 得分 | 层级 | "
        f"{dn['certainty']} | {dn['moat']} | {dn['catalyst']} | {dn['liquidity']} | {dn['risk']} | {dn['window']} |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for i, c in enumerate(companies, 1):
        d = c["dimensions"]
        add(
            f"| {i} | {c['name']} | {c['ticker'] or '—'} | {c['market']} | {c['industry']} "
            f"| {c['class_label']} | {c['score']} | {c['tier']} "
            f"| {d['certainty']} | {d['moat']} | {d['catalyst']} | {d['liquidity']} | {d['risk']} | {d['window']} |"
        )
    add("")
    add("## 七、评分方法")
    add("")
    add("- 六个维度（各 0-100）：" + "、".join(f"{dn[d]}({cfg['dimension_weights'][d]})" for d in scoring.DIMENSIONS))
    add("- **事件热度**为真实信号：近30天公司/行业新闻数（`engine/fetch_news.py` 每周抓取）+ 临近里程碑加成")
    add("- **叙事关键词**只作用于确定性/卡位（同源叙事的回声，权重已刻意压低，仅供排序）")
    add("- **赛道窗口**受里程碑人工状态联动：missed −15 / slipped −8 / hit +10（`config/weights.json` 可调）")
    add("- 标的类型：`卖铲人`（确定性优先）/ `期权型`（高赔率优先）/ `整机/总包` / `其他`")
    add("- 修改权重后重跑 `python engine/build_report.py` 即可全量重算；周度 diff 依赖 `data/snapshots/previous.json`")
    add("")
    add("---")
    add("")
    add("数据来源：《股权财政时代的财富逻辑》对话研究整理 + Google News RSS 公开新闻标题（只存标题/链接/日期）。")
    add("免责声明：本项目为开源研究工具，不构成任何证券投资建议。市场有风险，投资需谨慎。")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    build()
