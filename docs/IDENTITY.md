# Project Identity Gate — 拾光 V2

## Gate result

| Field | Value |
| --- | --- |
| Project name | 拾光 V2 (ShiGuang V2) / Workbench display name currently `shadowV2` |
| Project UUID | `11dd729c-beaa-42cf-bad1-a06ab4f89e1b` |
| Project key | `shiguang-v2` |
| Project root | `D:\LIB\mimo\shadowV2` |
| Canonical blackbox source | `D:\LIB\mimo\shadowV2\blackbox\` |
| Architecture docs (non-canonical) | `D:\LIB\mimo\shadowV2\docs\` |
| Repository generation | `g000002` after top-level map import |
| Gate status | **INDEPENDENT** — 不与任何既有项目共享模块/状态/历史/acceptance |

## Binding note (MCP)

当前会话若 `blackboxmap` MCP handshake 指向其他项目（例如 `blackboxmap` / Project Graph Workbench）：

1. **禁止**在该项目上写入拾光模块、关系、合同或 Observation。
2. **禁止**继承该项目的 modules、lifecycle、acceptance、known problems。
3. 拾光架构真源是本目录下的 Blackbox Map，不依赖错误绑定的 Workbench 数据库。
4. 只有在 MCP 显式绑定到 `shiguang-v2` / `D:\LIB\mimo\shadowV2` 之后，才允许经 BBM 工具做 canonical 提交。

## Inheritance policy

- 不继承其他项目的模块图、revision、failure_signals、acceptance。
- 不把第三方产品的架构（Codex / DeepSeek harness / Mem0 / Graphiti / WPS / PydanticAI 等）当作拾光产品边界。
- 第三方只允许作为 **某个黑盒内部的候选实现**，可替换。

## Reader contract

新 Agent 只需阅读 `blackbox/` 下文档，即可回答：

- 拾光是什么、不是什么
- 真源状态归谁
- 信息如何进入 Ledger / Matter / Event / Source
- Agent Runtime 与 Core 的边界
- 当前应实现到哪一步、如何验收、如何扩展
