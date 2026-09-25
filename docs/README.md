# 拾光 V2 — Blackbox Map

**Project root：** `D:\LIB\mimo\shadowV2`  
**Canonical source：** `blackbox/`（BBM RepositoryStore）  
**Architecture docs：** `docs/`（人读材料，非唯一真源）  
**Identity：** 见 [IDENTITY.md](IDENTITY.md)

## 阅读顺序

1. [IDENTITY.md](IDENTITY.md) — 项目身份门禁
2. [product-boundary.md](product-boundary.md) — 产品边界与原则
3. [architecture.md](architecture.md) — 顶层黑盒与关系
4. [ledgers.md](ledgers.md) — 多账本分类
5. [canonical-state.md](canonical-state.md) — 真源所有权与数据模型
6. [boundary-contracts.md](boundary-contracts.md) — C1–C12 边界合同
7. [modules/MODULE_INDEX.md](modules/MODULE_INDEX.md) — 模块清单与关系
8. [scenarios/acceptance.md](scenarios/acceptance.md) — 验收场景 A–G
9. [rollout.md](rollout.md) — P0/P1/P2 与第三方定位

## 一句话

> 拾光以 Personal Ledger 为长期现实状态核心；AI 是理解与操作 Ledger 的智能层，而不是 Ledger 本身。历史用 Event/Source 保留，Matter 维护当前状态；HOT/WARM/COLD/RAW 控成本；摘要增量维护；模型/记忆/表格皆可替换。

## 本目录不是

- 不是 P0 实现代码
- 不是 index.html 产品源
- 不是第三方 Agent/Memory 框架的配置文件
- 不是其他项目 Blackbox Map 的副本

## 导入 BBM

仅当 MCP handshake 已绑定 `shiguang-v2` / 本项目根目录后，才可将本目录内容导入 Workbench。  
导入前不得写入其他项目的 canonical。
