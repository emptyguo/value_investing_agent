# Gates And Recovery

## 通用 Gate 规则

1. 阶段前 gate：读取上一阶段回执，若 `next_stage_allowed=false` 则禁止继续。
2. 阶段后 gate：校验“记录数闭合 + 文件存在性 + stage 枚举合法”。
3. 任一 gate 失败必须停机，不允许“猜测修复后继续”。

## 计数闭合规则

每阶段必须能回答：

1. 输入记录总数是多少
2. 成功数是多少
3. 跳过数是多少
4. 失败数是多少
5. 四者是否闭合

不闭合视为失败。

## 路径安全规则

1. staging 文件必须位于 `{workspace}/lark_sync/staging/` 子树。
2. 最终归档必须位于 `{OPENCLAW_DATA_DIR}/` 子树。
3. 任一路径越界立即失败并停止。

## 断点续传

1. 只处理当前阶段的合法前置状态记录。
2. 已完成记录不重复处理。
3. 重跑不应破坏已归档结果。

## 清理策略

1. 仅当阶段 4 回执 `ok=true` 且 `failed_archive=0` 时允许清理 staging 文件。
2. manifest 至少保留 30 天。
3. 未完成批次严禁清理。

## 标准失败回执（强制 JSON）

```json
{
  "stage": "stageX",
  "ok": false,
  "batch_id": "20260401-154600",
  "error_code": "GATE_VALIDATION_FAILED",
  "error_message": "count mismatch: input=20 success=18 failed=1 skipped=0",
  "next_stage_allowed": false
}
```
