# Value Investing Digital Twin System

## 项目概述

价值投资数字分身系统 — 基于 OpenClaw 原生架构的多 Agent 投资助手。

## 真相来源

- **线上服务器配置**：以根目录 `openclaw.json` 为准（Agent 身份、路由、Feishu 账号、技能注册）
- **架构设计方案**：以 `docs/` 为准
- `reflective.md` 仅作为历史参考，不作为当前实现依据

## Agent 总览

| Agent ID | 名称 | 用途 | Workspace |
|---|---|---|---|
| `assistant` | 龙虾小助手 | 个人主体通用助手，可调度子 agent | `/root/.openclaw/workspace` |
| `mifeng_corporate_hub` | 觅风中枢龙虾 | 公司主体中枢 Agent，飞书文档同步，未来调度 value_* | `.../agents/mifeng_corporate_hub` |
| `value_guo` | 郭沛英的分身 | 价值投资分身 | `.../agents/value_guo` |
| `value_tianxiong` | 天雄的分身 | 价值投资分身 | `.../agents/value_tianxiong` |
| `value_qingfeng` | 清风的分身 | 价值投资分身 | `.../agents/value_qingfeng` |
| `value_weichao` | 惟超的分身 | 价值投资分身 | `.../agents/value_weichao` |
| `value_liaobin` | 廖斌的分身 | 价值投资分身 | `.../agents/value_liaobin` |

## 目录结构

```text
├── templates/              # 通用模板（可重复覆盖）
│   ├── AGENTS.md           # 行为契约
│   ├── SOUL.md             # 投资灵魂（模板）
│   ├── USER.md             # 用户信息（模板）
│   ├── IDENTITY.md         # Agent 身份（模板）
│   ├── TOOLS.md            # 工具规范
│   ├── HEARTBEAT.md        # 心跳自检
│   ├── domains/            # 行业模板
│   ├── views/              # 个股视图模板
│   └── skills/             # skills/ 的导出副本（rsync 同步，勿直接编辑）
├── skills/                 # 标准化无状态 Skill（唯一编辑入口）
│   ├── invest-news/        # 新闻采集（公共）
│   ├── invest-ingest/      # 新闻分流到公司目录（公共）
│   ├── invest-doc-router/  # 文档归档（公共）
│   ├── invest-pdf-parser/  # PDF 高保真解析（公共）
│   ├── invest-lark-cli/    # 飞书文档同步（公共，仅 mifeng_corporate_hub）
│   ├── invest-digest/      # 每日新闻简报（个人）
│   ├── invest-analysis/    # 深度定性定量分析（个人）
│   ├── invest-review/      # 原则复核（个人）
│   └── invest-focus/       # 公司主题切换（个人）
├── workspace_data/         # 本地参考数据（部署时同步到服务器）
│   └── references/         # companies.json, doc_types.json
├── docs/                   # 文档
│   ├── deploy.md           # 部署指南
│   └── architecture.md     # 架构决策记录
└── openclaw.json    # 线上服务器配置（唯一真相来源）
```

## 核心架构原则

1. **Skill-Agent 严格分离**：Skill 不存储状态，Agent workspace 不包含业务逻辑
2. **幂等部署**：部署步骤可安全重复执行（见 `docs/deploy.md`）
3. **个人数据不覆盖**：SOUL.md、views/、memory/ 仅首次写入
4. **共享 vs 个人**：公共数据存 `~/.openclaw/workspace/data/`，个人判断存各 agent workspace
5. **SKILL.md 精简原则**：SKILL.md 只保留执行步骤和硬约束（≤80行），参考数据（目录树、检查清单、输出模板、JSON schema）移到 `references/` 子目录，Agent 在执行步骤中按需读取

## 部署

参见 [docs/deploy.md](docs/deploy.md)

## Skill 注册策略

技能按对话流需求注册，可重叠。数据隔离靠路径（公共 → `data/`，个人 → `agents/{id}/`），不靠技能注册：

