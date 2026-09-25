# P0 / P1 / P2 Rollout

> 规划完整，实施渐进。P0 很小，但接口与真源边界按长期产品预留。

---

## P0 — 证明 Ledger 架构成立（最小真实闭环）

**目标场景：** Scenario A（日常承诺）+ Scenario C 的最小多轮 + Scenario E 的最小纠正。

**范围：**

1. 单一消息入口（可先 CLI / 本地 Web 对话）
2. Event 写入
3. Matter 创建/更新（可先单层，不强制 UI 树）
4. People 最小字段
5. Reminder 创建 + 到点触发（Durable 最小实现）
6. Context Capsule 最小增量维护
7. State/Commit：允许单 Turn 同时 Reply + Ledger Ops
8. 极简 Inspector/表格：看 Matter、摘要、状态、子项、人物、提醒、Events、Files
9. Source 保存 + 纠正不改原文

**明确不做（但接口不挡死）：**

- 全渠道接入
- 向量检索/Graphiti/Mem0
- OCR/语音/Office 全格式
- 企业微信/邮件/日历
- 复杂权限
- 背景智能整库整理
- WPS 深度集成

**P0 验收：** Scenario A 端到端可演示；询问能恢复状态；提醒能到；纠正后用新值。

---

## P1 — 从“能记”到“好用”

1. Matter 父子层级 + 摘要树传播（Scenario D）
2. Archive 最小召回（Scenario F）
3. Knowledge / Product Ledger 正式启用（Scenario B）
4. 多 Ledger 扇出（Scenario G）
5. File 附件与证据下钻完善
6. Conversation Burst 合并
7. Context Compiler 预算与 HOT/WARM/COLD（即使实现很朴素）
8. 备份 / 迁移最小工具
9. Projection：更好用的表格编辑

---

## P2 — 长期产品形态

1. 多 Channel（企微、App、分享、浏览器扩展、语音、邮件）
2. Capability Registry 全面接入（OCR、Office、日历、浏览器、网盘、PC 上下文…）
3. Background Intelligence（夜间整理、去重、模式发现、降温、归档）
4. 可插拔 Memory Provider 对比与切换
5. 多模型 / 本地模型策略
6. 工作流与外部 MCP
7. 更强权限策略（仍避免官僚化）
8. 多 Projection（WPS/自研/未来 App）

---

## 实施纪律

1. **P0 不等于 P0 架构。** 不为过 P0 把 Core 写死成聊天日志。
2. **每加能力先问：** 是否破坏 C1–C12 合同？是否污染 Canonical？
3. **第三方选型**只允许落在 Agent Runtime / Memory Fabric / Projection / Capability 内部。
4. **先合同后代码。** 跨模块语义先更新 `contracts/`，再实现。
5. **验收看场景，不看“接了多少框架”。**

---

## Agent Runtime / Memory / Projection 候选定位（非架构）

这些 **不是** 拾光整体架构，只是黑盒内实现菜单：

| 黑盒 | 候选思路 | 架构要求 |
| --- | --- | --- |
| Agent Runtime | 薄自建 harness；或 Provider 适配 Codex/DeepSeek/本地模型；或混合 | 可替换、工具走 Registry、不得直写真源 |
| Memory Fabric | 本地 Basic / Mem0 / Graphiti / 自建索引 | 可丢可重建、不拥有真源 |
| Projection | 自研 Web 表、WPS 多维表、Desktop | 经 Projection Adapter |
| Capability | MCP / 原生工具 / 外部服务 | 明确 Tool Contract + Permission |

**结论倾向（供 P0 决策，默认可推导）：**  
采用 **薄编排 + 明确 Tool Contract** 的 Agent Runtime 边界；模型与 harness 可换。P0 甚至可以先用单一模型 Provider 把 Ledger 闭环跑通，不必先定终身 harness。
