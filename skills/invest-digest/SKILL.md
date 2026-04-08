---
name: invest-digest
description: 每日新闻简报——从原始新闻中筛选、核实、按重要性排序，生成个性化新闻摘要
---

# Invest Digest Skill

## 核心职责

每日新闻策展——将 invest-news 采集的原始新闻加工为可直接阅读的个性化简报。

```
invest-news（采集）→ invest-ingest（分流）→ invest-digest（简报）← 本技能
```

## 数据源

| 输入 | 路径 |
|---|---|
| 当日原始新闻 | `{OPENCLAW_DATA_DIR}/news/raw/YYYY-MM-DD.jsonl` |
| 公司分流新闻 | `{OPENCLAW_DATA_DIR}/companies/{co}/news/raw/` |
| 关注清单 | `SOUL.md` → Active Watchlist |
| 公司配置 | `{OPENCLAW_DATA_DIR}/references/companies.json` |
| 行业认知 | `domains/{domain}.md` |

## 触发方式

**本技能无需任何外部参数。** 直接发送"请执行 invest-digest 技能"即可。
所有数据路径均自动解析（基于 `OPENCLAW_DATA_DIR` + 当日日期），无需传递 `path`、`ref-ids` 等流水线参数。
可在 `invest-news` + `invest-ingest` 之后自动触发，也可单独调用。

## 执行步骤

1. 读取 `references/digest-template.md` 获取排序规则、核实等级和输出模板
2. 从 SOUL.md 的 Active Watchlist 确定今日关注的公司列表
3. 对每家公司收集：个股新闻 + 竞品新闻（companies.json 的 competitors）+ 行业新闻（industry_keywords）
4. **跨日语义去重（重要）**：调取前一日（或最近一次）的简报存档（`memory/` 下的文件）。如果某重大事件（如“Spotify宣布4月28日发财报”）在昨日简报中已经汇报过，且今日新闻中**没有实质性的新进展**，则在今日简报中**直接剔除或仅一笔带过**，绝不重复占用篇幅。
5. 多源交叉验证：同一事件是否有 ≥2 个独立信源？标记核实等级
6. 按高/中/低重要性排序，SOUL.md 锚点相关的新闻提升优先级
7. 组装并输出简报内容
8. **执行物理写盘与脚本调用**（见下方输出位置要求）

## 输出位置（防止虚假执行的极度危险区）

**严禁仅在对话中回复“已写入文件”而不进行物理工具调用！这会被认定为严重的执行事故（Hallucinated Execution）。**

- **主要输出**：直接在对话中呈现给用户
- **物理存档（必做）**：你**必须**调用写文件工具（如 `fs_write` / `write`）或者执行终端命令追加写入（`echo '...' >> memory/YYYY-MM-DD.md`），将你刚才生成的简报内容真实地追加到 `memory/YYYY-MM-DD.md` 文件中，并带上 `## 每日简报` 的标题。
- **机器可读清单（必做）**：你**必须**亲自调用执行终端命令的工具（如 `exec` 或 `bash`），在工作区根目录执行 `python3 skills/invest-digest/scripts/generate_digest.py --date YYYY-MM-DD`（替换为当前日期）。此脚本会强制生成自动化回测所需的 `digest.json`。

## 硬约束

1. 每条新闻必须附原始链接
2. 不删除任何新闻——即使存疑也保留并标记
3. 不做投资建议，只呈现事实和重要性判断
4. 不做深度分析（invest-analysis 职责）
5. 空结果也要报告："今日关注清单中的标的无重要更新"
6. 可由 cron 在 invest-news + invest-ingest 后自动触发
7. **数据契约**：所有简报必须配对生成 `digest.json`，包含 coverage 和 confidence 指标。
