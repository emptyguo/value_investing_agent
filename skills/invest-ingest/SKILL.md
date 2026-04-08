---
name: invest-ingest
description: 将 news/raw/ 中的新闻按公司分流到 companies/{company}/ 目录，纯机械数据处理
---

# Invest Ingest Skill

## 核心职责

`invest-ingest` 是纯数据处理技能，将公共新闻池中的原始新闻按公司分流到各自的资料库目录。

**只做**：读取、分流、去重、记录时间线
**绝不做**：分析、判断、总结、评价

## 关键路径

| 用途 | 路径 |
|---|---|
| 输入 | `{OPENCLAW_DATA_DIR}/news/raw/YYYY-MM-DD.jsonl` |
| 输出 | `{OPENCLAW_DATA_DIR}/companies/{company}/news/raw/YYYY-MM-DD.jsonl` |
| 笔记 | `{OPENCLAW_DATA_DIR}/companies/{company}/news/notes/YYYY-MM-DD.jsonl` |
| 时间线 | `{OPENCLAW_DATA_DIR}/companies/{company}/timeline.md` |

## 执行方式（唯一合法路径）

**严禁 Agent 自己去读取 JSONL 或手动写入文件。这种行为会破坏系统的底层状态追踪（`ingest_state.jsonl`）和指纹校验。**

无论是在用户对话中触发，还是通过 Cron 触发，你**必须且只能**调用终端工具（如 `exec` 或 `bash`），在工作区根目录下执行以下 Python 脚本：

```bash
python3 skills/invest-ingest/scripts/ingest_news_to_companies.py --date YYYY-MM-DD
```

（请将 `YYYY-MM-DD` 替换为你实际想要分流的日期，默认为今天）。

脚本执行完毕后，它会在控制台输出类似 `[Companies: tme] raw_saved=9` 的汇总信息。你只需要将这个标准输出的汇总结果直接转述给用户即可。

## 处理逻辑（由脚本自动完成，无需你操心）

1. 读取当日 `news/raw/YYYY-MM-DD.jsonl`
2. 按每条记录的 `company` 字段分组
3. 分别写入 `companies/{company}/news/raw/` 和 `news/notes/`（去重）
4. 追加 `timeline.md` 记录

## 执行规则

- **幂等执行**：重复运行同一天不会产生重复数据
- **不做内容加工**：原样搬运，只增加结构化索引字段
- **可由 cron 自动触发**：建议在 invest-news 之后定时执行
