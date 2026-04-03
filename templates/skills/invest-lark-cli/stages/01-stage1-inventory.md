# Stage 1: Inventory

## 目标

只做"遍历 + 元信息归集 + 增量判断"，不下载文件内容。

## 执行方式

**Agent 运行脚本，不直接调用飞书 API。**

```bash
# 云盘文件夹模式
python3 skills/invest-lark-cli/scripts/lark_inventory.py \
  --workspace {workspace} \
  --source <folder_token_or_url>

# 知识库模式
python3 skills/invest-lark-cli/scripts/lark_inventory.py \
  --workspace {workspace} \
  --wiki-space <space_id> \
  [--wiki-node <parent_node_token>]
```

脚本内部调用 `lark-cli` 完成：
1. 递归遍历飞书文件夹/知识库节点
2. 获取每个文件的元信息（token、类型、修改时间）
3. 对比 `state/doc_states.jsonl` 做增量判断
4. 写入 `{workspace}/lark_sync/staging/{batch_id}_manifest.jsonl`

## 输入

1. 飞书入口（文件夹 token/URL 或 wiki space_id）
2. `state/doc_states.jsonl`（历史状态，用于增量判断）

## 输出

`{workspace}/lark_sync/staging/{batch_id}_manifest.jsonl`，每行一条记录：

```json
{
  "batch_id": "20260401-154600",
  "file": "QLibbMurco_4Q25_TME_Investor_Presentation.pdf",
  "original_name": "4Q25 TME Investor Presentation.pdf",
  "doc_token": "QLibbMurcoZ4JixDjkBceGApnmf",
  "file_type": "pdf",
  "created_at": "1774841002",
  "updated_at": "1774841070",
  "feishu_path": "腾讯音乐/01698&TME腾讯音乐/简报/",
  "feishu_path_segments": ["腾讯音乐", "01698&TME腾讯音乐", "简报"],
  "depth": 3,
  "source_type": "drive",
  "stage": "inventoried"
}
```

## 增量规则

1. 若 `updated_at` 与 `doc_states.jsonl` 中一致且上次已 `archived`，标记 `skipped_unchanged`。
2. 否则保留 `inventoried`，进入阶段 2。

## Gate

通过条件：

1. manifest 文件存在且非空（允许全量 `skipped_unchanged`）。
2. 所有记录都包含 `doc_token` 主键。
3. `stage` 只出现 `inventoried` 或 `skipped_unchanged` 或 `failed_inventory`。

失败处理：

1. 脚本会写入 `failed_inventory` 和 `error`。
2. 输出阶段回执并停止，不进入阶段 2。

## 阶段回执（脚本自动输出）

```json
{
  "stage": "stage1_inventory",
  "ok": true,
  "batch_id": "20260401-154600",
  "total": 20,
  "inventoried": 12,
  "skipped_unchanged": 8,
  "failed_inventory": 0,
  "manifest_path": "{workspace}/lark_sync/staging/20260401-154600_manifest.jsonl",
  "next_stage_allowed": true
}
```
