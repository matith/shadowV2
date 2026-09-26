# Independent Audit Remediation Matrix — shadowV2

Audit baseline: HEAD `2db5e17` · BBM `g000259` · plan-p0-v3  
Remediation HEAD: see git log after this commit  
Final status: **READY_FOR_REAUDIT**（不自称 FINAL PASS）

## Method

1. 每条 Finding 用 `scripts/audit_repro.py` + `tests/test_audit_remediation.py` 最小确定性复现  
2. 对照 BBM（dec-source-write / dec-durable-writeback / ac-e / ac-x1 等）  
3. 分层修复，不按编号打补丁  
4. 共同根因合并记录

---

## Finding Matrix

| Finding | Sev | Verification | Root Cause | BBM Change | Implementation Change | Tests | Final Status |
|---------|-----|--------------|------------|------------|----------------------|-------|--------------|
| **F-001** 多 op Commit 非原子 | P0 | REPRODUCED → FIXED | 下层 Ledger/reminder 路径内嵌 `store.commit()`，逃出 `_Txn` 边界 → 半提交 | 无（BBM 已要求原子） | `Store.in_transaction` + `commit()` 事务内 no-op；`_Txn` 唯一 owner BEGIN/COMMIT/ROLLBACK；Ledger 只 mutate；失败发 REJECTED receipt | `test_F001_multi_op_rollback_leaves_zero_residue` `test_F001_retry_same_op_ids_after_rollback` | **CONFIRMED → CLOSED** |
| **F-002** Correction.field 动态 SQL | P0 | REPRODUCED → FIXED | 无字段契约；f-string 列名 | 明确 `CORRECTABLE_FIELDS` 白名单（matter/reminder）+ 固定 `REMINDER_COLUMNS` 映射 | OpValidator + CorrectionApplier 双重校验；非法字段 deterministic `ValidationReject` | `test_F002_illegal_field_rejected` `test_F002_wrong_target_kind` `test_F002_legal_field_whitelist` | **CONFIRMED → CLOSED** |
| **F-004** 写入口非唯一 | P0 | REPRODUCED → FIXED | Ledger/P1 API 可裸写业务表 | 无（dec-source-write 已规定） | `require_transaction()` 门禁；P1 `set_parent/knowledge/archive` 改走 Op + `P1WriteBridge` | `test_ledger_direct_write_rejected` `test_F004_p1_requires_bridge` `test_set_parent_goes_through_commit` | **CONFIRMED → CLOSED** |
| **F-011** 纠正不失效旧解释 | P0 | REPRODUCED → FIXED | proposer 不传 `interp_id`，无兜底失效 | 无（ac-e 已要求） | CorrectionApplier 自动 `INVALIDATED` 本 matter 的 ACTIVE 解释 | `test_F011_correction_invalidates_interps` | **CONFIRMED → CLOSED** |
| **F-003** 同文双 Reminder | P1 | REPRODUCED → FIXED | Reminder 无 identity 去重 | 明确 identity=`(matter_id,title,due_at)` 或 `collapse_key` | `CREATE_REMINDER` 复用已有非 CANCELLED 记录 | `test_F003_duplicate_reminder_same_text` | **CONFIRMED → CLOSED** |
| **F-005** message 无重放闸 | P1 | REPRODUCED → FIXED | `message_id=new_id` 每次新 | 输入幂等属 ac-x1 | 确定性 `msg_<hash(channel,user,text,ts-bucket)>` + `message_inbox` 闸 | `test_F005_same_message_replay` | **CONFIRMED → CLOSED** |
| **F-006** Directive 优先级 | P1 | REPRODUCED → FIXED | `and`/`or` 混用使 `hour<8` 误伤 reply | 无 | `kind=="notification" and (hour>=22 or hour<8)` | `test_F006_parentheses` | **CONFIRMED → CLOSED** |
| **F-013** dirty 只标最后 matter | P1 | REPRODUCED → FIXED | 批次只取 `matter_ref` | 无 | `matter_ids` 集合，批内全部标记 | `test_F013_all_matters_marked` | **CONFIRMED → CLOSED** |
| **F-017** mark_fired 先于 policy | P1 | CONFIRMED → FIXED | run_due 先 fire 再裁决 | 无 | policy 先；defer 走 SNOOZE Op，`fire_count` 不加 | `test_F017_policy_before_fire_defer_no_fire_count` | **CONFIRMED → CLOSED** |
| **F-014** LedgerRouter 死代码 | P1 | CONFIRMED → FIXED | `route()` 0 调用 | 无 | ingest 接入 soft route，写入 turn.meta | Scenario C 路径覆盖 | **CONFIRMED → CLOSED** |
| **F-012** find_similar 未接 | P1 | CONFIRMED → FIXED | 创建路径不查重 | ac 要求相似合并 | `CREATE_MATTER` 默认 `find_similar` 复用（`force_new` 可关） | P1 create + Scenario C | **CONFIRMED → CLOSED** |
| **F-016** effect receipt 可覆盖 | P1 | CONFIRMED → FIXED | `INSERT OR REPLACE` | dec-effect-receipt | insert-only；success 必须带 external_ref | `test_effect_receipt_on_delivery` | **CONFIRMED → CLOSED** |
| **F-008** 运行时直写 reminder | P1 灰区 | CONFIRMED → CLOSED | mark_fired/defer 裸写 | dec-durable-writeback | fire/defer 产生 Op 走 State/Commit | `test_restart_then_fire_once` | **CONFIRMED → CLOSED** |
| **F-007** 测试缺失败路径 | P1 | CONFIRMED → FIXED | 只测 happy path | 无 | 补齐 rollback/注入/重放/去重/门禁等 | `test_audit_remediation.py` 35 tests total | **CONFIRMED → CLOSED** |
| **F-009** Identity 默认构造 | P2 | OBSERVED | `identity_from_repo_root` 填期望 UUID | 门禁对错误 UUID 有效 | 不改产品用途；审计可要求外部绑定 | identity tests 保持 | **RECLASSIFIED → DEFERRED** |
| **F-010** RuleBasedModel 局限 | P2 | REPRODUCED | 模型润滑剂边界 | 已区分 Core/Model | 不在本轮修 NL；ModelAdapter 可替换 | fixture 回归保持 | **RECLASSIFIED → DEFERRED** |
| **F-018** already_fired 死条件 | P2 | PARTIAL | status 过滤已覆盖主路径 | 无 | fire 走 Op 后幂等由 op_id+status 保证 | restart fire test | **OBSOLETE → CLOSED by F-008 path** |
| **F-020** inbound STUB | P2 | CONFIRMED | Fake only | P0 允许模拟边界 | 不扩 P2 真实渠道 | — | **DEFERRED (P2 scope)** |
| **F-008～F-010 其余 P2** | P2 | 按任务书 | — | — | **不抢修** | — | **DEFERRED** |