```
assistant:              invest-news, invest-ingest, invest-doc-router, invest-pdf-parser, invest-lark-cli
mifeng_corporate_hub:   invest-news, invest-ingest, invest-doc-router, invest-pdf-parser,
                        invest-lark-cli, invest-digest, invest-analysis, invest-review
value_* agents:         invest-news, invest-ingest, invest-doc-router, invest-pdf-parser,
                        invest-lark-cli, invest-digest, invest-analysis, invest-review
```

注意：

- `companies.json` 只有 assistant 可直接编辑（防并发），value_* 发现新竞品时记录到 memory/ 并建议 assistant 更新。
- `invest-lark-cli` 已注册到所有 agent（assistant / mifeng_corporate_hub / value_*），用于飞书云文档同步与单文件上传。下载流水线（stages/01-04）仍以 `mifeng_corporate_hub` 为常规执行方；其他 agent 主要使用 `lark_upload.py` 上传产物。
- `invest-focus` 注册到 `mifeng_corporate_hub` 和所有 `value_*`，不注册到 `assistant`。
- **路由约束**：任何 agent 需要"上传文件到飞书"时，必须使用 `invest-lark-cli` 的 `lark_upload.py`，禁止调用 `feishu_upload_*` / `feishu_drive_*` 等 OpenClaw 原生工具。

## Skill 边界

| Skill | 性质 | 读取 | 写入 | 不碰 |
| --- | --- | --- | --- | --- |
| invest-news | 公共 | `companies.json` | `data/news/raw/` | `data/companies/`, `views/` |
| invest-ingest | 公共 | `data/news/raw/` | `data/companies/{co}/news/raw/`, `news/notes/` | `views/`, `SOUL.md` |
| invest-doc-router | 公共 | 用户上传 | `data/companies/{co}/` | `news/raw/`, `views/` |
| invest-pdf-parser | 公共 | PDF 文件 | 同目录生成 `.md` | 不做内容分析 |
| invest-lark-cli | 公共 | `companies.json`, `doc_types.json`, 飞书 API | `{workspace}/lark_sync/`（staging/state/logs）, `data/companies/{co}/`（阶段 4 落盘）, `data/industry/unclassified/lark/` | `views/`, `SOUL.md`, 不自动扩容 `companies.json` |
| invest-digest | 个人 | `data/news/raw/`, `data/companies/`, `SOUL.md`, `domains/` | `memory/` | `views/`, `SOUL.md`（不改） |
| invest-analysis | 个人 | `data/companies/`, `views/`, `SOUL.md`, `domains/` | `views/` | `SOUL.md`, `news/raw/` |
| invest-review | 个人 | `SOUL.md`, `views/`, `MEMORY.md` | 输出报告 | **不自动改 SOUL.md** |
| invest-focus | 个人 | `views/`, `domains/` | `views/`, `memory/` | `SOUL.md`, `data/` |

## 技能全景图 (Skill Panorama)

