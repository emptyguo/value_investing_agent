# 部署指南

## 前提

- 以根目录 `openclaw.json` 为线上真相源
- OpenClaw 已安装并可运行
- 服务器运行目录为 `/root/.openclaw/workspace/`

## 1. 部署 Skills

当前仓库中需要同步的 `invest-*` skills 共 8 个：

- `invest-news`
- `invest-ingest`
- `invest-doc-router`
- `invest-pdf-parser`
- `invest-lark-cli`
- `invest-digest`
- `invest-analysis`
- `invest-review`

同步命令：

```bash
rsync -a --exclude='__pycache__' skills/ templates/skills/
```

部署目录：`/root/.openclaw/workspace/skills`

安装依赖：

```bash
# PDF 解析
pip install opendataloader-pdf

# 飞书 CLI（invest-lark-cli 依赖）
npm install -g @larksuite/cli
lark-cli auth login --recommend
```

验证：

```bash
ls ~/.openclaw/workspace/skills/invest-*
# 应看到:
# invest-analysis
# invest-digest
# invest-doc-router
# invest-ingest
# invest-lark-cli
# invest-news
# invest-pdf-parser
# invest-review
```

## 2. 创建共享数据目录并同步参考数据

```bash
mkdir -p /root/.openclaw/workspace/data/references
mkdir -p /root/.openclaw/workspace/data/news/raw
mkdir -p /root/.openclaw/workspace/data/books
mkdir -p /root/.openclaw/workspace/data/companies
mkdir -p /root/.openclaw/workspace/data/industry/unclassified/lark

# doc_types.json 是公共分类规则，每次部署覆盖
cp workspace_data/references/doc_types.json /root/.openclaw/workspace/data/references/
```

`companies.json` 不建议直接覆盖，也不建议仅首次写入。它既包含仓库里手动新增的公司，也可能包含线上运行中积累出来的别名、竞品、行业关键词等演化字段。

建议对 `companies.json` 采用合并策略：

- 仓库权威字段：`id`、`name`、`symbol`、`market`
- 线上保留字段：`aliases`、`brands`、`competitors`、`industry_keywords`、`enabled_sources`、`schedule_profile`

这意味着：

- 仓库里新增的公司应补入线上
- 已有公司的基础标识字段以仓库为准
- 已有公司的雷达/监控扩展字段保留线上已有内容

按当前模板和 skills 约定，共享数据根目录为：

- `/root/.openclaw/workspace/data/references/`
- `/root/.openclaw/workspace/data/news/raw/`
- `/root/.openclaw/workspace/data/companies/`
- `/root/.openclaw/workspace/data/books/`
- `/root/.openclaw/workspace/data/industry/unclassified/lark/`

## 3. Provision Agent Workspace

所有 agent 统一从 `templates/` 部署，不再需要 `agents/` 目录。

新增 agent 只需在 `openclaw.json` 中添加条目，然后重新执行以下步骤。

```bash
for AGENT_ID in mifeng_corporate_hub value_guo value_tianxiong value_qingfeng value_weichao value_liaobin; do
  WORKSPACE=/root/.openclaw/workspace/agents/$AGENT_ID

  # 3a. 创建目录结构
  mkdir -p $WORKSPACE/{domains,views,memory}

  # 3a-extra. mifeng_corporate_hub 专用目录
  if [ "$AGENT_ID" = "mifeng_corporate_hub" ]; then
    mkdir -p $WORKSPACE/lark_sync/{staging,state,logs}
  fi

  # 3b. 模板文件（每次覆盖）
  cp templates/AGENTS.md $WORKSPACE/
  cp templates/TOOLS.md $WORKSPACE/
  cp templates/HEARTBEAT.md $WORKSPACE/
  cp templates/IDENTITY.md $WORKSPACE/

  # 3c. 个人文件（仅首次写入，已有跳过）
  [ ! -f $WORKSPACE/SOUL.md ] && cp templates/SOUL.md $WORKSPACE/
  [ ! -f $WORKSPACE/USER.md ] && cp templates/USER.md $WORKSPACE/

  # 3d. 行业模板（仅添加新文件，不覆盖已有）
  for f in templates/domains/*.md; do
    fname=$(basename "$f")
    [ ! -f $WORKSPACE/domains/$fname ] && cp "$f" $WORKSPACE/domains/
  done
done
```

