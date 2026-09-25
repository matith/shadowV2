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

## 独立审核收边（对照 8a685d3 审阅，g000256）

| # | 审阅问题 | 处置 | 核实 |
| --- | --- | --- | --- |
| 1 | matter/event/people/knowledge 缺 contains | 已补 4 条 `personal-ledger-core contains` | contains **52→56** |
| 2 | Directive 未闭环到执行方 | 补 `durable/capability/projection/agent-runtime → directive-policy-evaluator` | 4 条 depends_on |
| 3 | 关键跨盒缺 Boundary Contract | 补 Durable→Commit、Capability→Source、两条 Policy 合同 | boundary **12→16** |
| 4 | Plan/AC 无执行绑定 | `plan-p0/p1/p2-v2` 填 affected_module_ids（23/10/9）+ 4 条 module 级 AC binding | planning 查询可用 |
| 5 | q-template-v2 blocking 与开工结论矛盾 | 标记 **RESOLVED / DEFERRED_NON_BLOCKING**，另开 `q-template-v2-deferred` blocking=false | 不再挡 P0 |
| 6 | Identity RC 像已实现 | 新增 `rc-identity-gate-status`：**ACCEPTED_BUT_NOT_IMPLEMENTED** | 与 q-project-desc-api 一致 |

**图快照：** 68 节点 / **91** 关系（contains 56, depends_on 13, produces_for 12, related_to 7, references 3）

## 夜间施工前收边（g000259）

| 项 | 处置 |
| --- | --- |
| `q-template-v2` blocking 字段不一致 | 无 update API；以 **dec-open-question-gate** 规定门禁=`status==OPEN && blocking==true`。RESOLVED 不阻塞 |
| P0 施工清单不全 | 新 **plan-p0-v3**（35 模块）补：model-adapter、working-context-compiler、raw-source-store、delivery-router、delayed-scheduled-runner、table-projection、ledger-router、change-receipt、dirty-tracker 等 |
| 范围锁 | P0 only；**不自动进 P1** |

**Identity 人工门禁（开工前核对，勿跳过）：**  
`repo=matith/shadowV2` · `root=D:\LIB\mimo\shadowV2` · `uuid=11dd729c-beaa-42cf-bad1-a06ab4f89e1b` · `generation>=g000256`

## 结论（修订）

> 六项收边 + 执行层两项收边已完成。在 **Identity 硬门禁仍 ACCEPTED_BUT_NOT_IMPLEMENTED**（人工核对替代）的前提下，允许按 **plan-p0-v3** 进入 P0 连续施工；**P0 通过后停止，不自动进入 P1**。
