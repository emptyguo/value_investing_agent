---
name: invest-news
description: 采集市场新闻并存入公共原始数据区 {OPENCLAW_DATA_DIR}/news/raw/
---

# Invest News Skill

## 核心职责

纯采集技能——采集原始新闻事实、最小去重、追加写入 JSONL。
**绝不做**：真实性核实、重要性排序、观点总结、投资判断、碰 `{OPENCLAW_DATA_DIR}/companies/` 目录。

## 关键路径

| 用途 | 路径 |
|---|---|
| 公司配置 | `{OPENCLAW_DATA_DIR}/references/companies.json` |
| 新闻落盘 | `{OPENCLAW_DATA_DIR}/news/raw/YYYY-MM-DD.jsonl` |
| 格式与搜索策略 | 读取 `references/news-schema.md` |

## 执行步骤

1. 读取 `references/news-schema.md` 获取 JSON 落盘格式和自我进化规则
2. 读取 `companies.json`，获取 brands、competitors、industry_keywords
3. 按 `market` 字段差异化搜索（见下方搜索技巧）
4. 全维度搜索：公司名 + 品牌 + 竞品 + 行业关键词，聚焦最近 24 小时
5. 去重（同一天 + 同公司 + 同标题 + 同来源 = 重复）后追加写入 JSONL
6. 如发现新竞品/品牌/关键词，按 `references/news-schema.md` 中的自我进化规则处理

## 执行方式（双引擎复合采集策略）

**你必须采用“网络搜索 + AKShare”的双引擎策略，获取复合消息面，而不仅依赖单一信源。**

### 步骤（必须使用工具真实执行，绝不脑补）

1. **引擎一：宏观舆情与竞品采集**。你必须**分多次独立真实地调用** `web_search` 工具：
   - 搜索**主体公司**：`{公司名} 最新消息 今日`
   - 搜索**竞品动态**：查阅 `companies.json`，搜索 `{竞品名称} 最新消息`
   - 搜索**行业动态**：查阅 `companies.json`，搜索 `{行业关键词} 趋势 今日`

2. **引擎二：主体盘面采集**。调用你的终端工具（如 `exec`），**真实执行以下脚本**（AKShare 脚本会自动将其结果落盘，你无需手动处理它的输出）：
   ```bash
   python3 skills/invest-news/scripts/fetch_news.py --subject <公司名>
   ```

3. **数据组装**。把你用 `web_search` 搜回来的主体、竞品、行业动态，严格按照 `references/news-schema.md` 提取并组装为 JSON 格式。

4. **真实落盘追加写入（极度危险区）**。**严禁使用写文件工具（如 fs_write）去写 JSONL 文件（会覆盖清空数据）！** 你**必须**调用终端工具（如 `exec`），执行以下命令将你组装好的 JSON 记录严格**追加**到物理文件中（有几条记录就执行几次追加）：
   ```bash
   echo '{"ts": "...", "source": "...", ...}' >> {OPENCLAW_DATA_DIR}/news/raw/YYYY-MM-DD.jsonl
   ```

5. **生成流水账（Metadata）**。调用写文件工具，将你 `web_search` 写入的成功条数，生成元数据写入以下路径：
   `{OPENCLAW_DATA_DIR}/news/raw/metadata/run_{时间戳}_{随机ID}.json`

6. 如搜索均无结果，记录空结果即可，绝不编造。

### 搜索技巧（防反爬）

- **不要**在搜索词中使用 `site:xxx.com` 限定特定网站
- **不要**直接访问/抓取目标网站页面（会触发机器人检测）
- 只通过搜索引擎的通用搜索获取结果（搜索结果摘要已包含足够信息）
- CN/HK 市场：搜索 `{公司名} 最新消息 今日`、`{品牌名} 新闻`
- US/Global 市场：搜索 `{company_english_name} latest news today`、`{brand} news`（content 字段需含中文摘要）
- 每次搜索保持关键词简短通用，多次搜索覆盖不同维度（公司/品牌/竞品/行业）
- 如果某次搜索被拦截，**换一种关键词表述重试**，不要放弃

### 禁止事项

- **禁止** 跳过 `web_search` 仅依赖 AKShare，或跳过 AKShare 仅依赖 `web_search`（需提供多维复合消息面）。
- **禁止** 直接编写虚构新闻，未搜到内容时请如实反馈空结果。

## 硬约束

1. 只写事实，不写观点
2. 只做简单去重，不做深度加工
3. 失败可回退为空结果，不推断或补写
4. 允许空结果，不凑数
