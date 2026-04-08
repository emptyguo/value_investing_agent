# 飞书同步状态枚举与路径说明

## 状态枚举（只允许这些值）

| 状态 | 含义 | 产生阶段 |
|---|---|---|
| `inventoried` | 已登记元信息 | Stage 1 |
| `skipped_unchanged` | 增量判断无变化，跳过 | Stage 1 |
| `downloaded` | 已下载到 staging | Stage 2 |
| `parsed` | 已解析为 .md（或 `parse_method=copy`） | Stage 3 |
| `classified` | 已分类，落盘路径已确定（中间态） | Stage 4 |
| `archived` | 已落盘到最终目录 | Stage 4 |
| `failed_inventory` | 元信息获取失败 | Stage 1 |
| `failed_download` | 下载失败（后续阶段原样传递） | Stage 2 |
| `failed_parse` | 解析失败（Stage 4 降级归档） | Stage 3 |
| `failed_classify` | 分类失败 | Stage 4 |
| `failed_archive` | 落盘失败 | Stage 4 |

**注意**：`failed_download` 从 Stage 2 一直传递到 Stage 4，各阶段不修改、不跳过，只在计数闭合时纳入。

## 必需路径

| 用途 | 路径 |
|---|---|
| staging 根目录 | `{workspace}/lark_sync/staging/` |
| state | `{workspace}/lark_sync/state/doc_states.jsonl` |
| logs | `{workspace}/lark_sync/logs/` |
| 公司配置 | `{OPENCLAW_DATA_DIR}/references/companies.json` |
| 分类配置 | `{OPENCLAW_DATA_DIR}/references/doc_types.json` |
| 归档目标 | `{OPENCLAW_DATA_DIR}/companies/{company}/...` |
| 未识别池 | `{OPENCLAW_DATA_DIR}/industry/unclassified/lark/` |

其中 `{workspace}` = 当前 agent workspace（如 mifeng_corporate_hub 为 `/root/.openclaw/workspace/agents/mifeng_corporate_hub`）。
