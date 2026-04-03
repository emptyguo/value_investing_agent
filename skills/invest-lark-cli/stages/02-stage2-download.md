# Stage 2: Download

## 目标

只下载阶段 1 标记为 `inventoried` 的文件到 staging，不做解析和分类。

## 执行方式

**Agent 运行脚本，不直接调用飞书 API。**

```bash
python3 skills/invest-lark-cli/scripts/lark_download.py \
  --workspace {workspace} \
  --batch-id <batch_id>
```

脚本内部调用 `lark-cli` 完成：
1. 读取 manifest，筛选 `stage=inventoried` 记录
2. 飞书原生文档（doc/docx/wiki）→ `lark-cli docs +fetch` 导出 Markdown
3. 二进制文件（PDF/Word/Excel）→ `lark-cli drive +download` 下载原文件
4. 更新 manifest 中的下载路径和状态

## 输入

1. `{batch_id}_manifest.jsonl`
2. 下载目标目录：`{workspace}/lark_sync/staging/downloads/{batch_id}/`

## 处理规则

1. 只处理 `stage=inventoried` 记录。
2. 下载成功后脚本写：
   - `download_path`（相对路径）
   - `abs_download_path`（绝对路径）
   - `download_format`（`markdown` 或 `binary`）
   - `stage=downloaded`
   - `downloaded_at`
3. 下载失败写：
   - `stage=failed_download`
   - `error`
4. `skipped_unchanged` 记录保持不变。

## Gate

通过条件：

1. 所有 `stage=downloaded` 记录的 `abs_download_path` 文件实际存在。
2. `downloaded + skipped_unchanged + failed_download = stage1.inventoried + stage1.skipped_unchanged`。
3. 不允许出现空路径的 `downloaded` 记录。

失败处理：

1. 脚本自动标记失败项为 `failed_download`。
2. 输出回执并停止。

## 阶段回执（脚本自动输出）

```json
{
  "stage": "stage2_download",
  "ok": true,
  "batch_id": "20260401-154600",
  "downloaded": 12,
  "skipped_unchanged": 8,
  "failed_download": 0,
  "next_stage_allowed": true
}
```
