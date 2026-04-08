---
name: invest-analysis
description: 基于用户个人投资认知，综合多种数据源对公司进行深度定性与定量分析，更新 views/
---

# Invest Analysis Skill

## 核心职责

个人化深度分析技能。将用户的投资认知（SOUL.md）与多种数据源结合，形成有判断力的分析。
同样一份年报，不同用户的 Agent 应产出不同侧重的分析。

## 数据源（按信息质量排序）

| 数据源 | 路径 | 可信度 |
|---|---|---|
| 年报/季报/公告 | `{OPENCLAW_DATA_DIR}/companies/{co}/filings/` | L1 最高 |
| 业绩会/路演 | `{OPENCLAW_DATA_DIR}/companies/{co}/transcripts/` | L2 高 |
| 卖方研报 | `{OPENCLAW_DATA_DIR}/companies/{co}/sellside/` | L3 中 |
| 专家访谈/渠道调研 | `{OPENCLAW_DATA_DIR}/companies/{co}/primary/` | L4 因源而异 |
| 传闻/内部信息 | `{OPENCLAW_DATA_DIR}/companies/{co}/unofficial/` | L5 低 |
| 新闻 | `{OPENCLAW_DATA_DIR}/companies/{co}/news/` | L6 需核实 |
| 行业认知 | `domains/{domain}.md` | 背景 |
| 历史判断 | `views/{company}.md` | 对照 |
| 投资原则 | `SOUL.md` | 框架 |

未解析的 PDF 先调用 `invest-pdf-parser` 再读取。

## 执行步骤

1. 读取 `SOUL.md` 确定分析方向和标准
2. 读取 `references/analysis-dimensions.md` 获取定性/定量分析维度参考
3. **本地优先**收集证据：先读 `{OPENCLAW_DATA_DIR}/companies/{co}/` 下的本地资料（L1→L6），本地无资料或资料不足时才联网搜索补充
4. 根据 SOUL.md 侧重选择性深入相关维度
5. 写入 `views/{company}.md`（参考 `references/analysis-template.md` 的结构）

## 输出必含项

1. **当前观点**：一句话结论（看多/看空/中立 + 核心理由）
2. **关键判断与证据**：每个判断引用具体数据源
3. **与上次分析的对比**：哪些判断被证实/需修正
4. **风险与证伪条件**：什么情况下当前判断被推翻
5. **待验证事项**：open questions
6. **更新记录**：`[YYYY-MM-DD] 触发原因和核心结论`

## 认知沉淀

分析中发现可复用的投资认知（不限当前公司），记录到 `memory/YYYY-MM-DD.md`。
某认知多次验证后，提议沉淀到 `SOUL.md`（需用户确认）或 `domains/`（行业共识直接写）。

## 硬约束

1. 分析必须锚定 SOUL.md（为空时用通用框架并标注"尚未形成个性化原则"）
2. 事实与观点严格分离
3. 信息不足时标注"信息不足，暂缓判断"，不凑结论
4. 不抓新闻（invest-news 职责）、不改 SOUL.md（需 invest-review + 用户确认）
5. 不做买卖建议，只提供分析框架和证据梳理
