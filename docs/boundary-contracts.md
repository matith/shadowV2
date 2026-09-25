# Boundary Contracts (关键跨黑盒语义)

合同定义的是 **边界语义**，不是某次实现细节。破坏合同即架构错误。

---

## C1 — Source Immutability

**Between：** Source & Evidence ↔ 所有 Interpretation 消费者

- Source 内容创建后不可被 AI 覆盖
- 分类、摘要、实体、标签、推论均可变且可失效
- 用户纠正只能创建新 Interpretation / Correction，不能改原文
- Projection 展示“原话”时必须读 Source 或 Source 的忠实引用

**Failure：** 任何“改写原消息以符合当前理解”的行为都视为 bug。

---

## C2 — Canonical Write Path

**Between：** Agent Runtime / Memory Fabric / Projection ↔ Personal Ledger Core

- 唯一合法写路径：State / Commit Engine
- Runtime 只能提出 Ledger Operations，不能直接改账本文件
- Memory Provider、表格、向量库不得回写真源
- 高风险动作需确认；常规 patch 可自动提交

**Failure：** 绕过 Commit 的写入、或 Provider 覆盖 Canonical，均为阻断级问题。

---

## C3 — Event/Matter Separation

**Between：** Event Ledger ↔ Matter Ledger

- Event 追加历史；Matter 维护当前状态
- 禁止把 Matter 一行做成无限历史堆
- 多日同一事项必须收敛到同一 Matter（去重 / 关联），不默认新建重复 Matter

**Failure：** 同一事项目标被反复新建，或用 Event 永久替代 Matter 状态。

---

## C4 — Capsule Incrementality

**Between：** Summary System ↔ Matter Tree

- 更新必须是 `old + patch`，禁止默认全量重述
- 父级摘要只接收子级 dirty 传播
- 传播在“摘要无变化”处停止
- Capsule 必须带 Evidence 指针

**Failure：** 每条消息都重写全部摘要，或摘要无法追溯 Source。

---

## C5 — Context Compiler Budget

**Between：** Context Engine ↔ Agent Runtime

- Working Context 按消息与预算生成
- 长期数据增长不得导致单次上下文线性膨胀
- HOT/WARM/COLD/RAW 按 Recency + Lifecycle + Relevance + Importance + Pin + Activity，而非纯时间

**Failure：** 每次对话塞入全部历史，或纯时间导致重要长期事项被误冷。

---

## C6 — Replaceable Runtime & Provider

**Between：** Agent Runtime / Memory Fabric ↔ 外部实现

- 模型、Agent harness、Memory Provider、表格产品均可替换
- 替换不得要求重写 Personal Ledger Core
- 第三方术语不得泄漏为产品主模型

**Failure：** 业务真源依赖 Mem0/Graphiti/WPS/Codex 私有结构才能恢复。

---

## C7 — Durable Delivery

**Between：** Agent Runtime ↔ Durable Task Runtime

- 模型可决定创建 reminder/delay/schedule
- 触发与恢复由 Durable Runtime 保证
- 进程重启、会话结束不得导致任务静默丢失

**Failure：** “三天后提醒”只存在于模型上下文或聊天记录。

---

## C8 — Multi-Ledger Fan-out

**Between：** Ledger Router ↔ Personal Ledger Core

- 单条输入允许同时落到多个 Ledger
- 用引用连接，不重复拷贝原文
- Router 错误可通过 Correction 修复，不作为唯一分类锁

**Failure：** 强制单分类丢掉人物/资料/事项中的其他维度。

---

## C9 — Correction First-class

**Between：** 用户输入 ↔ State / Commit Engine

- 纠正必须可表达、可提交、可审计
- 后续 Context 必须采用纠正后状态
- 不得静默丢弃纠正，也不得永久保留错误权重

**Failure：** 纠正后系统继续用旧值，或改写了 Source。

---

## C10 — Projection Non-Ownership

**Between：** Projection Layer ↔ Personal Ledger Core

- 表格是共享操作面，不是唯一真源
- 外部表产品可换
- 用户直接改 Projection 应映射为 Ledger Patch，而不是让 WPS 变成真源

**Failure：** 无 WPS/无 Web 时业务状态不可恢复。

---

## C11 — Archive Recall

**Between：** Archive Ledger ↔ Context Engine

- 归档保留极小 capsule + 指针
- 提起旧事项时能先命中“有这么回事”，再展开
- 展开是按需的，不把全历史预热进 HOT

**Failure：** 归档后完全不可召回，或召回即全量灌入上下文。

---

## C12 — Idempotent Operations

**Between：** 全部写入方 ↔ State / Commit Engine

- Ledger Operation 幂等
- 部分成功可续传
- 重复投递（渠道重试、Agent 重跑）不产生重复 Matter/Reminder（或可归并）

**Failure：** 网络重试导致重复提醒、重复事项、重复账本行。
