# -*- coding: utf-8 -*-
"""硬科技雷达 · 评分引擎 v0.2

方法论（源自《股权财政时代》研究报告）：
  1. 卖铲人优先 —— 路线胜负未分时，确定性最高的是"无论谁赢都要采购"的环节；
  2. 核心仓 + 期权仓 —— 整机/路线型标的按期权估值，只给卫星仓位；
  3. 证伪清单 —— 里程碑人工维护状态（on_track/slipped/hit/missed），
     延期/落空自动拉低对应行业"赛道窗口"分；
  4. 兑现窗口 —— 2027-2035 是六大赛道共同的密集验证期，越近分越高。

v0.2 变化：催化密度（事件热度）改为真实新闻事件驱动（engine/fetch_news.py），
叙事关键词只保留在确定性/卡位两维。所有分数仅供研究观察排序，不构成投资建议。
"""
import json
import os
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DIMENSIONS = ["certainty", "moat", "catalyst", "liquidity", "risk", "window"]

# 公司层级标签
TIERS = [
    (70, "核心观察"),
    (55, "重点观察"),
    (45, "一般跟踪"),
    (0, "背景资料"),
]

STATUS_ADJUST_KEY = {"missed": "window_penalty_missed",
                     "slipped": "window_penalty_slipped",
                     "hit": "window_bonus_hit"}


def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def load_config():
    return load_json("config", "weights.json")


def load_companies():
    return load_json("data", "companies.json")


def load_milestones():
    data = load_json("data", "milestones.json")
    return sorted(data["milestones"], key=lambda m: m["date"])


def load_events(path=None):
    """读取事件文件；不存在/为空时优雅降级为空结构。"""
    p = path or os.path.join(ROOT, "data", "events.json")
    if not os.path.exists(p):
        return {"company": {}, "industry": {}, "meta": {"count": 0}}
    raw = json.load(open(p, encoding="utf-8"))
    return index_events(raw.get("events", []), raw)


def index_events(events, meta=None):
    """把事件列表按公司/行业索引，便于评分查询。"""
    idx = {"company": {}, "industry": {}, "meta": {"count": len(events)}}
    if meta:
        idx["meta"]["fetched_at"] = meta.get("fetched_at")
    for e in events:
        bucket = idx.get(e.get("type") or "company", idx["company"])
        bucket.setdefault(e.get("target") or "", []).append(e)
    return idx


def filter_recent(events, lookback_days, today=None):
    """只保留近 N 天事件（按 published 日期）。无日期的事件忽略。"""
    today = today or date.today()
    out = []
    for e in events:
        pub = e.get("published")
        if not pub:
            continue
        try:
            d = datetime.fromisoformat(pub).date()
        except ValueError:
            continue
        if (today - d).days <= lookback_days:
            out.append(e)
    return out


def _hits(text, keywords):
    text = text or ""
    return sum(1 for kw in keywords if kw in text)


def classify(company, cfg):
    """按角色关键词把标的分为 shovel（卖铲人）/ option（期权型）/ integrator（整机/总包）/ other。"""
    text = " ".join(str(company.get(k) or "") for k in ("role", "segment", "note", "name"))
    kw = cfg["keywords"]
    if _hits(text, kw["shovel"]) > 0:
        return "shovel"
    if _hits(text, kw["option"]) > 0:
        return "option"
    if _hits(text, kw["integrator"]) > 0:
        return "integrator"
    return "other"


CLASS_LABELS = {
    "shovel": "卖铲人",
    "option": "期权型",
    "integrator": "整机/总包",
    "other": "其他",
}


def sector_window_adjustment(sector, milestones, cfg):
    """按该赛道里程碑的人工状态计算赛道窗口分调整值。"""
    rules = cfg["event_rules"]
    adjust = 0
    for m in milestones:
        if m.get("sector") != sector:
            continue
        adjust += rules.get(STATUS_ADJUST_KEY.get(m.get("status"), ""), 0)
    return adjust


def next_milestone_bonus(sector, milestones, cfg, today=None):
    """该赛道最近的未到期里程碑越临近，事件热度加成越高。"""
    rules = cfg["event_rules"]
    today = today or date.today()
    best = None
    for m in milestones:
        if m.get("sector") != sector or m.get("status") in ("hit", "missed"):
            continue
        y, mo, d = (int(x) for x in m["date"].split("-"))
        delta = (date(y, mo, d) - today).days
        if delta >= 0 and (best is None or delta < best):
            best = delta
    if best is None:
        return 0
    if best <= rules["milestone_near_days"]:
        return rules["milestone_near_bonus"]
    if best <= rules["milestone_mid_days"]:
        return rules["milestone_mid_bonus"]
    return 0


