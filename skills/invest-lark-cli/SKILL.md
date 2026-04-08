---
name: invest-lark-cli
description: 分阶段 pipeline 同步飞书云文档/云盘文件到投研资料库，只做采集与归档，不做分析
---

# Invest Lark Sync Skill

## 核心职责

采集归档飞书云文档，不做任何投资分析。执行方式："总控文档 + 分阶段文档 + 阶段门禁"。

## 执行边界（按 agent 区分）

- **下载流水线（stages/01-04）**：仅 `mifeng_corporate_hub` 执行。其他 agent（`assistant` / `value_*`）即使注册了本技能，也**不得**触发四阶段下载流水线。
- **单文件上传（`lark_upload.py`）**：所有注册了本技能的 agent 都可以使用。

## 前置条件

- `lark-cli` 已安装（`npm install -g @larksuite/cli`）并已认证

## 总体原则

1. Stage 1-2 走脚本（飞书 API 交互），Agent 不直接调用 `feishu_*` 工具
2. Stage 3-4 走 Agent 原生能力（解析和分类归档）
3. 每阶段：读文档 → 执行 → 过 gate → 下一阶段
4. 失败必须写入 manifest 状态和 error 字段，不允许静默跳过
5. 路径分离：运行态 `{workspace}/lark_sync/`，最终归档 `{OPENCLAW_DATA_DIR}/`
6. `companies.json` 只读，不自动扩容

状态枚举和路径说明：读取 `references/lark-states.md`

## 阶段文档

1. `stages/01-stage1-inventory.md`
2. `stages/02-stage2-download.md`
3. `stages/03-stage3-parse.md`
4. `stages/04-stage4-classify-archive.md`
5. `stages/05-gates-and-recovery.md`

## 执行顺序（强制）

1. 先读 `references/lark-states.md` 和 `05-gates-and-recovery.md` 的公共 gate 规则
2. 按 01 → 02 → 03 → 04 顺序执行

### Stage 1-2：运行脚本

```bash
# Stage 1: Inventory
python3 skills/invest-lark-cli/scripts/lark_inventory.py \
  --workspace {workspace} --source <folder_token_or_url>

# Stage 2: Download
python3 skills/invest-lark-cli/scripts/lark_download.py \
  --workspace {workspace} --batch-id <batch_id_from_stage1>
```

### Stage 3-4：Agent 执行

```bash
# Stage 3: Parse
python3 skills/invest-lark-cli/scripts/agent_stage3.py \
  --workspace {workspace} --batch-id <batch_id>

# Stage 4: Classify & Archive
python3 skills/invest-lark-cli/scripts/agent_stage4.py \
  --workspace {workspace} --batch-id <batch_id>
```

### 门禁校验（每阶段完成后强制执行）

```bash
python3 skills/invest-lark-cli/scripts/verify_stage.py \
  --workspace {workspace} --batch-id {batch_id} --stage stage1|stage2|stage3|stage4
```

**Gate 1**（Stage 2 后）：`total == downloaded + failed_download + skipped_unchanged` 且 `ok=true`。不闭合 → 停止，禁入 Stage 3。

**Gate 2**（Stage 3 后）：`total == parsed + failed_parse + failed_download + skipped_unchanged`。任何 `downloaded` 未转换 → 停止，禁入 Stage 4。

**Gate 3**（全流程后）：`skills/invest-lark-cli/scripts/batch_summary.py --silent-if-empty`，最终闭环汇报。

## 飞书源链接溯源（feishu_url）

Stage 4 在归档每条记录时会写入 `feishu_url` 字段，路由规则集中在 `skills/common/scripts/utils.py:build_feishu_url`：

- `source_type=wiki` → `https://feishu.cn/wiki/{token}`
- `file_type=doc/docx` → `https://feishu.cn/docx/{token}`
- `file_type=sheet` → `https://feishu.cn/sheets/{token}`
- `file_type=bitable` → `https://feishu.cn/base/{token}`
- 其他 → `https://feishu.cn/file/{token}`

写入位置：manifest 行、`{co}/intake_log.jsonl`、`{co}/timeline.md`。

历史归档记录（无 `feishu_url` 字段）使用一次性脚本回填：

```bash
python3 skills/invest-lark-cli/scripts/backfill_feishu_urls.py \
  --workspace {workspace} [--dry-run]
```

幂等：按 `stored_rel_path` 去重，已有 `feishu_url` 的记录不重复写入。仅在历史数据迁移时使用，不进入常规流水线。

## 上传单个文件到飞书云盘

当用户需要"把某个本地文件传到飞书"时，**必须**使用本技能的 `lark_upload.py`，不允许使用 OpenClaw 底层的 `feishu_*` 原生工具。

```bash
python3 skills/invest-lark-cli/scripts/lark_upload.py <本地文件> [--folder <token>] [--name <飞书侧文件名>]
```

- 默认 folder token：`Aw6JfcD3jlHmV3dNJIucD6dSnLg`（mifeng_corporate_hub 统一上传目录）
- 文件大小上限：20MB（lark-cli `drive +upload` 限制）
- 仅支持单文件，不支持批量、不维护状态、不做去重——重复需求请先与用户确认是否真的需要

## 硬约束

1. 严禁输出分析结论
2. 严禁使用中文目录名；落盘目录由 `doc_types.json.dir` 决定
3. 严禁在 Stage 4 临时改分类；分类只能来自 Stage 3 的 manifest
4. 允许空结果，空结果也要输出阶段回执
5. 上传文件到飞书时，**只能**走 `lark_upload.py`，不允许调用 `feishu_upload_*` / `feishu_drive_*` 等 OpenClaw 原生工具
