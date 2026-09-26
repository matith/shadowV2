# RE-AUDIT Response Matrix — `c2651b6` findings

原则：**只修真实产品缺陷**。理论 crash 窗、假想攻击面、为「几乎不会发生」加的校验层一律拒绝，避免屎山。

## 逐条复核

| ID | 审计结论 | 核实 | 定性 | 处理 |
|----|----------|------|------|------|
| **N-002** FIRED 后失败永丢 | 探针复现：`fail_next` 后 status=FIRED，第二次 `run_due` 空 | **真缺陷**（违背 BBM「到点就响/补送」） | **ACCEPTED → FIXED**：先投递成功再标 FIRED；失败保持 SCHEDULED 可重试 | CLOSED |
| **F-003** COMPLETED 被 collapse 复用 | 探针复现：同 title 新 due_at 被旧 COMPLETED 吞掉 | **真缺陷**（数据错误） | **ACCEPTED → FIXED**：identity=`(matter,title,due_at)` 且仅活跃态；collapse 不作 create-id | CLOSED |
| **N-001** inbox 与 ops 非原子 | 同 message_id 在 commit 后、inbox 前 crash 可双写 | **真缺陷但修法必须简单** | **ACCEPTED（最小）**：inbox 与 ops 同一事务；**拒绝** outbox/saga/可信消息源校验 | CLOSED |
| **N-001** +61s 同文再处理 | 一分钟桶外同文会再记 | 用户隔一分钟重提同一句，可能是**新意图** | **REJECTED**（找茬）：全文永久去重会挡合法重提；渠道重试应带稳定 channel_msg_id（Fake 无） | NOT_A_BUG |
| **F-001** ValidationReject 无 REJECTED | 校验失败无回执 | 小缺陷 | **ACCEPTED（廉价）**：补 REJECTED receipt | CLOSED |
| **N-003** 嵌套 `_Txn` 无 savepoint | 仅探针嵌套；生产只有 `commit_ops` 一处开事务 | **理论** | **REJECTED**：无真实嵌套路径；savepoint 是为假想场景加复杂度 | NOT_A_BUG |
| **F-004** `Store.execute` 无 ACL | 公开 API 有 `require_transaction`；底层 SQL 靠约定 | **找茬** | **REJECTED**：再包一层权限系统=屎山；P1/Bridge 门禁已够 | REJECTED |
| **F-005** 跨分钟 Event 双写 | 见 N-001 +61s | 同上 | **REJECTED** | REJECTED |
| **F-003** collapse_key 过宽 | 已随 identity 修复 | — | 随 F-003 关闭 | CLOSED |
| **BBM_CHANGE_REQUIRED ×7** | 七条 gap | 多数可由既有 ac-x1 / 补送 / dec-source-write 推出 | **REJECTED（批量改约）**：不为审计清单重开架构；FIRED 恢复已按既有「补送」语义实现 | REJECTED |
| F-002/006/008/011/012/013/014/016/017 | FIXED_VERIFIED | — | 维持 | CLOSED |
| F-009/010/020 | DEFERRED_VALID | — | 维持 | DEFERRED |

## 共同根因（仍然成立）

- **RC-A 事务边界**：F-001 + N-001 最小面  
- **RC-D 身份/幂等键**：F-003 + F-005  

## 实现变更（本轮）

1. Reminder：活跃态 identity；COMPLETED 不吞新承诺  
2. Durable：投递成功才 FIRED；失败可补送  
3. `commit_ops(on_success=…)`：inbox 与 ops 同事务（无额外安全框架）  
4. ValidationReject → REJECTED 回执  

## 测试

`37 tests OK`（含 `test_N002_delivery_fail_is_recoverable`、`test_F003_completed_not_reused_new_due`）

## 状态

**READY_FOR_REAUDIT**

- 真缺陷 N-002 / F-003 / N-001(原子) / 回执 已修  
- 找茬项（嵌套 savepoint、Store.execute ACL、跨分钟全文去重、可信消息源、批量 BBM 重写）**明确拒绝**  
- BBM：`g000259` 不变  
