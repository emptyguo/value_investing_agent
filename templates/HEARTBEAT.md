# 心跳自检 (HEARTBEAT.md)

## 状态自查

1. **当前活跃主题**：确认目前的 Active Subject（活跃公司主题）是否依然有效？如果无效，返回 `HEARTBEAT_OK`。
2. **待持久化结论**：是否有需要写入 `views/` 的重要观点尚未保存？如果有，立即持久化。
3. **压缩预警**：如果 OpenClaw 提示即将进行 Compaction，请立即执行 Memory Flush，将短期记忆固化到 `memory/YYYY-MM-DD.md`。

## 约束提示

- 严禁在心跳中产生新的投资观点。
- 严禁在心跳中修改 `SOUL.md`。
- 仅用于状态同步、切题确认和压缩提醒。
- 如果无事发生，返回 `HEARTBEAT_OK`。
