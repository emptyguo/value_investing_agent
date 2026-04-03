# Spec: Harness-Grade Investment Data Pipeline Rebuild

- **Date**: 2026-04-03
- **Status**: Draft (v3 - Final Harness Hardening)
- **Author**: Gemini CLI Agent
- **Topic**: Rebuilding `invest-news`, `invest-ingest`, and `invest-digest` skills.

## 1. 背景与核心痛点 (Revised)

根据基于 Superpowers 的两轮深度验证复核（v1 & v2 Audit），流水线必须解决：
1. **指纹设计缺陷**：哈希逻辑包含不稳定变量，需建立强一致性标准化规则。
2. **并发与幂等漏洞**：必须引入文件锁级别状态保护，防止多进程下数据污染。
3. **契约不一致**：CLI 接口需具备清晰的互斥与优先级逻辑。
4. **可观测性缺失**：Digest 需具备固定 Schema 支撑回归测试。

## 2. 设计原则 (Architectural Principles)

- **Atomic State Updates**: 使用文件锁（fcntl）与临时重命名确保 `state` 与 `logs` 的写安全性。
- **Hard-Coded Normalization**: 废除“可选”预处理，建立强制性的字符串剥离逻辑。
- **Contract-First CLI**: 使用互斥参数组（Mutex Groups）定义工具接口。

## 3. 详细规格 (Detailed Specs)

### 3.0 查询路由硬规则 (Report Query Routing Hard Rule)
- **适用场景**：当用户询问公司或竞品的季报/年报/财报指标时。
- **本地优先 (Mandatory)**：
    1. 必须先查询本地资料（`companies/{id}/` 已归档报告、解析结果、`references/`）。
    2. 若本地存在可用报告，**禁止**直接联网搜索替代本地结果。
- **联网回退 (Fallback Only)**：
    1. 仅当本地缺失报告或关键字段时，允许调用网络搜索补全。
    2. 所有回退结果必须打标 `[网络补充]` 并附 URL。
- **冲突处理**：本地已归档官方文件与网络结果冲突时，以本地归档官方文件为准，并记录冲突日志。

### 3.1 `invest-news` (采集层)
- **指纹标准化规则 (Strict)**：
    - `URL`：移除协议头(http/s)、移除 `www.`、**移除所有查询参数(?)与片段(#)**、移除尾部斜杠、转小写。
    - `TITLE`：移除所有空白符、移除标点符号、转小写。
- **CLI 契约**：
    - **Scope 组 (互斥)**：`--all` (遍历 companies.json) 或 `--subject <id>` (单公司)。
    - **Mode 参数**：`--mode {native|akshare|all}` (默认 `all`)。
    - **Date 参数**：`--date YYYY-MM-DD` (默认当前本地交易日，Asia/Shanghai)。
- **并发审计**：路径 `news/raw/metadata/run_{timestamp}_{run_id}.json` 记录单次运行。

### 3.2 `invest-ingest` (分流层)
- **并发写保护**：
    - 针对 `{DATA_DIR}/state/ingest_state.jsonl` 的所有写入操作，必须封装在 `with file_lock:` 上下文中。
    - 写入流程：`open .tmp -> write -> lock original -> move .tmp to original -> unlock`。
- **状态键值对**：`ENTITY_ID:FINGERPRINT:ACTION` 作为唯一索引。

### 3.3 `invest-digest` (智能层)
- **输出契约 (The Contract)**：
    - **文件路径**：`{DATA_DIR}/companies/{cid}/news/digest/{YYYY-MM-DD}_digest.json`。
    - **Schema 约束**：
        - `version` (string, required): 固定为 "1.0"。
        - `news_referenced_ids` (array, required): 包含本次摘要采纳的标准化指纹列表。
        - `metrics.coverage` (float, required): `referenced_count / total_available_items`。
        - `metrics.confidence` (float, 0-1, required): AI 自评。

## 4. 验证与对账 (Harness Verification)

- **守恒对账逻辑**：
  `Raw_Count (per run_id) == Ingested + Skipped (Dup) + Filtered (No-Map) + Errored`
- **回放断言 (Replay Assertion)**：使用 `harness_check.py` 喂入 JSONL 备份，断言生成的 `digest.json` 中的 `news_referenced_ids` 与原始记录一致。

## 5. 迁移与安全策略

1. **备份**：`cp -a {DATA_DIR} {DATA_DIR}_backup_v2`。
2. **迁移脚本**：提供 `migrate_v2_to_v3.py`，负责将旧 ID 重算为 Strict 模式下的新 ID。
3. **回滚**：若校验公式失败，执行安全回滚脚本：
   - `test -d "{DATA_DIR}_backup_v2" && mv "{DATA_DIR}" "{DATA_DIR}_failed_$(date +%Y%m%d_%H%M%S)" && mv "{DATA_DIR}_backup_v2" "{DATA_DIR}"`
   - 禁止在手工回滚中使用裸 `rm -rf`。
