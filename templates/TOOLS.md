# 工作区工具规范 (TOOLS.md)

## 文件读写规范

- **日期格式**：所有日期采用 `YYYY-MM-DD` 格式。
- **文件编码**：UTF-8。
- **JSONL 格式**：每行一条独立 JSON 记录。

## Skills

### 数据采集与处理（公共职责，主要由 assistant 驱动）

| Skill | 职责 | 计划注册到 | 当前状态 | 触发方式 |
|---|---|---|---|---|
| `invest-news` | 联网搜索采集新闻，落盘到 news/raw/ | `assistant`, `value_*` | 已注册 | cron / 手动 |
| `invest-ingest` | 将 news/raw/ 按公司分流到 companies/ | `assistant`, `value_*` | 已注册 | cron（news 之后）/ 手动 |
| `invest-doc-router` | 归档用户上传的公司文件，PDF 自动触发解析 | `assistant`, `value_*` | 已注册 | 用户上传触发 |
| `invest-pdf-parser` | PDF 转高保真 Markdown | `assistant`, `value_*` | 已注册 | 自动 / 手动 |

### 分析与认知（个人职责，由各 value agent 独立执行）

| Skill | 职责 | 计划注册到 | 当前状态 | 触发方式 |
|---|---|---|---|---|
| `invest-digest` | 每日新闻简报：筛选、核实、按重要性排序 | `value_*` | 已注册 | cron 每日 / 手动 |
| `invest-analysis` | 基于 SOUL.md + 多数据源的深度定性定量分析 | `value_*` | 已注册 | 手动 |
| `invest-review` | 复核投资原则锚点 | `value_*` | 已注册 | 手动 / 定期 |

## 目录结构

### Workspace 内（个人空间）
- `domains/` — 跨公司的行业共有逻辑
- `views/` — 单一公司专属观点
- `memory/` — 每日流水、切题日志
- `MEMORY.md` — OpenClaw 原生管理的长期摘要
- `SOUL.md` — 投资灵魂（核心信仰 + 锚点 + 关注清单）

### 共享数据（`/root/.openclaw/workspace/data/`）
- `references/` — companies.json 等配置
- `news/raw/` — invest-news 写入的原始新闻
- `companies/{company}/` — 公司资料库（filings / transcripts / sellside / primary / unofficial / news）
- `books/` — 投资经典书籍
