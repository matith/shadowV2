# Personal Ledger Core

## Purpose

维护用户生活与工作 **现实状态** 的唯一 Canonical 业务真源。AI 与用户共同读写同一账本，但解释层可纠正、可重建。

## In scope

- 多账本实体：Matter / Event / People / Knowledge / Product / File-Source / Directive / Archive
- 字段级状态（状态、摘要指针、下一步、层级、关联、生命周期、pin/importance）
- 通过 State/Commit Engine 接受 Patch 与 Correction
- 为 Context Engine / Summary / Projection 提供稳定读取

## Out of scope

- Embedding / Vector / 语义图谱真源
- 渠道收发
- 模型循环
- 表格产品私有结构
- 外部系统写入

## Expected outcomes

1. 同一事项多轮更新收敛同一 Matter
2. 一条消息可多账本引用
3. 历史在 Event，当前在 Matter
4. 归档保留极小可召回
5. 无 Projection 时仍可独立恢复

## Failure signals

- 重复 Matter 扩散
- 聊天记录被当作唯一状态
- Provider/表格覆盖真源
- 纠正后继续用旧值
- 归档后完全失联

## Constraints

- 遵守 C1–C12 合同
- 写入幂等
- Source 永不覆盖
- 摘要指针必须可下钻证据
