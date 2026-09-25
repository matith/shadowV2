# BBM 规划收口 — 求证与处置（对照第三方审阅）

## 求证结果（逐条，非采信）

| # | 审阅主张 | 求证 | 处置 |
| --- | --- | --- | --- |
| 1 | Project Identity 未进 canonical | **属实**：`project.description=""`，bindings=[]，仅 docs 有 | 记入 **dec-identity** + **rc-identity-gate** + **ev-docs-identity**；仍缺稳定 `project.description` 写 API → **q-project-desc-api** |
| 2 | Planning Ledger 为空 | **属实**：plans/decisions/criteria/evidence 全 [] | 已写入 4 Plan、8 Decision、15 AC（A–G+X1–X8）、3 Question、3 Evidence、1 RC、scopes=p0/p1/p2/project |
| 3 | Summary `basis_revision=2` 落后 `current=3` | **属实**：12 模块全部落后 | 已全部刷新；抽查 **stale_count=0** |
| 4 | 只有 12 大黑盒，子系统塞 custom 字符串 | **属实**：Matter Ledger 等非 Node | 已拆 **56 个子黑盒** + `contains` 关系；**nodes=68**；全 `PLANNED` |
| 5 | 缺 Durable→State Commit | **属实**：无该边 | 已加边 + 子黑盒 `task-action-bridge` |
| 6 | 缺 Effect Receipt | **属实** | 已加 `effect-receipt-emitter/store` + 边；Decision **dec-effect-receipt** |
| 7 | 跨渠道 Identity 无 owner | **属实** | 已加 `channel-identity-mapping` |
| 8 | Directive 未覆盖提醒投递 | **属实** | 已加 `directive-policy-evaluator` + Decision **dec-directive-enforcement** |
| 9 | File Ledger vs Source 重叠 | **属实** | 已加 `file-ledger`（语义目录）与 Source 子黑盒（bytes/版本）；Decision **dec-file-source-split** |
| 10 | custom 无 schema | **属实**：`custom: object` | 记为 **q-template-v2**（需 architecture-module-v2） |
| 11 | 证据/追问过约束 | **属实**（agent-runtime / source-evidence 约束过死） | 已改：证据仅约束「个人状态/资料/Ledger/文档事实」；「最多 3 问」标为 UX 启发式 |

## 当前 canonical 快照（g000233）

- Nodes **68**（12 父 + 56 子）
- Relations **83**
- Planning：4 plans / 8 decisions / 15 acceptance / 3 questions / 3 evidence / 1 requirement-change
- Summary lag：**0**

## 仍未完全闭合（诚实记录）

1. `project.description` / planning bindings 的 **Identity 结构化字段**仍无专用写 API（用 decision+RC+evidence 固化意图）。
2. `general-module-v2` 模板未建（q-template-v2）。
3. 子黑盒 specs 为规划级摘要，详细验收可随实现再加深。
4. 全部子黑盒 lifecycle=PLANNED，**未施工业务代码**。

## 结论

> 房屋图纸级规划已进入 canonical；P0 可开工「日常承诺」装修，但 Identity 硬门禁的原生 schema 与 template-v2 仍需补。
