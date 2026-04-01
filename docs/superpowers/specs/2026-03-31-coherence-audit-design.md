# 价值投资数字分身系统 — 逻辑自洽审计与修正方案

> 审计日期：2026-03-31
> 状态：已执行

---

## 一、审计背景

本文档对整个项目进行了一次系统性的逻辑自洽审计，覆盖了从执行模型基础假设到具体文件间一致性的全链条检查。

### 已确认的基础前提

| 前提 | 结论 | 来源 |
|---|---|---|
| Skill 执行模型 | Skill = prompt 指令集 + 可调用脚本，注入 Agent（Gemini 3.1）上下文执行 | 用户确认 |
| 脚本调用能力 | OpenClaw 可以调用 Skill 目录下的 Python 脚本 | 用户确认 |
| 文件访问范围 | Workspace 是默认 cwd 但非硬性沙箱，绝对路径可用 | OpenClaw 文档 |
| 数据归属原则 | 公司资料 = 公共，个人认知 = 私有 | 用户确认 |

---

## 二、发现的矛盾与修正方案

### 矛盾 1：7 个 invest-* skill 中 6 个未注册到任何 agent

**现状**：

`openclaw.json` 中各 agent 实际注册的 skills：

| Agent | 实际注册的 skills |
|---|---|
| assistant | ontology, self-improving-agent, gateway, feishu_doc, feishu_chat, feishu_calendar, **invest-pdf-parser** |
| fa-tuoshui | fa-intelligence, **invest-pdf-parser** |
| value_* (4个) | ontology, self-improving-agent, feishu_doc, **invest-pdf-parser** |

**只有 invest-pdf-parser 注册了。** invest-news、invest-ingest、invest-doc-router、invest-digest、invest-analysis、invest-review 全部未注册到任何 agent——包括 assistant。

AGENTS.md（108-141 行）已经完整定义了场景 A/B/C 的对话工作流和执行连招，workflow 本身的设计是清晰的。**真正的问题是：workflow 引用的 skill 未注册到执行它的 agent。** CLAUDE.md 也计划了注册策略，但线上配置与计划脱节。

另外值得确认的是：AGENTS.md:128 和 invest-doc-router/SKILL.md:40 已经统一使用 `unofficial/` 路径（而非旧的 `notes/`），这部分路径口径是一致的，无需再改。

**根因**：
1. skills 仍在"优化中"，尚未注册是预期的——但文档没有体现这个过渡状态
2. 计划的注册策略把"公共 vs 个人"画在了"技能注册"上，实际应该画在"数据存储位置"上

**修正方案**：

技能注册应按"谁的对话流需要这个能力"来决定，不按"公共/个人"分类。

修正后的注册策略：

```
assistant:
  - invest-news          # cron 自动采集
  - invest-ingest        # cron 自动分流
  - invest-doc-router    # assistant 也可能收到文件
  - invest-pdf-parser    # 通用能力

value_* agents:
  - invest-doc-router    # 用户直接发文件给 value agent
  - invest-pdf-parser    # 分析时按需解析 PDF
  - invest-digest        # 每日个性化简报
  - invest-analysis      # 深度分析（读 SOUL.md）
  - invest-review        # 原则复核（读 SOUL.md）
```

**修改涉及**：
- [x] `openclaw.json` — assistant 添加 invest-news、invest-ingest、invest-doc-router；value_* 添加 invest-doc-router，以及后续就绪的 invest-digest / invest-analysis / invest-review
- [x] `CLAUDE.md` — 更新 Skill 分层与注册策略表
- [x] `templates/TOOLS.md` — 更新技能注册表，去掉"公共技能 / 个人技能"的分类标签，改为按功能分组

**需要决策**：
- invest-news 和 invest-ingest 是否也注册到 value_*？目前它们是 cron 触发的批量任务，value_* 在对话中不需要主动调用。如果不注册，当用户跟 value_guo 说"帮我搜一下腾讯最新新闻"时，value_guo 没有 invest-news 的指令。
  - 选项 A：不注册，value_guo 用自身 web search 能力搜索，不走 invest-news 的标准化流程
  - 选项 B：也注册，让 value_guo 可以按 invest-news 的格式落盘
  - 建议：选项 B，保持数据格式一致性。但需注意并发写入风险（见矛盾 6）