def score_company(company, cfg, events=None, milestones=None, today=None):
    """给单个标的打分。events 为 index_events() 的索引，milestones 为里程碑列表。"""
    today = today or date.today()
    events = events or {"company": {}, "industry": {}}
    milestones = milestones if milestones is not None else load_milestones()
    text = " ".join(str(company.get(k) or "") for k in ("name", "segment", "role", "key_data", "note"))
    kw = cfg["keywords"]
    rules = cfg["event_rules"]
    industry = company.get("industry") or "综合"

    # 1) 确定性 certainty：叙事关键词（卖铲人 +，期权型 -）
    cert = 50.0
    cls = classify(company, cfg)
    if cls == "shovel":
        cert += 25
    elif cls == "option":
        cert -= 20
    elif cls == "integrator":
        cert -= 10

    # 2) 卡位强度 moat：垄断/龙头/第一等叙事关键词
    moat = 40.0 + 12 * _hits(text, kw["moat"])

    # 3) 事件热度 catalyst：真实新闻事件驱动（v0.2）
    comp_ev = filter_recent(events["company"].get(company["name"], []), rules["event_lookback_days"], today)
    ind_ev = filter_recent(events["industry"].get(industry, []), rules["event_lookback_days"], today)
    cata = float(rules["catalyst_base"])
    cata += min(rules["company_event_cap"], rules["company_event_points"] * len(comp_ev))
    cata += min(rules["industry_event_cap"], rules["industry_event_points"] * len(ind_ev))
    cata += next_milestone_bonus(industry, milestones, cfg, today)

    # 4) 流动性 liquidity：上市地 + 代码
    liq = float(cfg["liquidity_base"].get(company.get("market") or "原文未明确", 25))
    if (company.get("ticker") or "").strip():
        liq += cfg["liquidity_ticker_bonus"]

    # 5) 风险可控度 risk：叙事扣分项（权重已降至 0.05）
    risk = 100.0 - 12 * _hits(text, kw["risk"])

    # 6) 赛道窗口 window：兑现窗口距离 + 里程碑人工状态联动
    window = float(cfg["industry_window"].get(industry, 55))
    window += sector_window_adjustment(industry, milestones, cfg)

    dims = {
        "certainty": max(0, min(100, cert)),
        "moat": max(0, min(100, moat)),
        "catalyst": max(0, min(100, cata)),
        "liquidity": max(0, min(100, liq)),
        "risk": max(0, min(100, risk)),
        "window": max(0, min(100, window)),
    }
    w = cfg["dimension_weights"]
    total = sum(w[d] * dims[d] for d in DIMENSIONS) / sum(w[d] for d in DIMENSIONS)

    out = dict(company)
    out["class"] = cls
    out["class_label"] = CLASS_LABELS[cls]
    out["dimensions"] = {d: round(dims[d], 1) for d in DIMENSIONS}
    out["score"] = round(total, 1)
    for threshold, label in TIERS:
        if out["score"] >= threshold:
            out["tier"] = label
            break
    out["recent_events"] = [
        {"title": e["title"], "url": e["url"], "published": e.get("published"), "source": e.get("source")}
        for e in comp_ev[:3]
    ]
    return out


def score_all(companies, cfg, events=None, milestones=None, today=None):
    return [score_company(c, cfg, events, milestones, today) for c in companies]


def milestone_view(milestones, today=None):
    """给里程碑附加倒计时字段。"""
    today = today or date.today()
    view = []
    for m in milestones:
        y, mo, d = (int(x) for x in m["date"].split("-"))
        delta = (date(y, mo, d) - today).days
        item = dict(m)
        item["days_left"] = delta
        if m.get("status") == "hit":
            item["status_view"] = "兑现"
        elif m.get("status") == "missed":
            item["status_view"] = "落空"
        elif m.get("status") == "slipped":
            item["status_view"] = "延期"
        elif delta < 0:
            item["status_view"] = "已过期"
        else:
            item["status_view"] = "跟踪中"
        item["alert"] = m.get("status") in ("slipped", "missed")
        view.append(item)
    return view


def load_picks():
    data = load_json("data", "picks.json")
    return data["picks"]


def match_company(name, companies):
    """把精选名单中的短名称匹配到底池记录：精确 → 去括号前缀 → 包含。返回公司 dict 或 None。"""
    name = (name or "").strip()
    for c in companies:
        if c["name"] == name:
            return c
    for c in companies:
        base = c["name"].split("（")[0].split("(")[0].strip()
        if base == name:
            return c
    for c in companies:
        if name in c["name"] or (c.get("aliases") or "").find(name) >= 0:
            return c
    return None


def compute_diff(current, previous):
    """对比上次快照，返回 {name: delta} 与升降榜。"""
    prev_scores = (previous or {}).get("scores", {})
    deltas = {}
    for c in current:
        name = c["name"]
        if name in prev_scores:
            d = round(c["score"] - prev_scores[name], 1)
            if abs(d) >= 0.05:
                deltas[name] = d
    movers_up = sorted(
        [{"name": n, "delta": v, "score": c["score"], "industry": c["industry"]}
         for c in current for n, v in [(c["name"], deltas.get(c["name"]))] if n in deltas and v > 0],
        key=lambda x: -x["delta"])[:10]
    movers_down = sorted(
        [{"name": n, "delta": v, "score": c["score"], "industry": c["industry"]}
         for c in current for n, v in [(c["name"], deltas.get(c["name"]))] if n in deltas and v < 0],
        key=lambda x: x["delta"])[:10]
    return {"deltas": deltas, "movers_up": movers_up, "movers_down": movers_down}
