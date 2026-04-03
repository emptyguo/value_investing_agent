---
name: invest-doc-router
description: 当用户上传公司相关文件或链接时，按公司、文档类型和可信度归档到公司资料库
---

# Invest Doc Router Skill

## 核心职责

`invest-doc-router` 是归档技能，负责将用户上传的外部文件/链接统一归档到公司资料库。

**只做**：归档、分类、标记可信度、记录时间线
**绝不做**：分析、评价、产出投资结论

## 关键路径

| 用途 | 路径 |
|---|---|
| 公司配置 | `~/.openclaw/workspace/data/references/companies.json` |
| 分类配置 | `~/.openclaw/workspace/data/references/doc_types.json` |
| 公司资料库 | `~/.openclaw/workspace/data/companies/{company}/` |

## 路径构造规则（强制）

所有落盘路径**必须**按以下公式构造，**禁止自行拼接或使用中文目录名**：

```
{DATA_ROOT}/companies/{company}/{doc_types.json 中的 dir 字段}/source/{filename}   ← 源文件
{DATA_ROOT}/companies/{company}/{doc_types.json 中的 dir 字段}/{filename}.md        ← 解析后内容
```

其中：
- `{DATA_ROOT}` = `~/.openclaw/workspace/data`
- `{company}` = `companies.json` 中的 `id` 字段（英文小写）
- `{dir}` = `doc_types.json` 中匹配条目的 `dir` 字段（如 `sellside/briefings`、`filings/annual`）
- 目录名**全部使用英文**，由 `doc_types.json` 的 `dir` 字段决定，**严禁使用 label 中文名替代**

### 路径示例

| 输入 | doc_type | 源文件落盘路径 | 解析后路径 |
|---|---|---|---|
| `tme_4q25.pdf`，简报 | `briefings` | `data/companies/tme/sellside/briefings/source/tme_4q25.pdf` | `data/companies/tme/sellside/briefings/tme_4q25.md` |
| `腾讯2025年报.pdf` | `annual` | `data/companies/tencent/filings/annual/source/腾讯2025年报.pdf` | `data/companies/tencent/filings/annual/腾讯2025年报.md` |
| 业绩会纪要链接 | `earnings_calls` | N/A（link 类型无源文件） | `data/companies/tencent/transcripts/earnings_calls/20260401_earnings_call.json` |

## 公司资料库结构

按**信息可信度从高到低**组织，每个分类目录下设 `source/` 子目录存放源文件：

```
data/companies/{company}/
├── filings/              # 官方披露（可信度：最高）
│   ├── prospectus/       # 招股书
│   │   ├── source/       # 源文件（PDF/Word/Excel/PPT）
│   │   └── *.md          # 解析后的 markdown
│   ├── annual/           # 年报
│   │   ├── source/
│   │   └── *.md
│   ├── quarterly/        # 季报、中报
│   │   ├── source/
│   │   └── *.md
│   └── announcements/    # 公告
│       ├── source/
│       └── *.md
│
├── transcripts/          # 官方交流记录（可信度：高）
│   ├── earnings_calls/   # 业绩说明会、电话会议
│   │   ├── source/
│   │   └── *.md
│   ├── meeting_minutes/  # 会议纪要
│   │   ├── source/
│   │   └── *.md
│   └── roadshows/        # 路演、投资者日
│       ├── source/
│       └── *.md
│
├── sellside/             # 卖方研究（可信度：中，有利益偏差）
│   ├── briefings/        # 简报
│   │   ├── source/
│   │   └── *.md
│   ├── initiation/       # 首次覆盖
│   │   ├── source/
│   │   └── *.md
│   ├── update/           # 跟踪更新
│   │   ├── source/
│   │   └── *.md
│   └── industry/         # 行业报告（涉及该公司）
│       ├── source/
│       └── *.md
│
├── primary/              # 一手调研（可信度：因来源而异）
│   ├── expert_calls/     # 行业专家访谈
│   │   ├── source/
│   │   └── *.md
│   ├── channel_checks/   # 渠道调研
│   │   ├── source/
│   │   └── *.md
│   └── site_visits/      # 实地调研
│       ├── source/
│       └── *.md
│
├── unofficial/           # 非公开信息（可信度：低，需交叉验证）
│   ├── rumors/           # 小道消息、市场传闻
│   │   ├── source/
│   │   └── *.md
│   └── internal/         # 内部人士透露
│       ├── source/
│       └── *.md
│
├── news/                 # 新闻（由 invest-ingest 自动写入）
│   ├── raw/              # 原始新闻
│   └── notes/            # 结构化笔记
│
├── timeline.md           # 时间线（所有归档操作记录）
└── intake_log.jsonl      # 路由日志
```

