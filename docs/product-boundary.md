# 拾光 V2 — Product Boundary

## 1. 产品本质

拾光是 **长期陪伴用户、持续维护用户现实状态与个人信息账本的大模型 Agent**。

它服务的目标不是“记住所有聊天”，而是：

> **让用户不必自己一直记住生活、工作与长期事项的全部上下文。**

### 拾光是

- Personal Ledger（个人现实状态账本）的维护者
- 历史（Event / Source）与当前状态（Matter）的分层系统
- 模型理解与操作的智能层，外加可持久化的 Core
- 人机共享的表格式操作面（Projection）
- 可替换模型 / 可插拔记忆 Provider 的长期产品骨架

### 拾光不是

- 普通聊天机器人 / 纯 RAG
- 第二大脑式的“全量聊天记忆”
- 向量库产品
- 任务管理器产品本身
- 多 Agent 编排框架产品
- 文档管理器 / 提醒工具 / 企业微信机器人本身
- 某个第三方 Memory / Table / Agent 框架的封装壳

---

## 2. 核心原则（架构约束）

1. **模型负责理解，Core 负责持续性。**
2. **历史与当前状态必须分离**（Event vs Matter）。
3. **Source 与 Interpretation 必须分离。**
4. **表格是人机共享操作面，不是唯一数据真源。**
5. **Memory AI / Provider 是插件，不是 Core。**
6. **上下文按需编译，不无限累积。**
7. **摘要增量维护，不反复扫描完整历史。**
8. **Matter 可层级化，摘要沿层级增量传播。**
9. **不同类型信息进入不同 Ledger；一条信息可关联多个 Ledger。**
10. **Correction 是正常工作流。**
11. **归档不等于遗忘。**
12. **重要摘要可追溯 Source。**
13. **模型和第三方框架必须可替换。**
14. **不为架构纯洁度约束模型正常发挥。**
15. **边界严格，边界内部让模型自由。**

---

## 3. 大模型是“润滑剂”，不是工作流奴隶

允许：

```text
用户自然表达
→ 能力足够的模型
→ 根据上下文判断
→ 选择合适的 Ledger / Tool / Capability
→ 完成处理
```

严格控制的是：

- 数据边界
- 工具语义
- 状态所有权
- 权限与高风险动作
- 数据来源与可追溯性
- 持久化与关键写入

不规定模型每一步怎样思考。模型能力提高后，拾光应自然变强，而不必重写产品架构。

---

## 4. Canonical vs Non-Canonical

### Canonical（拾光真源，必须持久、可审计）

- Personal Ledger 各账本中的实体与字段
- Raw Source / Attachment / Provenance
- Event 记录与 Matter 当前状态
- Directive / Policy
- Durable Task（提醒、延迟任务）
- Correction / 纠正轨迹
- Archive Capsule（极小召回摘要）
- 已提交的 Summary Patch 轨迹（用于重建 Capsule）

### Derived / Projection / Provider（可重建，不是真源）

- Embedding / Vector DB
- Semantic / Relation Index
- HOT / WARM / COLD 分层缓存
- Context Capsule（由 Source + Events + Patch 增量维护，可重建）
- Chat session / Agent run logs
- WPS 多维表格、Web UI、Desktop UI
- Mem0 / Graphiti / 其他 Memory Framework
- 任何第三方表格或协作产品

必要时 Derived 全部可以丢掉并重建，不得反向覆盖 Canonical。

---

## 5. 人机共享面

用户应能打开类似多维表格的 Projection，看见：

- 事项、状态、摘要、下一步
- 子事项、关联人物、附件
- 历史变化、原始 Source、纠正记录

AI 通过结构化 Tool 读写同一 Ledger；表格只是 Projection。

---

## 6. 权限与高风险动作

拾光是个人系统，不过早设计复杂 RBAC。

需要用户确认的典型动作：

- 删除数据
- 对外发送消息
- 修改外部文件
- 涉及金额
- 对外提交

不应频繁确认的常规动作：

- 更新摘要
- 整理 Matter
- 建立关联
- 内部归档（可撤销）
- 创建内部提醒

---

## 7. 长期产品形态 vs 渐进实施

- **规划可以完整，实施必须渐进。**
- P0 只装修一个房间，但房子总体结构按长期产品设计。
- 后续能力（语音、OCR、企业微信、日历、邮件、MCP…）只预留接口，不提前施工。
