---
name: invest-news
description: 采集市场新闻并存入公共原始数据区 ~/.openclaw/workspace/data/news/raw/
---

# Invest News Skill (Raw Ingestion)

## 核心职责

`invest-news` 是纯采集技能，只负责：
- 采集原始新闻事实
- 做最小去重（避免重复落盘）
- 追加写入 `~/.openclaw/workspace/data/news/raw/YYYY-MM-DD.jsonl`

**绝不做**：
- 真实性核实
- 重要性排序
- 观点总结
- 投资判断与结论分发
- 碰 `data/companies/` 目录（那是 invest-doc-router 和 invest-analysis 的职责）

## 关键路径

| 用途 | 路径 |
|---|---|
| 公司配置 | `~/.openclaw/workspace/data/references/companies.json` |
| 新闻落盘 | `~/.openclaw/workspace/data/news/raw/YYYY-MM-DD.jsonl` |

## 采集流程

### Step 1：读取公司配置

读取 `companies.json`，获取目标公司的 brands、competitors、industry_keywords 等字段，用于构造搜索查询。

### Step 2：联网搜索采集（全球化策略）

使用 Agent 自带的 web search 能力，根据 `companies.json` 中的 `market` 字段采用差异化搜索策略：

- **针对 CN / HK 市场**：优先中文财经信息源（财联社、东方财富、同花顺、雪球、36Kr、界面新闻等）。
- **针对 US / Global 市场**：
  - **核心信源**：必须检索全球顶级信源（Reuters, Bloomberg, CNBC, Seeking Alpha, Investing.com）。
  - **检索语言**：必须使用**英文名称/别名**进行检索，确保抓取到第一手全球战略信息。
  - **语言处理**：归档时 `title` 可保留原文，但 `content` 必须包含 Agent 翻译后的中文核心摘要。
- **全维度搜索**：
  - 公司维度：公司名/别名 + "最新消息" / "Latest News"
  - 品牌维度：每个 brand + "新闻"
  - 竞品维度：每个 competitor + 相关动态
- 聚焦最近 24 小时内的新闻。

### Step 3：去重与落盘

对搜索结果提取标准字段，去重后追加写入当日 JSONL 文件。

去重规则：同一天 + 同公司 + 同标题 + 同来源 = 重复，跳过。

### 落盘格式

每条新闻一行 JSON：

```json
{
  "ts": "2026-03-30 14:22:00",
  "source": "财联社",
  "title": "新闻标题",
  "content": "新闻正文或摘要",
  "url": "https://...",
  "company": "tme",
  "company_name": "腾讯音乐娱乐",
  "company_symbol": "01698",
  "company_market": "HK",
  "match_type": "company|brand|competitor|industry",
  "match_keyword": "QQ音乐"
}
```

## 执行方式

### 交互模式（用户对话中触发）

Agent 按照本文档指令直接执行：用内置 web search 搜索，按格式写入 JSONL。

### 批量模式（cron 自动触发）

```bash
python3 {baseDir}/scripts/fetch_news.py --date YYYY-MM-DD
```

注意：fetch_news.py 依赖 AkShare（需额外安装 `pip install akshare`），作为 web search 不可用时的备用方案。

## 执行规则

- **只写事实，不写观点**
- **只做简单去重，不做深度加工**
- **失败可回退为空结果，不用推断或补写**
- **允许空结果，不凑数、不补充无关内容**
- **可由 cron 自动触发**

## 自我进化机制 (Self-evolving Radar)

新闻采集不是被动抓取，而是一个能自我生长的雷达。

### 触发条件

在采集或阅读新闻的过程中，如果发现：
- 目标公司出现了新的竞品（如腾讯音乐冒出新对手"某某音乐"）
- 出现了新的旗下品牌或产品线
- 出现了新的行业关键词或趋势

### 执行方式

**assistant 执行时**：直接编辑 `~/.openclaw/workspace/data/references/companies.json`，在对应公司的 `competitors`、`brands` 或 `industry_keywords` 数组中增减条目。

**value_* agent 执行时**：不直接编辑 companies.json（防止多 agent 并发写入冲突）。改为将发现记录到 `memory/YYYY-MM-DD.md`，格式如下：

```markdown
## [HH:MM] 雷达更新建议
- 公司: tme
- 字段: competitors
- 操作: 新增 "某某音乐"
- 原因: 在搜索新闻时发现该竞品频繁出现
```

assistant 在下次执行 invest-news 时读取 value_* 的建议并统一更新。

### 闭环

```
搜索新闻 → 发现新竞品/关键词 → 更新 companies.json → 下次搜索覆盖更广
```

### 约束

- 新增条目前先确认不重复
- 删除条目需谨慎，仅在确认该关联已失效时才移除
- 每次更新后在当日 news raw 中记一条 `{"type": "radar_update", ...}` 日志