## 可信度体系

每份归档资料自动标记可信度等级：

| 等级 | 目录 | 说明 | 分析时的使用规则 |
|---|---|---|---|
| L1 官方披露 | `filings/` | 公司依法向监管机构提交的材料 | 可直接作为事实引用 |
| L2 官方交流 | `transcripts/` | 管理层公开发言 | 注意区分事实陈述与展望承诺 |
| L3 卖方研究 | `sellside/` | 券商/卖方报告 | 重数据轻结论，注意利益偏差 |
| L4 一手调研 | `primary/` | 专家访谈、渠道调研 | 有参考价值，需交叉验证 |
| L5 非公开 | `unofficial/` | 传闻、小道消息 | 仅作为线索，不可直接作为判断依据 |
| L6 新闻 | `news/` | 媒体报道 | 需核实信源，注意时效性 |

## 输入

- `company`: 公司标识（必须在 `companies.json` 中存在）
- `type`: `file` / `link` / `text`
- `doc_type`: 见下方分类表，或 `auto`（自动识别）
- `title`: 文档标题
- `file-path`（type=file 时）
- `url`（type=link 时）
- `credibility_note`（可选）：对来源可信度的补充说明

## 自动分类规则

`doc_type=auto` 时，读取 `~/.openclaw/workspace/data/references/doc_types.json` 获取分类规则：

1. 遍历 `doc_types` 数组中每条规则的 `keywords` 字段
2. 用文档标题和内容匹配关键词
3. 命中则归入该规则的 `dir` 目录，标记对应的 `credibility` 等级
4. 无法匹配时，使用 `default_doc_type` 指定的默认分类

## 归档流程（type=file）

1. 根据分类规则确定 `doc_type`，从 `doc_types.json` 获取 `dir` 字段
2. **复制源文件**到 `data/companies/{company}/{dir}/source/{原始文件名}`
3. **如果是 PDF**：调用 `invest-pdf-parser`，输入为 `source/{文件名}`，输出 `.md` 到 `data/companies/{company}/{dir}/{文件名}.md`
4. **如果是非 PDF 可解析文件**（Word/PPT/Excel）：按相同规则存储源文件，解析能力视工具可用性决定
5. 在 `timeline.md` 追加归档记录（含可信度等级、源文件路径、解析文件路径）
6. 在 `intake_log.jsonl` 记录路由日志

## 归档流程（type=link/text）

1. 根据分类规则确定 `doc_type`
2. 写结构化 `.json` 记录到 `data/companies/{company}/{dir}/`
3. 更新 `timeline.md` 和 `intake_log.jsonl`

## 执行方式

### 交互模式（用户对话中触发）

Agent 按照本文档指令直接执行：读取 doc_types.json 分类，复制文件到对应目录，更新 timeline.md 和 intake_log.jsonl。

### 批量模式（脚本备用）

```bash
python3 {baseDir}/scripts/route_company_doc.py \
  --company tencent \
  --type file \
  --title "腾讯2025年报" \
  --file-path "/abs/path/tencent_2025_annual_report.pdf" \
  --doc-type auto
```

## 执行规则

- **路径必须由 doc_types.json 的 dir 字段决定，严禁使用中文目录名**
- **源文件必须保留在 source/ 子目录，不可丢弃**
- **只归档，不分析**
- **只记录，不写投资结论**
- **保留原始格式，不篡改源文件**
- **PDF 文件归档后自动触发解析**
- **非公开信息必须标记来源和可信度说明**
