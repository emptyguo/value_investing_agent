# Stage 3: Parse

## 目标

只做内容转换，输出 `parsed` 产物，不做分类和落盘。

## 输入

1. `{batch_id}_manifest.jsonl`
2. `{workspace}/lark_sync/staging/downloads/{batch_id}/`
3. `{workspace}/lark_sync/staging/parsed/{batch_id}/`

## 处理规则（按 `download_format` 分流）

1. 只处理 `stage=downloaded` 记录。
2. `stage=failed_download` 和 `stage=skipped_unchanged` 记录原样保留，不修改。

### `download_format=markdown`（飞书原生 doc/docx/wiki）

Stage 2 已将内容导出为 `.md`，Stage 3 **不需要再转换**：
- 将 `abs_download_path` 直接作为 `abs_parsed_path`
- 设 `stage=parsed`，`parse_method=pre_converted`

### `download_format=binary` + 文件类型为 PDF

调用 `invest-pdf-parser` 将 PDF 转为 Markdown：
- 输出 `.md` 到 `{workspace}/lark_sync/staging/parsed/{batch_id}/`
- 设 `stage=parsed`，`parse_method=pdf_parser`

### `download_format=binary` + 其他类型（xlsx/pptx/图片等）

无解析器，做降级处理：
- 设 `stage=parsed`，`parse_method=copy`（表示仅保留源文件、未做内容转换）
- `abs_parsed_path` 留空

### 通用写入字段

解析成功写：
- `parsed_path`
- `abs_parsed_path`（`parse_method=copy` 时留空）
- `parse_method`（`pre_converted` / `pdf_parser` / `copy`）
- `stage=parsed`
- `parsed_at`

解析失败写：
- `stage=failed_parse`
- `error`

## Gate

通过条件：

1. 所有 `stage=parsed` 记录的 `abs_parsed_path` 文件存在。
2. 计数闭合：`parsed + failed_parse + failed_download + skipped_unchanged = 上阶段记录总量`。
3. 不允许出现除 `parsed / failed_parse / failed_download / skipped_unchanged` 之外的 `stage` 值。

## 阶段回执（强制 JSON）

```json
{
  "stage": "stage3_parse",
  "ok": true,
  "batch_id": "20260401-154600",
  "parsed": 11,
  "failed_parse": 0,
  "failed_download": 1,
  "skipped_unchanged": 8,
  "next_stage_allowed": true
}
```
