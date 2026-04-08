# 新闻落盘格式与自我进化规则

## 落盘 JSON 格式

每条新闻一行 JSON，追加到 `{OPENCLAW_DATA_DIR}/news/raw/YYYY-MM-DD.jsonl`：

```json
{
  "ts": "2026-03-30 14:22:00",
  "source": "财联社",
  "title": "新闻标题",
  "content": "新闻正文或摘要",
  "url": "https://...",
  "company": "tme",
  "company_name": "腾讯音乐娱乐",
  "company_symbol": "01698",
  "company_market": "HK",
  "match_type": "company|brand|competitor|industry",
  "match_keyword": "QQ音乐"
}
```

## 运行元数据 (Run Metadata)

为了满足 Harness 守恒规范（防止数据重漏），你在将 `web_search` 的结果追加到 JSONL 后，**必须**生成一份运行元数据，调用写文件工具（如 `fs_write` / `write`）写入 `{OPENCLAW_DATA_DIR}/news/raw/metadata/run_{时间戳}_{随机ID}.json`。

文件内容示例：

```json
{
  "run_id": "gemini-search-a1b2",
  "timestamp": "20260406_153000",
  "target_date": "2026-04-06",
  "scope": "腾讯音乐",
  "mode": "web_search",
  "success_count": 3
}
```

- `timestamp`: 格式为 `YYYYMMDD_HHMMSS`
- `success_count`: 代表你此次 `web_search` 实际写入 JSONL 的新闻条数。如果你没搜到任何新闻，这里填 `0`。

## 搜索策略

根据 `companies.json` 中的 `market` 字段采用差异化策略：

### 搜索关键词策略（通过搜索引擎间接获取，不直接访问任何站点）

- **CN / HK**：`{公司名} 最新消息 今日`、`{品牌} 新闻`（中文搜索）
- **US / Global**：`{english_name} latest news today`、`{brand} news`（英文搜索，content 字段需含中文摘要）
- 公司维度 → 品牌维度 → 竞品维度 → 行业维度，逐步搜索
- 聚焦最近 24 小时内的新闻
- 来源填搜索结果中显示的实际来源（如财联社、Reuters 等），不需要限定搜索特定站点

**注意**：不要使用 `site:` 限定搜索，不要直接访问目标网站，只从搜索引擎结果摘要中提取信息。

## 自我进化规则 (Self-evolving Radar)

采集中发现新竞品/品牌/行业关键词时，记录到 `memory/YYYY-MM-DD.md`：

```markdown
## [HH:MM] 雷达更新建议
- 公司: tme
- 字段: competitors
- 操作: 新增 "某某音乐"
- 原因: 在搜索新闻时发现该竞品频繁出现
```

不直接编辑 `companies.json`（防多 agent 并发冲突），由 assistant 统一更新。

### 约束
- 新增条目前先确认不重复
- 删除条目需谨慎，仅在确认该关联已失效时才移除
- 每次更新后在当日 JSONL 中记一条 `{"type": "radar_update", ...}` 日志
