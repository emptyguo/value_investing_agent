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

## 执行步骤

1. 读取 `references/digest-template.md` 获取排序规则、核实等级和输出模板
2. 从 SOUL.md 的 Active Watchlist 确定今日关注的公司列表
3. 对每家公司收集：个股新闻 + 竞品新闻（companies.json 的 competitors）+ 行业新闻（industry_keywords）
4. 多源交叉验证：同一事件是否有 ≥2 个独立信源？标记核实等级
5. 按高/中/低重要性排序，SOUL.md 锚点相关的新闻提升优先级
6. 按公司分组输出简报

## 输出位置

- **主要输出**：直接在对话中呈现给用户
- **存档**：写入 `memory/YYYY-MM-DD.md`，标题为 `## 每日简报`
- **机器可读清单**：同步生成 `digest.json`（v1.0 架构），由 `scripts/generate_digest.py` 强制执行，用于自动化回测。

## 硬约束

1. 每条新闻必须附原始链接
2. 不删除任何新闻——即使存疑也保留并标记
3. 不做投资建议，只呈现事实和重要性判断
4. 不做深度分析（invest-analysis 职责）
5. 空结果也要报告："今日关注清单中的标的无重要更新"
6. 可由 cron 在 invest-news + invest-ingest 后自动触发
7. **数据契约**：所有简报必须配对生成 `digest.json`，包含 coverage 和 confidence 指标。
