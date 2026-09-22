# Hardtech Radar

> A tracking system for six hard-tech tracks in China's "equity-fiscal era": Semiconductors · AI Models · Quantum Computing · Fusion · AI Life Science · Embodied AI.
> **Curated picks + event-driven scoring + falsification calendar + weekly movers** over a 331-company pool. Zero third-party dependencies.

**⚠️ Disclaimer: This is an open-source research tool. RadarScore is a research-observation score for ranking only — not a quality rating and not investment advice. Company fundamentals are research compilations of public information (as of 2026-09); news events are public headlines from search-engine RSS feeds. Markets are risky.**

中文文档：[README.md](README.md)

---

## Why: picks are human, the radar keeps watch

Good companies come from deep research, not keyword black boxes. This project makes that explicit:

1. **Curated picks first** — `data/picks.json` holds the research conclusions: ~40 companies across 6 tracks, each with an explicit thesis and a bucket (`core` / `option` / `watch`). The Dashboard leads with it. The scoring system's job is to **monitor the picks and flag thesis reviews**: a listed pick falling below the 60th percentile of the full pool automatically appears in the report's "review hints".
2. **Scores breathe** — the "event heat" dimension is driven by real news (per-company and per-industry RSS feeds, last 30 days). Milestones are human-annotated (`on_track` / `slipped` / `hit` / `missed`) and feed back into the sector-window dimension — if SPARC slips, fusion scores actually drop.
3. **Falsification over narrative** — `data/milestones.json` holds hard verification points (SPARC first plasma, Helion→Microsoft 50MW, AI-pharma Phase III readout, IBM Starling…). One quarterly JSON edit keeps the calendar honest; the report surfaces slipped/missed items on top.

## Scoring model (v0.2)

| Dimension | Weight | Signal |
| --- | --- | --- |
| Certainty | 0.30 | "shovel-seller vs option" classification (narrative keywords) |
| Moat | 0.25 | monopoly/leader/only-one phrasing density |
| **Event heat** | 0.15 | **real news events** (30-day company/industry feeds) + nearby milestone bonus |
| Liquidity | 0.15 | listing venue + ticker |
| Risk control | 0.05 | bubble/falsified/loss phrasing penalties (deliberately low) |
| Sector window | 0.10 | distance to 2027–2035 payoff window + milestone status linkage |

All rules live in `config/weights.json`. Weekly diffs rely on `data/snapshots/previous.json` (committed by CI every week).

## Quick start

```bash
python -m unittest discover -s tests -v      # tests (stdlib only, Python 3.9+)
python engine/fetch_news.py                  # optional; degrades gracefully offline
python engine/build_report.py                # build data.js + REPORT.md + snapshot
python -m http.server 8080 --directory site  # preview dashboard at :8080
```

News fetching tries Bing first (reachable from mainland China), falls back to Google News. On GitHub Actions runners fetching is reliable.

## Deploy

```bash
git init && git add . && git commit -m "feat: hardtech radar v0.2"
git remote add origin https://github.com/<you>/hardtech-radar.git
git branch -M main && git push -u origin main
```

Then **Settings → Pages → Source: GitHub Actions**, run the workflow once. Live at `https://<you>.github.io/hardtech-radar/`.

## License

MIT
