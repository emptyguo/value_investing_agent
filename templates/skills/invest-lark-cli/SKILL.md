---
name: invest-lark-cli
description: 分阶段 pipeline 同步飞书云文档/云盘文件到投研资料库，只做采集与归档，不做分析
---

# Invest Lark Sync Skill

## 核心职责

`invest-lark-cli` 只负责采集归档，不做任何投资分析。执行方式是“总控文档 + 分阶段文档 + 阶段门禁（gate）”。

## 前置条件

- 服务器已安装 `lark-cli`（`npm install -g @larksuite/cli`）
- 已完成认证：`lark-cli auth login --recommend`

## 总体原则

1. **Stage 1-2 走 lark-cli 脚本**：飞书 API 交互全部由 `scripts/lark_inventory.py` 和 `scripts/lark_download.py` 完成，Agent 不直接调用 `feishu_*` 工具。
2. **Stage 3-4 走 Agent 原生能力**：解析和分类归档由 Agent 按阶段文档执行。
3. 每个阶段必须先读本阶段文档，再执行，再过 gate，才能进入下一阶段。
4. 阶段失败必须写入 manifest 的 `failed_*` 状态和 `error` 字段，不允许静默跳过。
5. 路径必须分离：
   - 运行态：`{workspace}/lark_sync/...`
   - 最终归档：`~/.openclaw/workspace/data/...`
6. `companies.json` 只读，不自动扩容。

## 阶段文档清单

1. `stages/01-stage1-inventory.md`
2. `stages/02-stage2-download.md`
3. `stages/03-stage3-parse.md`
4. `stages/04-stage4-classify-archive.md`
5. `stages/05-gates-and-recovery.md`

## 执行顺序（强制）

1. 先读取 `05-gates-and-recovery.md` 的公共 gate 规则。
2. 按 01 → 02 → 03 → 04 顺序执行。

### Stage 1-2：运行脚本

```bash
# Stage 1: Inventory（云盘文件夹）
python3 skills/invest-lark-cli/scripts/lark_inventory.py \
  --workspace {workspace} \
  --source <folder_token_or_url>

# Stage 2: Download
python3 skills/invest-lark-cli/scripts/lark_download.py \
  --workspace {workspace} \
  --batch-id <batch_id_from_stage1>
```

脚本自动输出 JSON 回执，Agent 读取回执判断是否继续。

### Stage 3: Parse

```bash
python3 skills/invest-lark-cli/scripts/agent_stage3.py \
  --workspace {workspace} \
  --batch-id <batch_id>
```

### Stage 4: Classify & Archive

```bash
python3 skills/invest-lark-cli/scripts/agent_stage4.py \
  --workspace {workspace} \
  --batch-id <batch_id>
```

### 每阶段完成后：运行校验（流水线硬门禁）

**必须严格遵守以下门禁逻辑，严禁静默跳过任何校验步骤：**

1. **Gate 1 (Stage 1-2 闭合)**：
   - 执行 Stage 2 下载后，必须运行 `verify_stage.py --stage stage2`。
   - **准入准则**：`total == downloaded + failed_download + skipped_unchanged` 且 `ok=true`。
   - **违规处理**：若计数不闭合，流水线必须原地停止，严禁进入 Stage 3。

2. **Gate 2 (Stage 3 完整性)**：
   - 执行 Stage 3 解析后，必须运行 `verify_stage.py --stage stage3`。
   - **准入准则**：`total == parsed + failed_parse + failed_download + skipped_unchanged`。
   - **违规处理**：若任何一条 `downloaded` 记录未能转换为 `parsed` 或 `failed_parse`，流水线必须原地停止，**绝不允许进入 Stage 4 归档**。

3. **Gate 3 (最终审计与静默汇报)**：
   - 全流程结束后，运行 `scripts/batch_summary.py --silent-if-empty`。
   - 该脚本作为 Pipeline 的最终闭环，负责向用户/监控系统汇报本次变动。

```bash
# 校验示例
python3 skills/invest-lark-cli/scripts/verify_stage.py \
  --workspace {workspace} --batch-id {batch_id} --stage stage1|stage2|stage3|stage4
```

## 必需路径

- `{workspace}` = 当前 agent workspace（如 `mifeng_corporate_hub` 为 `/root/.openclaw/workspace/agents/mifeng_corporate_hub`）
- staging 根目录：`{workspace}/lark_sync/staging/`
- state：`{workspace}/lark_sync/state/doc_states.jsonl`
- logs：`{workspace}/lark_sync/logs/`
- 公司配置：`~/.openclaw/workspace/data/references/companies.json`
- 分类配置：`~/.openclaw/workspace/data/references/doc_types.json`
- 归档目标：`~/.openclaw/workspace/data/companies/{company}/...`
- 未识别池：`~/.openclaw/workspace/data/industry/unclassified/lark/`

## 状态枚举（只允许这些值）

| 状态 | 含义 | 产生阶段 |
|---|---|---|
| `inventoried` | 已登记元信息 | Stage 1 |
| `skipped_unchanged` | 增量判断无变化，跳过 | Stage 1 |
| `downloaded` | 已下载到 staging | Stage 2 |
| `parsed` | 已解析为 .md（或无解析器时标记 `parse_method=copy`） | Stage 3 |
| `classified` | 已分类，落盘路径已确定（中间态） | Stage 4 |
| `archived` | 已落盘到最终目录 | Stage 4 |
| `failed_inventory` | 元信息获取失败 | Stage 1 |
| `failed_download` | 下载失败（后续阶段原样传递） | Stage 2 |
| `failed_parse` | 解析失败（Stage 4 降级归档） | Stage 3 |
| `failed_classify` | 分类失败 | Stage 4 |
| `failed_archive` | 落盘失败 | Stage 4 |

注意：`failed_download` 会从 Stage 2 一直传递到 Stage 4，各阶段不修改、不跳过，只在计数闭合时纳入。

## 硬约束

1. 严禁输出分析结论。
2. 严禁使用中文目录名作为最终落盘目录；必须由 `doc_types.json.dir` 决定。
3. 严禁在阶段 4 临时改分类；分类只能来自阶段 3 写入的 manifest 字段。
4. 允许空结果；空结果也要输出阶段回执。
