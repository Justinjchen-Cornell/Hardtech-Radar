# 硬科技雷达 · Hardtech Radar

> 股权财政时代的六大赛道跟踪系统：半导体 · AI 大模型 · 量子计算 · 可控核聚变 · AI 生命科学 · 具身智能。
> **精选池（人工首选组合）+ 事件驱动评分 + 证伪清单日历 + 周度升降榜**，331 家标的池，零第三方依赖。

**⚠️ 免责声明：本项目是开源研究工具。RadarScore 为研究观察分，仅供排序，不是质量评级，更不构成任何投资建议。公司基础数据为公开信息的研究性整理（2026-09 口径），新闻事件为搜索引擎 RSS 公开标题。市场有风险，投资需谨慎。**

English README: [README.en.md](README.en.md)

---

## 核心理念：好公司是"选"出来的，系统负责"盯"出来

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                      数据层 data/                                │
 │  companies.json(331标的)  picks.json(人工精选池)  milestones.json │
 │       底池与口径            首选组合+论点        硬验证点+人工状态  │
 └──────────────┬──────────────────────────────────────────────────┘
                │
 ┌──────────────▼──────────────┐   每周(GitHub Actions)   ┌──────────────────┐
 │      engine/fetch_news.py   │ ───────────────────────▶ │ 搜索引擎新闻 RSS  │
 │      事件抓取(Bing→Google)   │   只存标题/链接/日期      │  公司feed×121     │
 └──────────────┬──────────────┘                          │  行业feed×6       │
                │ events.json                              └──────────────────┘
 ┌──────────────▼──────────────┐
 │        engine/scoring.py    │  六维评分：确定性.30 卡位.25 事件热度.15
 │  评分引擎（规则全部在config） │           流动性.15 风险.05 赛道窗口.10
 │  里程碑状态联动窗口分         │  slipped/missed ↓行业窗口分
 └──────────────┬──────────────┘
 ┌──────────────▼──────────────┐
 │      engine/build_report.py │  周度快照 diff → 升降榜
 │ 精选池校验×实时分 │ REPORT.md │  精选股掉分 → 复核提示
 └──────────────┬──────────────┘
 ┌──────────────▼──────────────┐
 │   site/ 静态Dashboard(Pages)│  精选池首屏 · 证伪日历 · 筛选/搜索 · CSV导出
 └─────────────────────────────┘
```

三条铁律：

1. **精选池优先**：好公司来自深度研究的"首选组合"（`data/picks.json`，每家带投资论点），Dashboard 第一屏就是它。评分系统不做黑箱选股，它的任务是**持续监控精选标的并在异动时提示复核论点**——已上市精选股总榜百分位跌破 60% 会自动出现在报告的"复核提示"里。
2. **分数会呼吸**：事件热度维度由真实新闻事件驱动（近 30 天公司/行业 feed），里程碑人工状态（on_track/slipped/hit/missed）联动赛道窗口分——SPARC 延期，聚变板块真的会扣分。
3. **证伪清单可操作**：每季度人工复核一次 `milestones.json` 的状态字段（几行 JSON），REPORT.md 自动把延期/落空的里程碑顶到最前面。

## 快速开始

```bash
# 运行测试（无第三方依赖，仅需 Python 3.9+）
python -m unittest discover -s tests -v

# 抓取新闻事件（可选；失败自动降级，不阻塞构建）
python engine/fetch_news.py            # 6天内抓过会跳过；--force 强制；--limit 3 调试

# 构建数据与报告
python engine/build_report.py

