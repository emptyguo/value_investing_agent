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
| 输入 | `~/.openclaw/workspace/data/news/raw/YYYY-MM-DD.jsonl` |
| 输出 | `~/.openclaw/workspace/data/companies/{company}/news/raw/YYYY-MM-DD.jsonl` |
| 笔记 | `~/.openclaw/workspace/data/companies/{company}/news/notes/YYYY-MM-DD.jsonl` |
| 时间线 | `~/.openclaw/workspace/data/companies/{company}/timeline.md` |

## 执行方式

### 交互模式（用户对话中触发）

Agent 直接读取 JSONL 文件，按 `company` 字段分流写入对应公司目录。

### 批量模式（cron 自动触发）

```bash
python3 {baseDir}/scripts/ingest_news_to_companies.py --date YYYY-MM-DD
```

## 处理逻辑

1. 读取当日 `news/raw/YYYY-MM-DD.jsonl`
2. 按每条记录的 `company` 字段分组
3. 分别写入 `companies/{company}/news/raw/` 和 `news/notes/`（去重）
4. 追加 `timeline.md` 记录

## 执行规则

- **幂等执行**：重复运行同一天不会产生重复数据
- **不做内容加工**：原样搬运，只增加结构化索引字段
- **可由 cron 自动触发**：建议在 invest-news 之后定时执行
