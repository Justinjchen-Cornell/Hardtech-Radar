# -*- coding: utf-8 -*-
"""硬科技雷达 · 可选推送通道（全部按需启用，未配置 Secret 时静默跳过）

支持：
  SERVERCHAN_KEY      Server酱·Turbo —— 推送到微信（推荐国内用户）
  WECOM_WEBHOOK       企业微信群机器人 Webhook
  DINGTALK_WEBHOOK    钉钉群机器人 Webhook（注意机器人安全设置里的自定义关键词，
                      建议设置为"雷达"，周报标题已包含）
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID   Telegram Bot

  python engine/notify.py    # 读取 data/snapshots/digest_latest.json 并推送
失败只告警不抛错——推送永远不阻塞构建。
"""
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST_PATH = os.path.join(ROOT, "data", "snapshots", "digest_latest.json")
TIMEOUT = 20


def _post(url, data=None, as_json=True):
    body = json.dumps(data).encode("utf-8") if as_json else urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "hardtech-radar/0.2"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def push_serverchan(key, title, markdown):
    import urllib.parse
    return _post("https://sctapi.ftqq.com/%s.send" % key,
                 {"title": title, "desp": markdown}, as_json=False)


def push_wecom(webhook, markdown):
    return _post(webhook, {"msgtype": "markdown",
                           "markdown": {"content": markdown[:4000]}})


def push_dingtalk(webhook, title, markdown):
    return _post(webhook, {"msgtype": "markdown",
                           "markdown": {"title": title, "text": markdown[:18000]}})


def push_telegram(token, chat_id, markdown):
    return _post("https://api.telegram.org/bot%s/sendMessage" % token,
                 {"chat_id": chat_id, "text": markdown, "disable_web_page_preview": True})


def run():
    if not os.path.exists(DIGEST_PATH):
        print("no digest file, skip notify")
        return 0
    digest = json.load(open(DIGEST_PATH, encoding="utf-8"))
    title, markdown = digest.get("title", "雷达周报"), digest.get("markdown", "")
    sent, skipped = [], []
    attempts = [
        ("ServerChan", bool(os.environ.get("SERVERCHAN_KEY")),
         lambda: push_serverchan(os.environ["SERVERCHAN_KEY"], title, markdown)),
        ("WeCom", bool(os.environ.get("WECOM_WEBHOOK")),
         lambda: push_wecom(os.environ["WECOM_WEBHOOK"], title + "\n" + markdown)),
        ("DingTalk", bool(os.environ.get("DINGTALK_WEBHOOK")),
         lambda: push_dingtalk(os.environ["DINGTALK_WEBHOOK"], title, markdown)),
        ("Telegram", bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
         lambda: push_telegram(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], markdown)),
    ]
    for name, configured, fn in attempts:
        if not configured:
            skipped.append(name)
            continue
        try:
            fn()
            sent.append(name)
        except Exception as e:
            print("[warn] %s push failed: %s" % (name, e), file=sys.stderr)
    print("notify: sent=%s skipped=%s" % (sent or "none", skipped or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(run())