---

### 矛盾 2：分类逻辑三源并存

**现状**：invest-doc-router 的文件分类规则同时存在于三个地方：

| 位置 | 内容 | 何时被读取 |
|---|---|---|
| `skills/invest-doc-router/SKILL.md` 第 88-101 行 | 硬编码的关键词 → 目录映射表 | Agent 执行 skill 时（作为 prompt 读入） |
| `workspace_data/references/doc_types.json` | 13 条分类规则（含 keywords、credibility） | Python 脚本执行时 |
| `skills/invest-doc-router/scripts/route_company_doc.py` | `auto_classify()` 函数读取 doc_types.json | 脚本被调用时 |

**问题**：
- Agent 读到的是 SKILL.md 里的硬编码表，不会去看 doc_types.json
- 如果修改 doc_types.json 但不更新 SKILL.md，Agent 行为与脚本行为不一致
- 三处维护成本高，容易不同步

**修正方案**：

**doc_types.json 为唯一真相源。**

- SKILL.md 中删除硬编码分类表，改为指令：
  > "读取 `~/.openclaw/workspace/data/references/doc_types.json` 获取分类规则。按 keywords 字段匹配，归入对应 dir 目录。无法匹配时使用 default_doc_type。"
- Python 脚本保留，作为 cron/批量场景的执行工具，也读 doc_types.json
- 新增/修改分类规则只需改 doc_types.json 一个文件

**修改涉及**：
- [x] `skills/invest-doc-router/SKILL.md` — 删除硬编码表，引用 doc_types.json
- [x] 确认 doc_types.json 当前内容与 SKILL.md 硬编码表一致（避免引入 gap）

---

### 矛盾 3：companies.json 部署会覆盖自我进化数据

**现状**：
- `deploy.md` 第 54 行：`cp workspace_data/references/companies.json ~/.openclaw/workspace/data/references/`
- 这是无条件覆盖
- 但 invest-news 的"自我进化雷达"会在服务器上编辑 companies.json（增加新竞品、关键词等）
- 重新部署 → 进化数据全丢

**修正方案**：

将 `companies.json` 与 `doc_types.json` 分开处理：

- `doc_types.json` 是公共分类规则，**每次部署覆盖**
- `companies.json` 是可演化的实体配置，**部署时合并，不直接覆盖**

`companies.json` 的建议合并规则：

- 仓库权威字段：`id`、`name`、`symbol`、`market`
- 线上保留字段：`aliases`、`brands`、`competitors`、`industry_keywords`、`enabled_sources`、`schedule_profile`

这样可以同时满足两件事：

1. 手动在仓库里新增公司时，部署能把新公司补到线上
2. 线上运行中积累出来的雷达字段不会因重新部署而丢失

deploy.md 幂等规则表增加一行：