```
                         ┌──────────────────────────┐
                         │    invest-meeting         │  P3 · 规划中
                         │   （多Agent会议/辩论）      │
                         └────────────┬─────────────┘
                                      │ 调度各 value_* agent
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
      ┌──────────┴──────────┐ ┌──────┴──────┐ ┌──────────┴──────────┐
      │ invest-analysis     │ │ invest-     │ │ invest-financial-   │
      │ (定性+综合分析)      │ │ challenger  │ │ model               │
      │ ✅ 已实现·优化中     │ │ (认知挑战)   │ │ (财务建模/预测)       │
      └──────────┬──────────┘ │ P2 · 规划中  │ │ P1 · 规划中          │
                 │            └──────┬──────┘ └──────────┬──────────┘
                 │                   │                    │
                 │            共同读取 domains/            │
                 │                   │                    │
      ┌──────────┴───────────────────┴────────────────────┘
      │
      │  ┌─────────────────────────────────────────────────────┐
      ├──│ domains/*.md  ←  invest-cognitive-framework          │
      │  │ (思维框架/心智模型：芒格、格雷厄姆...)                  │
      │  │ P0 · 规划中（地基级，优先实施）                        │
      │  └─────────────────────────────────────────────────────┘
      │
      │  ┌─────────────────────────────────────────────────────┐
      ├──│ invest-digest   ✅ 已实现·优化中                      │
      │  │ (每日新闻简报：筛选/核实/排序)                          │
      │  └─────────────────────────────────────────────────────┘
      │
      ├── invest-review    ✅ 已实现·优化中 (原则复核)
      │
      └── SOUL.md + views/{company}.md + memory/
                 ↑ 数据来源
      ┌──────────┴─────────────────────────────────────────────┐
      │                   数据采集与归档层                        │
      │                                                         │
      │  invest-news ──→ data/news/raw/     ✅ 已实现·优化中     │
      │       ↓                                                 │
      │  invest-ingest ──→ companies/{co}/news/  ✅ 已实现·优化中│
      │                                                         │
      │  invest-doc-router ──→ companies/{co}/{type}/  ✅ 已实现 │
      │       ↓ (PDF时自动触发)                                  │
      │  invest-pdf-parser ──→ 同目录 .md          ✅ 已实现·可用│
      │                                                         │
      │  invest-lark-cli ──→ 飞书文档 → 四阶段归档   ✅ 已实现  │
      │  （仅 mifeng_corporate_hub，多文件约束 Pipeline）        │
      └─────────────────────────────────────────────────────────┘
```

### 现有技能状态

| Skill | 层级 | 状态 | 注册到 openclaw.json | 脚本 | references/ |
| --- | --- | --- | --- | --- | --- |
| `invest-pdf-parser` | 数据采集 | ✅ 可部署 | 是（assistant + value_*） | `parse_pdf.py` ✅ | — |
| `invest-news` | 数据采集 | ✅ 可部署 | 是（assistant + value_*） | `fetch_news.py` + `update_radar.py` ✅ | `news-schema.md` |
| `invest-ingest` | 数据采集 | ✅ 可部署 | 是（assistant + value_*） | `ingest_news_to_companies.py` ✅ | — |
| `invest-doc-router` | 数据采集 | ✅ 可部署 | 是（assistant + value_*） | `route_company_doc.py` ✅ | `archive-structure.md` |
| `invest-lark-cli` | 数据采集 | ✅ 可部署 | 是（mifeng_corporate_hub） | `lark_inventory.py` + `lark_download.py` + `agent_stage3.py` + `agent_stage4.py` + `verify_stage.py` | `lark-states.md` |
| `invest-digest` | 个人分析 | ✅ 可部署 | 是（value_*） | 纯 Prompt | `digest-template.md` |
| `invest-analysis` | 个人分析 | ✅ 可部署 | 是（value_*） | 纯 Prompt | `analysis-dimensions.md`, `analysis-template.md` |
| `invest-review` | 个人分析 | ✅ 可部署 | 是（value_*） | 纯 Prompt | `review-checklist.md` |
| `invest-focus` | 个人分析 | ✅ 可部署 | 是（mifeng + value_*） | 纯 Prompt | — |

### 规划技能

| Skill | 层级 | 优先级 | 说明 | 依赖 |
|---|---|---|---|---|
| `invest-cognitive-framework` | 认知地基 | **P0** | 从投资经典中提取思维模型，沉淀到 `domains/*.md` | 无，最先实施 |
| `invest-financial-model` | 定量分析 | **P1** | 财报拆分、增长预测、DCF 估值，维护 `companies/{co}/models/` | invest-pdf-parser |
| `invest-challenger` | 认知质疑 | **P2** | 基于 domains/ 的思维框架做反向质疑（每个 Agent 自身能力，非独立角色） | invest-cognitive-framework |
| `invest-meeting` | 多 Agent 协同 | **P3** | 主持人选题 → 各分身发言 → 会议纪要 → 分歧记录 → 人工纠偏 | 前三个技能成熟后 |

### 规划技能详细说明

**`invest-cognitive-framework`（P0 地基）**

每位知名投资人的认知体系独立提炼、独立存储，保持原汁原味，与用户个人无关：

