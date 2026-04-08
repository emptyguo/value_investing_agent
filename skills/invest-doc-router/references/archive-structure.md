# 公司资料库结构与可信度体系

## 目录结构

按信息可信度从高到低组织，每个分类目录下设 `source/` 子目录存放源文件：

```
{OPENCLAW_DATA_DIR}/companies/{company}/
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

## 路径示例

| 输入 | doc_type | 源文件落盘路径 | 解析后路径 |
|---|---|---|---|
| `tme_4q25.pdf`，简报 | `briefings` | `{OPENCLAW_DATA_DIR}/companies/tme/sellside/briefings/source/tme_4q25.pdf` | `{OPENCLAW_DATA_DIR}/companies/tme/sellside/briefings/tme_4q25.md` |
| `腾讯2025年报.pdf` | `annual` | `{OPENCLAW_DATA_DIR}/companies/tencent/filings/annual/source/腾讯2025年报.pdf` | `{OPENCLAW_DATA_DIR}/companies/tencent/filings/annual/腾讯2025年报.md` |
| 业绩会纪要链接 | `earnings_calls` | N/A（link 类型无源文件） | `{OPENCLAW_DATA_DIR}/companies/tencent/transcripts/earnings_calls/20260401_earnings_call.json` |
