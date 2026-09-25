# Top-level Blackboxes

> Seed 模块树是起点，不是不可改动的清单。下列划分已按职责清晰度做了必要收敛；实现时若发现边界错误，应修订本 Map，而不是打补丁。

```text
拾光 V2
│
├── 交互层（Interaction Layer）
├── 智能体运行时（Agent Runtime）        ← 可替换发动机
├── 上下文引擎（Context Engine）         ← 编译 Working Context
├── 个人账本核心（Personal Ledger Core） ← Canonical 状态
├── 记忆织物（Memory Fabric）            ← 派生索引 / 可插拔 Provider
├── 摘要系统（Summary System）           ← Capsule / 增量摘要
├── 来源与证据（Source & Evidence）      ← 原文与溯源
├── 状态提交引擎（State / Commit Engine）← Patch / Correction / Commit
├── 持久任务运行时（Durable Task Runtime）
├── 能力注册表（Capability Registry）
├── 投影层（Projection Layer）
└── 运维与配置（Operations）
```

> **命名约定：** Workbench 展示用中文名；模块 ID 保持英文 slug（稳定引用）。详细目的 / 真实场景验收 / 约束以 BBM Spec 为准。

---

## Interaction Layer

**Purpose：** 把多渠道输入规范化为拾光内部统一消息，并把回复送达用户。

**Boundary：**

- Channel 只负责：收消息、标识来源、发回复、附件、身份映射
- **不**把业务状态绑死在企业微信 / App / Web 等单一 Channel
- 不做 Ledger 业务写入；交给下游 Agent Turn / State Commit

**Contains：** Channel Gateway · Message Normalizer · Delivery

---

## Agent Runtime

**Purpose：** 可替换的模型循环发动机：Model → Context → Tools → Observation → Model。

**Boundary：**

- **不是**拾光架构的主人，只是发动机
- 模型可自由决定是否查 Ledger、读 Matter、读原文、建 Reminder、搜 Knowledge
- 所有能力必须经 Capability Registry 的明确 Tool Contract
- 不得绕过 State / Commit Engine 直接改 Canonical 真源
- 不得把某一种 Agent 框架（Codex / DeepSeek harness / 自建）写死为产品架构

**Contains：** Model Adapter · Tool Calling · Turn Orchestration

**实现候选（仅黑盒内部）：** 薄自建 harness、可插拔 Provider、或混合编排。选型不得反向定义产品边界。

---

## Context Engine

**Purpose：** 按需生成每次 Working Context，并决定信息路由。

**Contains：**

- **Context Compiler** — 结合当前消息、活跃 Matter、相关 People、时间窗、重要度、Directive、Token Budget，编译 Working Context
- **Ledger Router** — 判断新信息应进入哪些 Ledger（可主模型自判，可轻量辅助）
- **Memory Retrieval** — 从 Memory Fabric / Ledger 取回相关内容
- **Context Budget** — 长期数据增长不得导致上下文无限膨胀

**Boundary：** 只读 Canonical + Derived，不拥有业务真源。

---

## Personal Ledger Core

**Purpose：** 用户现实状态的唯一 Canonical 业务真源。

**Contains（多 Expert）：**

- Matter Ledger
- Event Ledger
- People Ledger
- Knowledge Ledger
- Product / Business Ledger
- File / Source Ledger
- Directive Ledger
- Archive Ledger

**Boundary：**

- 表格、向量库、第三方 Memory **都不是**真源
- 一个信息可被多个 Ledger 引用
- 写入须经 State / Commit Engine
- Source 永不被 AI Interpretation 覆盖

---

## Memory Fabric

**Purpose：** 检索加速与长期降温，可插拔。

**Contains：** HOT / WARM / COLD · Semantic Index · Relation Index · Memory Provider · Background Consolidation

**Boundary：**

- Provider（Mem0 / Graphiti / 本地 Basic…）只负责 semantic recall、实体/时间关系、联想检索、模式发现
- **Provider 不拥有业务真源**，可整体替换重建
- Background AI 不得篡改 Source

---

## Summary System

**Purpose：** 维护 AI 可稳定读取的 Context Capsule，并保证增量成本。

**Contains：** Context Capsule · Incremental Summary · Tree Propagation · Dirty Tracking

**规则：**

- 禁止每个新事件都重读全历史再总结
- `Old Capsule + New Patch → New Capsule`
- 子事项变化只向上递归传播；某级摘要未变则停止
- Capsule 是 Derived，可从 Source + Events + Patch 轨迹重建

---

## Source & Evidence

**Purpose：** 保存原文、附件与溯源链。

**Contains：** Raw Source · Attachment · Provenance · Version

**规则：**

```text
Source
  ↓
Interpretation (Event / 分类 / 摘要 / 推论)
  ↓
Ledger State
```

用户纠正不修改原 Source，而是失效旧 Interpretation、记 Correction、更新 Current State。

---

## State / Commit Engine

**Purpose：** 把模型输出的确定性操作安全落到 Canonical。

**Contains：** Proposal · Patch · Correction · Conflict · Commit

**规则：**

- 一次 Agent Turn 可同时产出 Reply + Ledger Operations（create_event / update_matter / create_fact / create_reminder / attach_file…）
- 程序执行确定性操作，而不是再串行多次 LLM
- Correction 是一级能力：纠正、撤销错误推论、重关联、降权、删 Derived Memory、保留审计轨迹
- 高风险动作走确认策略；常规整理不打断用户

---

## Durable Task Runtime

**Purpose：** 保证“未来一定会发生”。

**Contains：** Reminder · Delayed Task · Scheduled Task · Resume

**规则：** Agent 决定要做什么；Durable Runtime 保证它真的在未来发生。不依赖模型“记住以后做”。

---

## Capability Registry

**Purpose：** 统一暴露工具能力，保持 Runtime 可替换。

**Contains：** Native Tools · MCP · External Service · Permission

**预留能力（不提前施工）：** 图片、OCR、语音、PDF、Word、PPT、Excel、邮件、日历、浏览器、企业微信、文件夹、网盘、PC 工作上下文、自动归档、产品知识库、人际关系、长期项目、工作流、Background Agent、多模型/本地模型、第三方插件。

---

## Projection Layer

**Purpose：** 人机共享操作面；可更换外部表格产品。

```text
Canonical Ledger
      │
      ▼
Projection Adapter
      │
 ┌────┼────┐
 ▼    ▼    ▼
WPS  Web  App
```

**边界：** WPS / 自研 Web / Desktop 都不是不可替换核心。Canonical 可在无 Projection 时独立存在。

---

## Operations

**Purpose：** 可运维、可恢复、可换模。

**Contains：** Diagnostics · Trace · Backup · Migration · Model Configuration · Provider Configuration

---

## 关系总览（逻辑）

```text
Interaction Layer
       │ messages
       ▼
Agent Runtime ──tools──► Capability Registry
       │ turn
       ▼
Context Engine ──reads──► Personal Ledger Core
       │                  Memory Fabric
       │                  Summary System
       ▼
State / Commit Engine ──writes──► Personal Ledger Core
       │                         Source & Evidence
       │                         Durable Task Runtime
       ▼
Projection Layer ◄──reads── Personal Ledger Core

Operations 横切全部模块
```
