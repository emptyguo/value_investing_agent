# 工作区工具规范 (TOOLS.md)

## 文件读写规范

- **日期格式**：所有日期采用 `YYYY-MM-DD` 格式。
- **文件编码**：UTF-8。
- **JSONL 格式**：每行一条独立 JSON 记录。

## 路由表

| 用户意图 | 技能 |
|---|---|
| 搜新闻、查最新动态 | invest-news → invest-ingest |
| 发来 PDF/研报/纪要 | invest-doc-router → invest-pdf-parser |
| 要求深度分析某公司 | invest-analysis |
| 每日简报 | invest-digest |
| 复核投资原则 | invest-review |
| 切换公司或主题 | invest-focus |
| 同步/拉取飞书文档 | invest-lark-cli |

**注意**：所有以 `invest-` 开头的指令均为内置技能（Skill），必须通过 `activate_skill` 工具（或对应唤醒词）加载执行，**绝不可作为子代理（Sub-agent）调度**。

触发技能后，必须立即使用 `activate_skill` 工具（或对应的 Skill 唤醒词）加载该技能的 SKILL.md 并严格遵循。

## 目录结构

### Workspace 内（个人空间）
- `domains/` — 跨公司的行业共有逻辑
- `views/` — 单一公司专属观点
- `memory/` — 每日流水、切题日志
- `MEMORY.md` — OpenClaw 原生管理的长期摘要
- `SOUL.md` — 投资灵魂（核心信仰 + 锚点 + 关注清单）

### 共享数据（`{OPENCLAW_DATA_DIR}/`）
- `references/` — companies.json 等配置
- `news/raw/` — invest-news 写入的原始新闻
- `companies/{company}/` — 公司资料库（filings / transcripts / sellside / primary / unofficial / news）
- `books/` — 投资经典书籍