| 文件类型 | 文件 | 部署策略 |
|---|---|---|
| Template | AGENTS.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md | 每次覆盖 |
| Personal | SOUL.md, USER.md | 仅首次写入，已有跳过 |
| **Rule** | **doc_types.json** | **每次覆盖** |
| **Evolving Reference** | **companies.json** | **合并，不直接覆盖** |
| Runtime | views/, memory/, MEMORY.md | 绝不覆盖 |
| Merged | domains/*.md | 添加新文件，不覆盖已有 |

**额外考虑**：

- `doc_types.json` 的变化应通过修改仓库并重新部署完成，不应在服务器上手改漂移
- `companies.json` 不适合“首次写入后永不更新”，否则后续在仓库里新增公司无法同步到线上

**修改涉及**：
- [x] `docs/deploy.md` — 将 `doc_types.json` 定义为 Rule（每次覆盖），将 `companies.json` 定义为 Evolving Reference（合并）
- [x] `CLAUDE.md` — 如有幂等规则描述也同步

---

### 矛盾 4：Python 脚本与 Agent 原生能力边界模糊

**现状**：

| 脚本 | Agent 原生能否做 | 脚本存在的意义 |
|---|---|---|
| `parse_pdf.py` | 不能（需要 opendataloader-pdf） | **必须保留** |
| `fetch_news.py` | 能（Gemini 内置 Google Search） | AkShare 备用方案 |
| `ingest_news_to_companies.py` | 能（读 JSON 写文件） | 批量/cron 场景 |
| `route_company_doc.py` | 能（读配置 + 写文件） | 批量/cron 场景 |

**问题**：
- SKILL.md 中没有明确说明"交互模式用 Agent 原生能力，cron/批量模式用脚本"
- 开发者/维护者不清楚脚本和 prompt 指令的关系

**修正方案**：

在每个 SKILL.md 中明确**双模式执行**：

```markdown
## 执行方式

### 交互模式（用户对话中触发）
Agent 按照本文档指令直接执行，使用原生文件读写和搜索能力。

### 批量模式（cron 自动触发）
调用脚本执行：
\`\`\`bash
python3 {baseDir}/scripts/xxx.py --date YYYY-MM-DD
\`\`\`
```

**修改涉及**：
- [x] `skills/invest-news/SKILL.md` — 明确双模式
- [x] `skills/invest-ingest/SKILL.md` — 明确双模式
- [x] `skills/invest-doc-router/SKILL.md` — 明确双模式（doc-router 通常只在交互模式下触发，脚本作为备用）

---

### 矛盾 5（已合并入矛盾 1）

公共/个人技能分界与实际对话流不匹配 — 已在矛盾 1 中统一解决。

---

### 矛盾 6：companies.json 并发写入竞争条件

**现状**：

invest-news 的"自我进化雷达"允许 Agent 直接编辑 `companies.json`（增加新竞品、关键词）。如果按 D1 建议 B 将 invest-news 注册到所有 value_* agent，则 assistant + 4 个 value agent = **5 个 agent 可能并发写同一个 companies.json**。

**风险场景**：
1. value_guo 搜索新闻，发现腾讯音乐新竞品"某某音乐"，准备追加到 tme.competitors
2. 同时 value_tianxiong 也在搜索，发现美的新品牌，准备追加到 midea.brands
3. 两个 agent 各自读取 companies.json → 各自修改 → 各自写回 → 后写的覆盖先写的改动

**修正方案**：

| 选项 | 描述 | 优点 | 缺点 |
|---|---|---|---|
| A：只允许 assistant 写 companies.json | value_* 发现新竞品时记录到 memory/，由 assistant 统一更新 | 零并发风险 | 更新链路变长，依赖 assistant 执行 |
| B：文件锁机制 | 写入前加 `.lock` 文件，写完删除 | 直接解决并发 | Agent 可能不可靠地执行锁协议 |
| C：按公司拆分配置文件 | `companies/{co}.json` 每个公司独立文件 | 不同 agent 关注不同公司，天然避免冲突 | 改动大，所有读取 companies.json 的地方都要改 |
| D：接受风险，依赖实际并发概率低 | 不做特殊处理 | 零开发成本 | 如果真的并发了会丢数据 |

**建议**：选项 A。符合已有架构——assistant 负责公共数据维护，value_* 负责个人认知。value_* 的 SKILL.md 中将"自我进化"改为"发现新竞品/关键词时记录到 `memory/YYYY-MM-DD.md`，并建议 assistant 更新 companies.json"。

**修改涉及**：
- [x] `skills/invest-news/SKILL.md` — 如果注册到 value_*，自我进化部分改为"记录 + 建议"而非"直接编辑"
- [x] 确认 assistant 的 invest-news 保持直接编辑权限

---

## 三、跨文件一致性检查

除了上述 6 个结构性矛盾，还发现以下不一致：

### 3.1 TOOLS.md 的技能分组标签过时

**现状**：TOOLS.md 将技能分为"公共技能（由 assistant 执行）"和"个人技能（由各 value agent 执行）"两组。这个分组作为**职责说明**是合理的——它清晰表达了每个 skill 的主要执行角色。

**问题**：分组标签本身没问题，但表格中没有体现**实际注册状态**。当前线上所有 agent 只注册了 invest-pdf-parser，其他 6 个 skill 都未注册。文档给人"已部署就绪"的错觉。此外，修正矛盾 1 后 invest-doc-router 等 skill 会横跨两组（assistant 和 value_* 都注册），表格需要反映这一点。

**修正**：保留"公共/个人"的职责分组标签，但在每个 skill 行中增加"注册到"列，体现实际注册状态和目标状态：

```markdown
## Skills

### 数据采集与处理（公共职责，主要由 assistant 驱动）

| Skill | 职责 | 计划注册到 | 当前状态 | 触发方式 |
|---|---|---|---|---|
| invest-news | 联网搜索采集新闻 | assistant, value_* | 未注册 | cron / 手动 |
| invest-ingest | 新闻按公司分流 | assistant, value_* | 未注册 | cron（news 之后）|
| invest-doc-router | 文件/链接归档 | assistant, value_* | 未注册 | 用户上传触发 |
| invest-pdf-parser | PDF 转 Markdown | assistant, value_* | **已注册** | 自动/手动 |

### 分析与认知（个人职责，由各 value agent 独立执行）

| Skill | 职责 | 计划注册到 | 当前状态 | 触发方式 |
|---|---|---|---|---|
| invest-digest | 每日新闻简报 | value_* | 未注册 | cron 每日 / 手动 |
| invest-analysis | 深度定性定量分析 | value_* | 未注册 | 手动 |
| invest-review | 原则复核 | value_* | 未注册 | 手动 / 定期 |
```

**修改涉及**：
- [x] `templates/TOOLS.md` — 更新 Skills 表格，增加"计划注册到"和"当前状态"列

### 3.2 CLAUDE.md Skill 分层描述过时

**现状**：
```
assistant:        invest-news, invest-ingest, invest-doc-router, invest-pdf-parser
value_* agents:   invest-digest, invest-analysis, invest-review, invest-pdf-parser
```

**修正**：需与修正后的注册策略同步。

**修改涉及**：
- [x] `CLAUDE.md` — 更新"Skill 分层与注册策略"部分

### 3.3 AGENTS.md 对话工作流中缺少"调用 invest-news"的入口

**现状**：AGENTS.md 定义了三种场景（标准资料/非公开情报/偏好信号），但没有覆盖"用户要求搜新闻"的场景。

**如果 invest-news 注册到 value_***，需要增加场景 D：

```markdown
### 场景 D：用户要求搜索最新消息

**触发条件**：用户说"帮我搜一下XX最新消息"、"XX有什么新动态"。

**执行连招**：
1. 按 invest-news 流程搜索，落盘到 `data/news/raw/`
2. 按 invest-ingest 分流到公司目录
3. 按 invest-digest 逻辑筛选重要性，直接在对话中呈现
4. 如有冲击性信息，走场景 A 的碰撞流程
```

**修改涉及**：
- [x] `templates/AGENTS.md` — 增加场景 D

### 3.4 invest-news SKILL.md 中 fetch_news.py 仍引用 AkShare

**现状**：SKILL.md 主文说"使用 Agent 自带的 web search"，但 `scripts/fetch_news.py` 依赖 AkShare。两者定位不一致。

**修正**：在 SKILL.md 中明确 fetch_news.py 是"备用/批量模式"，且标注 AkShare 依赖需要额外安装。这与矛盾 4 的双模式方案一致。

### 3.5 invest-review SKILL.md 中引用 `shared/` 路径

**现状**：invest-review SKILL.md 第 33 行提到 "来自 views/ 或 shared/ 的支撑证据"。

**问题**：项目中不存在 `shared/` 目录，应该是 `data/companies/` 或 `domains/`。

**修改涉及**：
- [x] `skills/invest-review/SKILL.md` — 将 `shared/` 改为准确路径

---

## 四、数据流端到端验证

修正所有矛盾后，完整数据流应该是：

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据采集层                                │
│                                                                 │
│  [cron/手动] invest-news                                        │
│      │ Gemini web search / AkShare backup                       │
│      ▼                                                          │
│  data/news/raw/YYYY-MM-DD.jsonl                                 │
│      │                                                          │
│  [cron/手动] invest-ingest                                      │
│      │ 按 company 字段分流                                       │
│      ▼                                                          │
│  data/companies/{co}/news/raw/YYYY-MM-DD.jsonl                  │
│                                                                 │
│  [用户上传] invest-doc-router                                    │
│      │ 读 doc_types.json 分类，标记 L1-L5 可信度                  │
│      ▼                                                          │
│  data/companies/{co}/{filings|transcripts|sellside|...}/        │
│      │                                                          │
│  [自动] invest-pdf-parser （如果是 PDF）                          │
│      │ opendataloader-pdf → .md                                 │
│      ▼                                                          │
│  同目录生成 .md 文件                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    个人分析层（每个 value_* agent 独立）           │
│                                                                 │
│  invest-digest                                                  │
│      │ 读 news/raw + companies/ + SOUL.md                       │
│      │ 核实、排序、生成简报                                       │
│      ▼                                                          │
│  memory/YYYY-MM-DD.md（简报存档）+ 对话输出                      │
│                                                                 │
│  invest-analysis                                                │
│      │ 读 companies/{co}/ 全层 + views/ + SOUL.md + domains/    │
│      │ 定性定量分析，碰撞已有判断                                 │
│      ▼                                                          │
│  views/{company}.md（更新）+ memory/（认知沉淀）                  │
│                                                                 │
│  invest-review                                                  │
│      │ 读 SOUL.md + views/ + MEMORY.md + memory/                │
│      │ 检查原则是否需要进化                                       │
│      ▼                                                          │
│  输出复核报告 → 用户确认后才能修改 SOUL.md                        │
└─────────────────────────────────────────────────────────────────┘
```

### 数据写入权限矩阵（修正后）

| 写入目标 | invest-news | invest-ingest | invest-doc-router | invest-pdf-parser | invest-digest | invest-analysis | invest-review |
|---|---|---|---|---|---|---|---|
| `data/news/raw/` | **写** | 读 | - | - | 读 | - | - |
| `data/companies/{co}/news/` | - | **写** | - | - | 读 | 读 | - |
| `data/companies/{co}/{type}/` | - | - | **写** | **写**(.md) | - | 读 | - |
| `data/references/companies.json` | **读写**（仅 assistant） | - | 读 | - | 读 | - | - |
| `data/references/doc_types.json` | - | - | 读 | - | - | - | - |
| `views/{company}.md` | - | - | - | - | - | **写** | 读 |
| `memory/YYYY-MM-DD.md` | - | - | - | - | **写** | **写** | - |
| `SOUL.md` | - | - | - | - | - | - | **只读**（改需确认）|
| `domains/{domain}.md` | - | - | - | - | - | **写**（行业共识）| - |

---

## 五、修改清单汇总

### 优先级 P0（逻辑矛盾，不修会导致系统不可用）

| # | 修改项 | 涉及文件 | 说明 |
|---|---|---|---|
| 1 | 修正技能注册策略 | `openclaw.json` | assistant 添加 invest-news/ingest/doc-router；value_* 添加 invest-doc-router（及后续就绪的 digest/analysis/review/news/ingest） |
| 2 | SKILL.md 分类规则去重 | `skills/invest-doc-router/SKILL.md` | 删除硬编码表，引用 doc_types.json |
| 3 | companies.json 部署策略修正 | `docs/deploy.md` | 改为合并，不直接覆盖 |
| 4 | companies.json 并发写入保护 | `skills/invest-news/SKILL.md` | value_* 的自我进化改为"记录+建议"，只有 assistant 可直接编辑 |

### 优先级 P1（一致性，不修会导致混乱）

| # | 修改项 | 涉及文件 | 说明 |
|---|---|---|---|
| 5 | TOOLS.md 技能表格补全 | `templates/TOOLS.md` | 保留职责分组，增加"计划注册到"和"当前状态"列 |
| 6 | CLAUDE.md 注册策略更新 | `CLAUDE.md` | 与修正后的注册策略一致 |
| 7 | SKILL.md 双模式说明 | `invest-news/ingest/doc-router SKILL.md` | 明确交互模式 vs 批量模式 |
| 8 | invest-review 路径修正 | `skills/invest-review/SKILL.md` | `shared/` → 准确路径 |

### 优先级 P2（增强，不修不影响基本运行）

| # | 修改项 | 涉及文件 | 说明 |
|---|---|---|---|
| 9 | AGENTS.md 增加场景 D | `templates/AGENTS.md` | 用户要求搜新闻的工作流 |
| 10 | deploy.md 幂等规则补全 | `docs/deploy.md` | 增加 Reference 行 |

---

## 六、待决策事项

| # | 问题 | 选项 | 建议 |
|---|---|---|---|
| D1 | invest-news / invest-ingest 是否也注册到 value_*？ | A: 不注册 / B: 注册 | B（保持数据格式一致），但需配合矛盾 6 的并发保护 |
| D2 | doc_types.json 部署时覆盖还是保护？ | A: 仅首次 / B: merge / C: 每次覆盖 | C（不会被 Agent 修改） |
| D3 | 除 parse_pdf.py 外的 Python 脚本长期保留还是逐步废弃？ | A: 保留双模式 / B: 仅保留 parse_pdf.py | A（cron 批量场景有价值） |
| D4 | companies.json 并发写入保护策略 | A: 只允许 assistant 写 / B: 文件锁 / C: 按公司拆分 / D: 接受风险 | A（符合已有架构，assistant 管公共数据）|

---

## 七、修正前后对比

### 修正前

```
"公共技能" ──────────── assistant 独占
"个人技能" ──────────── value_* 独占
数据存在哪 ──────────── 没有显式规则
SKILL.md ────────────── 有的硬编码，有的引用配置
companies.json ──────── 每次部署覆盖（进化数据丢失）
脚本 vs Agent ────────── 边界模糊，同一件事两种做法不知道用哪个
```

### 修正后

```
技能注册 ────────────── 按对话流需求注册，可重叠（assistant 和 value_* 都需要的就都注册）
数据隔离 ────────────── 公共 → data/，个人 → agents/{id}/（显式规则）
配置真相源 ──────────── doc_types.json（唯一），SKILL.md 引用而非硬编码
companies.json ──────── 合并同步（新增公司可上线，演化字段不丢失）+ 只有 assistant 可直接编辑（防并发）
执行模式 ────────────── 交互模式（Agent 原生）/ 批量模式（Python 脚本），SKILL.md 明确标注
部署来源 ────────────── 统一 templates/，砍掉 agents/ 目录（个性化通过对话自然生长）
新增用户 ────────────── 只改 openclaw.json，无需建 agents/ 子目录
```

---

## 八、已执行的结构性变更

### 8.1 砍掉 agents/ 目录（方案 B）

**变更原因**：agents/ 目录中每人 3 个文件（IDENTITY.md、USER.md、SOUL.md），但独有信息极少：
- IDENTITY.md 的名字和 emoji 已在 openclaw.json `identity` 字段中
- USER.md 的姓名/称呼可由 Agent 首次对话时感知写入
- SOUL.md 除 value_guo 有真实数据外，其他三人 ≈ 空模板

**执行内容**：
- [x] value_guo 的 SOUL.md 已在线上服务器保留（部署策略"已有跳过"，不会被覆盖）
- [x] templates/IDENTITY.md 改为读取 openclaw.json 的 `identity.name`，移除 emoji
- [x] templates/USER.md 改为空模板，首次对话时 Agent 感知写入
- [x] deploy.md 简化为统一从 templates/ 部署，去掉 agents/ 相关步骤
- [x] deploy.md 改为 companies.json 合并策略 + doc_types.json 每次覆盖
- [x] deploy.md 幂等规则表增加 Reference 分类
- [x] CLAUDE.md 目录结构移除 agents/
- [x] 删除 agents/ 目录
