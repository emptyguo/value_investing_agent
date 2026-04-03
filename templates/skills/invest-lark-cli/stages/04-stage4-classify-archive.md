# Stage 4: Classify And Archive

## 目标

先分类再落盘，且落盘路径必须由 `doc_types.json` 驱动。

## 输入

1. `{batch_id}_manifest.jsonl`
2. `~/.openclaw/workspace/data/references/companies.json`
3. `~/.openclaw/workspace/data/references/doc_types.json`
4. `{workspace}/lark_sync/staging/downloads/{batch_id}/`
5. `{workspace}/lark_sync/staging/parsed/{batch_id}/`

## 飞书文件夹结构（非均匀，两种模式）

manifest 中每条记录包含 `feishu_path_segments`（路径段列表）和 `feishu_path`（原始路径字符串），据此分类。

### 模式 A：标准结构（公司 → 文档类型 → 文件）

```
业务组/公司/doc_type目录/文件
```

示例路径段：`["TME", "简报", "TME 4Q25.pdf"]` 的 segments 为 `["TME", "简报"]`

- 公司 = segments 中命中 `companies.json` 的那个段
- doc_type = segments 中命中映射表或 `doc_types.json.keywords` 的那个段

### 模式 B：纪要合集（反转结构：文档类型 → 公司 → 文件）

```
业务组/纪要合集/公司/文件
业务组/纪要合集/公司/业绩会/文件
```

- 当 segments 中包含"纪要合集" → 触发模式 B
- doc_type = `meeting_minutes`（纪要合集下的文件默认为纪要）
- 若子目录为"业绩会" → doc_type 改为 `earnings_calls`
- 公司 = "纪要合集"后面紧跟的那个段

### 混合目录处理

| 飞书目录名 | 处理方式 |
|---|---|
| `招股书&年报&业绩公告` | 按文件名关键词二次判断：含"招股"→ `prospectus`，含"年报"→ `annual`，含"季报/中报/半年报"→ `quarterly`，其余 → `announcements` |

## 分类规则

### 公司识别（优先级从高到低）

1. `feishu_path_segments` 中逐段匹配 `companies.json` 的 `id/name/aliases`
2. 文件名/标题命中
3. 正文首段命中
4. 以上都不命中 → `company=unknown`

### 文档类型识别

**统一使用 `doc_types.json.keywords` 动态匹配**，不维护硬编码映射表。

流程：

1. 加载 `doc_types.json`，构建关键词 → doc_type 索引
2. 将 `feishu_path_segments` 的每个段与所有 doc_type 的 keywords 做包含匹配
3. 若命中 → 使用该 doc_type
4. 若未命中 → 用文件名/标题再匹配一轮
5. 仍未命中 → 使用 `doc_types.json.default_doc_type`

**特殊规则（仅两条，优先于通用匹配）：**

| 条件 | 处理 |
|---|---|
| segments 中包含"纪要合集" | 触发模式 B（见上方结构说明）；默认 `meeting_minutes`，子目录含"业绩会"则改为 `earnings_calls` |
| segments 中包含"招股书&年报&业绩公告"等混合目录 | 该段跳过，改用文件名关键词二次判断：含"招股"→ `prospectus`，含"年报"→ `annual`，含"季报/中报/半年报"→ `quarterly`，其余 → `announcements` |

**匹配方式**：段名包含某 keyword 即视为命中（如段名"重要公告"包含 keyword"公告" → 命中 `announcements`）。多个 doc_type 同时命中时，取 `credibility` 等级更高（L1 > L2 > L3 > L4 > L5）的那个。

## 落盘路径公式（强制）

```
源文件：  data/companies/{company_id}/{doc_type.dir}/source/{filename}
解析文件：data/companies/{company_id}/{doc_type.dir}/{filename_stem}.md
未识别：  data/industry/unclassified/lark/{filename}
```

- `{company_id}` 来自 `companies.json.id`（英文小写）
- `{doc_type.dir}` 来自 `doc_types.json` 对应条目的 `dir` 字段
- 严禁使用中文目录名；严禁自行拼接路径

示例：
```
data/companies/tme/sellside/briefings/source/tme_4q25.pdf
data/companies/tme/sellside/briefings/tme_4q25.md
```

## 落盘规则

1. 处理 `stage=parsed` 和 `stage=failed_parse` 记录。`stage=failed_download` 和 `stage=skipped_unchanged` 记录原样保留。
2. 对于 `failed_parse` 记录采取**降级归档**：仅落盘源文件，`target_parsed_path` / `abs_target_parsed_path` 留空。
3. 分类成功写：
   - `company`
   - `doc_type`
   - `doc_type_dir`
   - `target_source_path`
   - `target_parsed_path`（降级归档时留空）
   - `abs_target_source_path`
   - `abs_target_parsed_path`（降级归档时留空）
   - `stage=classified`
4. 落盘完成后写：
   - `stage=archived`
   - `archived_at`
5. `company=unknown` 落到 `data/industry/unclassified/lark/`。
6. 更新：
   - `state/doc_states.jsonl`
   - 公司 `timeline.md`
   - 公司 `intake_log.jsonl`

## Gate

通过条件：

1. 每个 `archived` 记录的源文件必须在目标路径真实存在。若存在 parsed 文件（即非降级归档），则 parsed 文件也必须存在。
2. 目录必须英文化且来自 `doc_types.json.dir`，禁止中文目录名。
3. 计数闭合：`archived + failed_classify + failed_archive + failed_download + skipped_unchanged = 上阶段记录总量`。

失败处理：

1. 记录 `failed_classify` 或 `failed_archive`。
2. 写入 `error` 并停止后续清理动作。

## 阶段回执（强制 JSON）

```json
{
  "stage": "stage4_classify_archive",
  "ok": true,
  "batch_id": "20260401-154600",
  "classified": 11,
  "archived": 11,
  "unknown_company": 1,
  "failed_classify": 0,
  "failed_archive": 0,
  "next_stage_allowed": true
}
```
