# 拾光 V2 / shadowV2

长期陪伴用户的 **Personal Ledger Agent**：维护生活与工作现实状态账本，而不是聊天流水。

## 这个仓库是什么

| 路径 | 内容 |
| --- | --- |
| `docs/` | 产品边界、架构、Ledger、数据模型、交互审计、验收与分期 |
| `blackbox/` | **BBM Canonical**（模块/关系/边界合同/修订），Workbench 可打开 |
| `scripts/` | 写入 BBM 规格与交互合同的辅助脚本 |

## 核心原则（摘）

1. 模型负责理解，Core 负责持续性  
2. 历史（Event）与当前状态（Matter）分离  
3. Source 与 Interpretation 分离；纠正不改原文  
4. 表格是投影，不是唯一真源  
5. 边界严格，边界内部让模型自由  
6. 摘要增量维护；归档 ≠ 遗忘  

## 顶层黑盒

交互层 · 智能体运行时 · 上下文引擎 · **个人账本核心** · 来源与证据 · 状态提交引擎 · 摘要系统 · 记忆织物 · 持久任务运行时 · 能力注册表 · 投影层 · 运维与配置

## 阅读顺序

1. [docs/README.md](docs/README.md)  
2. [docs/product-boundary.md](docs/product-boundary.md)  
3. [docs/architecture.md](docs/architecture.md)  
4. [docs/interaction-audit.md](docs/interaction-audit.md)  
5. Workbench 查看 `blackbox/` 中模块 Spec 与 Boundary Contract  

## 项目身份

- 项目根：本仓库根目录  
- Canonical：`blackbox/`  
- 详见 [docs/IDENTITY.md](docs/IDENTITY.md)  
