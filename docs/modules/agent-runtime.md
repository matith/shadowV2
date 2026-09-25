# Agent Runtime

## Purpose

可替换的模型发动机：把 Working Context + Tools 交给模型，产出 Reply 与 Ledger Operations。它是润滑剂，不是产品主人。

## In scope

- Model Adapter（多 Provider：DeepSeek / 本地 / 订阅型 harness / 未来模型）
- Tool Calling（只经 Capability Registry）
- Turn Orchestration（单轮内理解→操作→回复；可批量 burst）

## Out of scope

- Canonical 账本存储与所有权
- 长期摘要算法实现细节（归 Summary System）
- 渠道 UI
- 强制固定分类器/决策树工作流

## Expected outcomes

1. 换模型不必改 Personal Ledger Core
2. 单 Turn 可同时产生 Reply + 确定性 Ledger Ops
3. 模型可自行选择读 Capsule / Event / Source / 工具
4. 边界外未知不阻断本轮（记 Feedback）

## Failure signals

- 业务状态写死在 harness 私有会话里
- 绕过 Commit 直接改账本
- 每条消息串行 4–5 次模型调用才完成一次记账
- 用第三方框架概念反向命名拾光模块

## Constraints

- 遵守 C2 / C5 / C6 / C7 / C12
- 实现候选（自建薄 harness、Codex、DeepSeek harness、混合）只在本模块内评估