## 4. 同步线上配置

将根目录 `openclaw.json` 同步到服务器实际使用的 OpenClaw 配置位置。

当前线上配置中的 Agent 与 workspace 为：

- `assistant` -> `/root/.openclaw/workspace`
- `mifeng_corporate_hub` -> `/root/.openclaw/workspace/agents/mifeng_corporate_hub`
- `value_guo` -> `/root/.openclaw/workspace/agents/value_guo`
- `value_tianxiong` -> `/root/.openclaw/workspace/agents/value_tianxiong`
- `value_weichao` -> `/root/.openclaw/workspace/agents/value_weichao`
- `value_qingfeng` -> `/root/.openclaw/workspace/agents/value_qingfeng`
- `value_liaobin` -> `/root/.openclaw/workspace/agents/value_liaobin`

当前线上实际注册的 skills 以 `openclaw.json` 为准：

- `assistant`: `ontology`, `self-improving-agent`, `gateway`, `feishu_doc`, `feishu_chat`, `feishu_calendar`, `invest-pdf-parser`, `invest-news`, `invest-ingest`, `invest-doc-router`
- `mifeng_corporate_hub`: `ontology`, `self-improving-agent`, `feishu_doc`, `invest-pdf-parser`, `invest-doc-router`, `invest-news`, `invest-ingest`, `invest-lark-cli`, `invest-digest`, `invest-analysis`, `invest-review`
- `value_*`: `ontology`, `self-improving-agent`, `feishu_doc`, `invest-pdf-parser`, `invest-doc-router`, `invest-news`, `invest-ingest`, `invest-digest`, `invest-analysis`, `invest-review`

说明：

- 当前仓库中的 8 个 `invest-*` skills 已全部部署到 `~/.openclaw/workspace/skills/`。
- 当前线上真正注册到 agent 的技能集合以 `openclaw.json` 为准；新增或移除技能时，需同步更新该文件后再发布配置。

## 5. 校验 bindings 与 Feishu accounts

确认 `openclaw.json` 中以下三处保持一致：

- `acp.allowedAgents`
- `agents.list[*].id`
- `bindings[*].agentId` 与 `channels.feishu.accounts`

当前线上投资 agent 相关账号名应为：

- `mifeng_corporate_hub`
- `value_guo`
- `value_tianxiong`
- `value_weichao`
- `value_qingfeng`
- `value_liaobin`

## 6. 验证

```bash
for agent in mifeng_corporate_hub value_guo value_tianxiong value_qingfeng value_weichao value_liaobin; do
  echo "=== $agent ==="
  ls /root/.openclaw/workspace/agents/$agent/
done

ls /root/.openclaw/workspace/skills/invest-*/SKILL.md

ls /root/.openclaw/workspace/data/references/
ls /root/.openclaw/workspace/data/news/raw/
ls /root/.openclaw/workspace/data/
```

如果需要进一步校验配置内容，可检查：

```bash
python3 - <<'PY'
import json
with open('openclaw.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for agent in data['agents']['list']:
    print(agent['id'], agent['workspace'], agent['skills'])
PY
```

## 幂等性规则

| 文件类型 | 文件 | 部署策略 |
| --- | --- | --- |
| Template | `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md`, `IDENTITY.md` | 每次覆盖 |
| Personal | `SOUL.md`, `USER.md` | 仅首次写入，已有跳过 |
| Rule | `doc_types.json` | 每次覆盖 |
| Evolving Reference | `companies.json` | 合并，不直接覆盖 |
| Runtime | `views/`, `memory/`, `MEMORY.md` | 绝不覆盖 |
| Merged | `domains/*.md` | 添加新文件，不覆盖已有 |