```
data/books/
├── buffett/            # 巴菲特：护城河、能力圈、安全边际、所有者盈余...
│   ├── source/         # 原书/原文 PDF → md
│   └── framework.md    # 提炼后的结构化思维模型
├── munger/             # 芒格：多元思维模型、反转思维、检查清单...
│   ├── source/
│   └── framework.md
├── duan_yongping/      # 段永平：商业模式、不做什么、差异化...
│   ├── source/
│   └── framework.md
└── graham/             # 格雷厄姆：安全边际、内在价值、市场先生...
    ├── source/
    └── framework.md
```

- 输入：投资经典书籍（`data/books/{master}/source/`）
- 输出：每位大师独立的 `framework.md`（结构化思维模型）
- 定位：**公共数据**，不归属任何特定 agent，所有 value_* 和 assistant 均可读取
- 与 SOUL.md 的关系：`framework.md` 是客观提炼的"大师原始思想"，`SOUL.md` 是用户个人的投资哲学——用户可以选择性吸收多位大师的框架组合成自己的信仰体系
- 被 `invest-analysis`、`invest-challenger` 共同读取

**`invest-financial-model`（P1 定量引擎）**

- 输入：`companies/{co}/filings/` 中的年报/季报（经 pdf-parser 解析）
- 输出：`companies/{co}/models/financial_model.json`（持久化财务模型）
- 能力：财报拆分、关键指标趋势、增长预测、估值计算
- 特点：可追溯的"预测 vs 实际"对比

**`invest-challenger`（P2 反向质疑）**

- 输入：`views/{company}.md` + `data/books/{master}/framework.md`
- 输出：质疑报告（融入对话或会议）
- 能力：反转思维、换角度思考、同业/异业对比、质疑本质问题
- 定位：每个 value_* Agent 的自身能力，不是独立角色；基于学到的大师认知框架进行反向质疑

**`invest-meeting`（P3 皇冠）**

- 主持人（assistant）选题确认 → 各 value_* 发言 → 各自用 challenger 自我攻击 → 会议纪要
- 输出：`data/meetings/YYYY-MM-DD-{company}.md`
- 记录：共识、分歧、待验证事项、人工纠偏结果

### 部署

飞书云文档定时任务

```
openclaw cron add \
  --name "飞书文档同步" \
  --cron "0 8-20/1 * * *" \
  --tz "Asia/Shanghai" \
  --session isolated \
  --message "【流水线指令】
    1. 请使用技能 invest-lark-cli，不要将其视为系统程序，务必遵循技能中的SKILL.md 的规则。
    2. 按照技能中的流程进行分步骤执行，不要跳步，不要遗漏任何步骤。如果失败请及时发送消息通知" \
  --agent mifeng_corporate_hub \
  --announce \
  --channel feishu \
  --to "user:ou_cbcd3ee3f57877285dfa8e80f1ad066e"
```

```
openclaw cron add   --name "新闻抓取"   --cron "0 8-20/5 * * *"   --tz "Asia/Shanghai"   --session isolated   --message "【流水线指令】1. 请使用技能 invest-news，不要将其视为系统程序，务必遵循技能中的SKILL.md 的规则。 2. 按照技能中的流程进行分步骤执行，不要跳步，不要遗漏任何步骤。如果失败请及时发送消息通知"   --agent mifeng_corporate_hub   --announce   --channel feishu   --to "user:ou_cbcd3ee3f57877285dfa8e80f1ad066e"
```

```
openclaw cron add   --name "新闻归档"   --cron "20 8-20/5 * * *"   --tz "Asia/Shanghai"   --session isolated   --message "【流水线指令】1. 请使用技能 invest-ingest，不要将其视为系统程序，务必遵循技能中的SKILL.md 的规则。 2. 按照技能中的流程进行分步骤执行，不要跳步，不要遗漏任何步骤。如果失败请及时发送消息通知"   --agent mifeng_corporate_hub   --announce   --channel feishu   --to "user:ou_cbcd3ee3f57877285dfa8e80f1ad066e"
```
