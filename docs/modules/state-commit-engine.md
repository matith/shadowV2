# State / Commit Engine

## Purpose

把模型与用户的意图变成 **确定性、可审计、可幂等** 的 Canonical 状态变更，并处理纠正与冲突。

## In scope

- Proposal 规范化
- Patch（create_event / update_matter / create_fact / create_reminder / attach_file / ...）
- Correction（失效旧解释、记轨迹、更新当前态）
- Conflict 检测（重复 Matter、并发字段）
- Commit 原子提交与审计
- 高风险动作确认策略

## Out of scope

- 自然语言理解（Runtime）
- 原文存储细节（Source & Evidence 执行落盘）
- 提醒调度（Durable Task Runtime 执行未来触发）

## Expected outcomes

1. 一次输入可多账本扇出
2. 纠正后后续 Context 用新值
3. 重试不双写
4. 半失败可恢复，不产生悬空引用

## Failure signals

- 改写 Source
- 静默丢纠正
- 重复提醒/重复事项
- 高风险动作无确认

## Constraints

- 遵守 C1 / C2 / C8 / C9 / C12
- Ledger Operation 必须幂等键