# 本地预览 Dashboard
python -m http.server 8080 --directory site
# 浏览器打开 http://localhost:8080
```

> 网络说明：新闻抓取优先走 Bing（国内可直连），失败自动回退 Google News；本机网络受限时会优雅降级（0 事件照常构建），GitHub Actions 环境可稳定抓取。

## 精选池（示例）

| 赛道 | 仓位 | 标的 | 论点（节选） |
| --- | --- | --- | --- |
| 可控核聚变 | 核心仓 | 联创光电 | 最纯正聚变磁体卖铲人，星火一号约 50 亿元订单 |
| 可控核聚变 | 期权仓 | DJT（TAE） | FRC+氢硼无中子，百倍空间梦想、归零也无妨 |
| 量子计算 | 核心仓 | 国盾量子 | 量子通信已商用+测控+制冷机自研的 A 股绝对稀缺 |
| 半导体 | 核心仓 | 北方华创 | 只要晶圆厂扩产就有订单的设备卖铲人 |
| AI大模型 | 期权仓 | DeepSeek | 约 1/10 成本做同级模型的开源期权 |
| AI生命科学 | 核心仓 | 晶泰控股 | 行业第一个盈利者，70 多亿现金的压舱石 |
| 具身智能 | 核心仓 | 三花智控 | Optimus 供应链 Tier 1 + 主业现金流托底 |

完整 39 家见 Dashboard 或 `data/picks.json`。名单人工维护，欢迎 Issue/PR 讨论增删——这正是把它做成配置文件的原因。

## 评分模型（v0.2）

| 维度 | 权重 | 信号来源 | 说明 |
| --- | --- | --- | --- |
| 确定性 | 0.30 | 叙事关键词（卖铲人/期权型分类） | 同源叙事，仅供排序 |
| 卡位强度 | 0.25 | 垄断/龙头/唯一等表述 | 同上 |
| **事件热度** | 0.15 | **真实新闻事件**（近30天公司/行业 feed）+ 临近里程碑 | 每周真实变动 |
| 流动性 | 0.15 | 上市地基准 + 代码 | |
| 风险可控度 | 0.05 | 泡沫/证伪/亏损等扣分 | 叙事回声，刻意压低 |
| 赛道窗口 | 0.10 | 兑现窗口距离 + **里程碑人工状态联动** | missed −15 / slipped −8 / hit +10 |

所有规则在 `config/weights.json`，改配置即全量重算。周度 diff 依赖 `data/snapshots/previous.json`（Actions 每周提交，自动积累时间轴）。

## 项目结构

```
hardtech-radar/
├── config/weights.json        # 评分权重 + 关键词 + 事件规则
├── data/
│   ├── companies.json         # 331 标的底池（含 as_of 口径标注）
│   ├── picks.json             # 精选池：39 家首选组合 + 论点
│   ├── milestones.json        # 硬验证点 + 人工状态(on_track/slipped/hit/missed)
│   ├── events.json            # 抓取产物：新闻事件（标题/链接/日期）
│   └── snapshots/previous.json# 上期得分快照（周度 diff 依赖）
├── engine/
│   ├── fetch_news.py          # RSS 事件抓取（Bing→Google，优雅降级）
│   ├── scoring.py             # 六维评分 + 里程碑联动 + 精选匹配 + diff
│   └── build_report.py        # 生成 data.js / REPORT.md / 快照
├── tests/test_scoring.py      # 21 个单元测试
├── site/                      # 零依赖静态 Dashboard
└── .github/workflows/update.yml  # 每周：抓取→评分→diff→提交→部署 Pages
```

## 发布到 GitHub

```bash
cd hardtech-radar
git init && git add . && git commit -m "feat: hardtech radar v0.2"
git remote add origin https://github.com/<你的用户名>/hardtech-radar.git
git branch -M main && git push -u origin main
```

推送后 **Settings → Pages → Source 选 GitHub Actions**，手动触发一次 workflow 完成首次部署。
站点：`https://<你的用户名>.github.io/hardtech-radar/`

## 每周提醒：三种触达方式

每周一 workflow 自动从"精选池新事件 → 分数升降 → 底池异动 → 证伪预警"中挑出**≤10 家有实质进展或变化的公司**（没有料就诚实说无变化+列临近里程碑，绝不硬凑），然后：

| 方式 | 配置 | 说明 |
| --- | --- | --- |
| **GitHub Issue 周报** | 零配置，自动开启 | 每周自动开一条 `📡 雷达周报` Issue，**Watch 本仓库即可收到站内/邮件通知** |
| **Atom 订阅源** | 零配置 | `https://<你>.github.io/hardtech-radar/feed.xml`，RSS 阅读器可订 |
| **微信/钉钉/TG 推送** | 可选 Secrets | `SERVERCHAN_KEY`（Server酱→微信）/ `WECOM_WEBHOOK` / `DINGTALK_WEBHOOK` / `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID`，配哪个推哪个，不配自动跳过 |

## Roadmap

- [ ] v0.3 融资事件结构化（一级市场周报）
- [ ] v0.3 精选池历史论点存档与命中复盘
- [ ] 六维雷达图视图；中英双语站点
- [ ] 更多数据源（公告/临床登记/专利）接入 fetcher 框架

## License

MIT
