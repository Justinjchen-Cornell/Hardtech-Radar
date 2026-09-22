# -*- coding: utf-8 -*-
"""硬科技雷达 · 新闻事件抓取器 v0.2（零依赖，Google News RSS）

  python engine/fetch_news.py            # 常规抓取（6天内抓过则跳过）
  python engine/fetch_news.py --force    # 强制重新抓取
  python engine/fetch_news.py --limit 3  # 只抓前3个目标（调试用）

抓取对象：全部上市公司（按公司名）+ 六大赛道行业级 feed。
只保存标题/链接/来源/日期（60天窗口），每个目标限量，带 1.2s 限速。
网络不可用时逐目标容错继续；全部失败则保留旧数据并返回码 0 —— 构建流程永不因抓取失败而中断。
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(ROOT, "data", "events.json")
LISTED = ("A股", "港股", "美股")
FEED_WINDOW_DAYS = 60
PER_COMPANY_LIMIT = 3
PER_INDUSTRY_LIMIT = 8
REQUEST_INTERVAL = 1.2
MAX_AGE_HOURS = 120

INDUSTRY_QUERIES = {
    "半导体": "半导体 芯片",
    "AI大模型": "AI 大模型",
    "量子计算": "量子计算",
    "可控核聚变": "可控核聚变",
    "AI生命科学": "AI制药 脑机接口",
    "具身智能": "人形机器人 具身智能",
}

RSS_BING = "https://www.bing.com/news/search?q={query}&format=rss&setmkt=zh-CN&setlang=zh-hans"
RSS_GOOGLE = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hardtech-radar/0.2)"}


def company_display_name(name):
    """去掉括号别名：'智谱AI（XtalPi）' -> '智谱AI'"""
    for sep in ("（", "("):
        if sep in name:
            name = name.split(sep)[0]
    return name.strip()


def build_targets():
    companies = json.load(open(os.path.join(ROOT, "data", "companies.json"), encoding="utf-8"))
    targets = []
    for c in companies:
        if c.get("market") in LISTED:
            targets.append({
                "type": "company",
                "key": c["name"],
                "query": '"%s"' % company_display_name(c["name"]),
                "limit": PER_COMPANY_LIMIT,
            })
    for industry, q in INDUSTRY_QUERIES.items():
        targets.append({"type": "industry", "key": industry, "query": q, "limit": PER_INDUSTRY_LIMIT})
    return targets


def parse_rss_bytes(data):
    """解析 Google News RSS XML 字节流为条目列表（供测试与抓取共用）。"""
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()
        if not title or not link:
            continue
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).date().isoformat()
            except Exception:
                published = None
        items.append({"title": title, "url": link, "source": source, "published": published})
    return items


def fetch_feed(query, timeout=25):
    """抓取一条新闻搜索 RSS。默认 Bing（国内可直连），失败自动回退 Google News。"""
    last_err = None
    for template, source in ((RSS_BING, "Bing News"), (RSS_GOOGLE, None)):
        try:
            url = template.format(query=urllib.parse.quote(query))
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            items = parse_rss_bytes(data)
            if source:
                for it in items:
                    if not it["source"]:
                        it["source"] = source
            if items:
                return items
            last_err = RuntimeError("empty feed")
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("all feed sources failed")


def run(force=False, limit=None):
    now = datetime.now(timezone.utc)
    # 断网/限流友好：未到刷新周期且存在旧数据则跳过
    if not force and os.path.exists(EVENTS_PATH):
        try:
            old = json.load(open(EVENTS_PATH, encoding="utf-8"))
            age_h = (now - datetime.fromisoformat(old["fetched_at"])).total_seconds() / 3600
            if age_h < MAX_AGE_HOURS:
                print("events.json is %.0fh old (<%dh), skip fetch (--force to override)" % (age_h, MAX_AGE_HOURS))
                return 0
        except Exception:
            pass

    targets = build_targets()
    if limit:
        targets = targets[:limit]

    cutoff = (now - timedelta(days=FEED_WINDOW_DAYS)).date().isoformat()
    events, ok, fail = [], 0, 0
    for t in targets:
        try:
            items = fetch_feed(t["query"])
            kept = 0
            for it in items:
                if it["published"] and it["published"] < cutoff:
                    continue
                events.append({"type": t["type"], "target": t["key"],
                               "title": it["title"], "url": it["url"],
                               "source": it["source"], "published": it["published"]})
                kept += 1
                if kept >= t["limit"]:
                    break
            ok += 1
        except Exception as e:
            fail += 1
            print("  [warn] %s '%s': %s" % (t["type"], t["key"], e), file=sys.stderr)
        time.sleep(REQUEST_INTERVAL)

    # 去重 + 排序
    seen, uniq = set(), []
    for e in sorted(events, key=lambda x: x.get("published") or "", reverse=True):
        k = e["title"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)

    payload = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "window_days": FEED_WINDOW_DAYS,
        "feeds_ok": ok,
        "feeds_failed": fail,
        "count": len(uniq),
        "events": uniq,
    }
    json.dump(payload, open(EVENTS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("fetched: %d events from %d/%d feeds (failed %d) -> %s"
          % (len(uniq), ok, len(targets), fail, os.path.relpath(EVENTS_PATH, ROOT)))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略缓存强制抓取")
    ap.add_argument("--limit", type=int, default=None, help="只抓前 N 个目标（调试）")
    args = ap.parse_args()
    sys.exit(run(force=args.force, limit=args.limit))
