# 架构决策记录 (ADR)

> 迁移日期：2026-03-30
> 状态：已实施

## 1. 迁移背景

系统从 `local_assets/` 自建平行结构迁移到 OpenClaw 原生目录标准：

- **之前**：`local_assets/agent_workspace/` + `local_assets/global_shared/skills/`
- **之后**：`templates/` + `skills/` + `workspace_data/` + `docs/`

## 2. 关键决策

### 2.1 Skill 合并策略

| 旧 Skill | 新 Skill | 原因 |
|---|---|---|
| `news` | `invest-news` | 重命名，加 `invest-` 前缀避免全局冲突 |
| `company-doc-router` | `invest-doc-router` | 重命名 |
| `company-library` + `qualitative` + `cognition` | `invest-analysis` | 三者有上下游依赖，合并为三阶段 skill |
| `twin` | `invest-review` | 简化为原则复核，去除 memory flush 职责 |
| `normal-chat` | **移除** | 由 OpenClaw 原生对话能力替代 |

### 2.2 twin.md + watchlist.md 合并到 SOUL.md

- **理由**：twin.md（稳定认知）、watchlist.md（关注清单）、SOUL.md（核心信仰） 三者都是跨会话的稳定个人偏好，拆成三个文件增加了 Agent "读取顺序" 的复杂度。
- **新结构**：`SOUL.md` = 核心信仰 + 锚点字段 + 禁忌 + 关注清单 + 偏好变化日志

### 2.3 Provision 幂等性分类

| 分类 | 文件 | 策略 |
|---|---|---|
| Template | AGENTS.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md | 可重复覆盖 |
| Personal | SOUL.md, USER.md | 仅首次写入 |
| Rule | doc_types.json | 每次覆盖 |
| Evolving Reference | companies.json | 合并，不直接覆盖 |
| Runtime | views/, memory/ | 绝不覆盖 |
| Merged | domains/*.md | 添加新文件，不覆盖已有 |

### 2.4 MEMORY.md vs memory/ 分工

- `MEMORY.md`：OpenClaw 原生机制管理的长期摘要，Agent 只读不写
- `memory/YYYY-MM-DD.md`：Agent 主动写入的每日流水，不跨日合并

## 3. 迁移映射

```
local_assets/agent_workspace/AGENTS.md     → templates/AGENTS.md
local_assets/agent_workspace/SOUL.md       → templates/SOUL.md
local_assets/agent_workspace/twin.md       → templates/SOUL.md (内容已吸收)
local_assets/agent_workspace/watchlist.md  → templates/SOUL.md (内容已吸收)
local_assets/agent_workspace/HEARTBEAT.md  → templates/HEARTBEAT.md
local_assets/agent_workspace/TOOLS.md      → templates/TOOLS.md
local_assets/agent_workspace/USER.md       → templates/USER.md
local_assets/agent_workspace/IDENTITY.md   → templates/IDENTITY.md
local_assets/agent_workspace/domains/      → templates/domains/
local_assets/agent_workspace/views/        → (运行态，由 provision 创建空目录)
local_assets/global_shared/skills/news/    → skills/invest-news/
local_assets/global_shared/skills/ingest/  → skills/invest-ingest/
local_assets/global_shared/skills/company-doc-router/ → skills/invest-doc-router/
local_assets/global_shared/skills/pdf-parser/         → skills/invest-pdf-parser/
local_assets/global_shared/skills/digest/             → skills/invest-digest/
local_assets/global_shared/skills/company-library/    → skills/invest-analysis/ (合并)
local_assets/global_shared/skills/qualitative/        → skills/invest-analysis/ (合并)
local_assets/global_shared/skills/cognition/          → skills/invest-analysis/ (合并)
local_assets/global_shared/references/companies.json  → workspace_data/references/companies.json
local_assets/global_shared/references/doc_types.json  → workspace_data/references/doc_types.json
```

## 4. 待清理

`local_assets/` 下的源文件和旧路径口径在所有验证完成后可以安全删除（非紧急）。

## 5. 参考文档

早期设计文档（docs/archive/）已清理。当前设计以各 `skills/invest-*/SKILL.md` 和 `templates/` 为准。