---

## Shared root causes（不伪装成独立补丁）

1. **RC-A 事务所有权缺失** → F-001、F-008（部分）、F-013（脏标记时机）  
2. **RC-B Canonical 写路径无门禁** → F-004、F-012、P1 旁路、F-014（假完成）  
3. **RC-C Correction 缺少字段/解释契约** → F-002、F-011  
4. **RC-D 身份/幂等键未定义** → F-003、F-005、F-018  

---

## BBM Change

本轮 **未修改 BBM canonical**。审计要求的语义均可由现有 Contract 推出：

- dec-source-write / dec-durable-writeback / dec-effect-receipt  
- ac-x1 幂等 / ac-e 纠正 / ac-x7 摘要一致  

实现侧将 `CORRECTABLE_FIELDS`、reminder identity、message replay 视为 **Contract 落地细节**，已写入代码与测试；若审计要求升格为正式 Boundary 字段，可在下一 generation 用最小 revision 固化。

---

## Claim re-verification

| Claim | After remediation |
|-------|-------------------|
| 18 tests VERIFIED | **35 tests OK**（含失败路径） |
| Scenario A/E | PASS |
| T0–T5 | PASS |
| Source immutable | PASS |
| No false success | PASS（失败发 REJECTED，成功仅 commit 后） |
| Reminder restart/idempotency | PASS |
| Evidence chain | PASS |
| P0 regression | PASS |
| Scenario C | **PASS**（收敛 + 路由接入） |
| State/Commit 唯一写 | **PASS**（require_transaction + P1 bridge） |
| 同 Matter 收敛 | **PASS**（find_similar + message identity） |
| Runtime Identity | 门禁有效；默认构造 **DEFERRED** |

---

## Verdict after remediation

```
P0:  PASS candidate → READY_FOR_REAUDIT
P1:  findings closed or explicitly deferred
Overall: READY_FOR_REAUDIT
```

**最终 commit SHA:** 见 git（本文件所在 commit）  
**BBM canonical generation:** `g000259`（本轮无 generation 推进）
