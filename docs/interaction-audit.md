# 黑盒间交互审计（Interaction Audit）

审计视角：**交接面**——谁把什么交给谁、失败会怎样、有没有旁路。  
结果已写入 canonical：新增 9 条关系、12 份 Boundary Contract（generation `g000098`）。

---

## 1. 总图（含本次补边）

```text
用户
 │
 ▼
交互层 ──Message Envelope──► 智能体运行时 ──Working Context──► 上下文引擎
 ▲                              │                              │
 │                              │                              ├─► 个人账本核心（读）
 │                              │                              ├─► 摘要系统（读）
 │                              │                              └─► 记忆织物（读/召回）
 │                              │
 │                              ├──工具──► 能力注册表
 │                              ├──下钻──► 来源与证据（读）
 │                              └──Ledger Ops──► 状态提交引擎 ──唯一写──► 个人账本核心
 │                                                    │
 │                                                    ├─► 来源与证据（挂接/纠正）
 │                                                    ├─► 持久任务运行时（建提醒）
 │                                                    └─► 摘要系统（Dirty）
 │
 ◄──NotificationIntent──持久任务运行时
 ▲
投影层 ──UserEditOp──► 状态提交引擎
记忆织物 ──Proposal──► 状态提交引擎（默认不自动改史）
运维与配置 ──横切 related_to──► 交互/持久/记忆/投影/运行时/账本
```

---

## 2. 审计发现与处置

| # | 发现 | 风险 | 处置 |
| --- | --- | --- | --- |
| A1 | **提醒没有回家的路**：Durable 只 `references` 账本，不产生到交互层的投递 | 到期无人送达/各渠道私发 | 新增 `持久任务 → 交互层` + Contract（NotificationIntent、collapse_key 防轰炸） |
| A2 | **表格可旁路写账本**：投影只依赖读账本，未强制经提交引擎 | 双真相、AI 不知道用户改了什么 | 新增 `投影 → 状态提交引擎` + Contract（UserEditOp→LedgerOps、冲突可见） |
| A3 | **改了状态摘要不知情**：提交引擎与摘要系统无边 | Capsule 过期、表与 AI 不一致 | 新增 `提交 → 摘要` Dirty 协议；禁止 commit 内做长总结 |
| A4 | **记忆整理可变相改史**：Provider 整理未钉死 proposal-only | 后台静默合并/删历史 | 新增 `记忆织物 → 提交引擎`，仅 Proposal，采纳才 commit |
| A5 | **证据下钻未声明**：运行时需要 Source 自证却无边 | 胡说页码、坏链 | 新增 `运行时 → 来源与证据`（只读）+ 缺证据即拒答 |
| A6 | **运维横切不完整** | 故障只盯 2 个模块，通知/提醒/表格黑盒不可观测 | 补 `related_to`：交互、持久、记忆、投影 |

---

## 3. 关键交接合同（已写入 Boundary Contract）

### 3.1 交互层 → 运行时（Message Envelope）
- **交出：** message_id / channel / user_ref / ts / payload / attachments / provenance  
- **收回：** Reply + 通知  
- **禁止：** 渠道会话当账本；Envelope 当 Matter 主键  
- **失败：** 投递失败必须可见可补送；message_id 幂等防重放  

### 3.2 运行时 → 提交引擎（Ledger Operations）
- **交出：** Reply 草稿 + ops[]（op_id 幂等）  
- **硬规则：** **只有 commit 成功才允许 UI 声称已保存**（反假成功）  
- **失败：** 半失败回滚/续传；超时降级文案  

### 3.3 提交引擎 → 账本 / 证据 / 持久 / 摘要
- **唯一写入口**进账本；挂 Source；创建任务；发 Dirty  
- **禁止：** 投影/Provider 直写；纠正改原文；commit 内 LLM 长总结  

### 3.4 持久 → 交互（NotificationIntent）
- 用 `collapse_key` 合并轰炸；至少进「未送达」列表  
- **禁止：** 持久层直连企微 SDK  

### 3.5 投影 → 提交（UserEditOp）
- 编辑先回执再落 UI 终值；冲突合并不静默覆盖  

### 3.6 记忆 → 提交（Proposal）
- 默认只建议；采纳才改真源；来源标 provider  

---

## 4. 一次完整交互的合格轨迹（验收用）

**输入：** 企微「明天下午提醒我联系李经理，合同还没盖章」→ Web 补「他周一盖」→ 表格把状态改成「等待」→ 到点提醒。

| 步 | 黑盒 | 交接物 | 合格表现 |
| --- | --- | --- | --- |
| 1 | 交互→运行时 | Envelope(A) | 同 user_ref，附件/文本完整 |
| 2 | 运行时→上下文 | 请求 Context | 带出李经理/合同相关胶囊 |
| 3 | 运行时→提交 | ops: event+matter+reminder | 一次 Turn 含 Reply |
| 4 | 提交→账本/证据/持久/摘要 | commit+dirty | 无双写；capsule 更新 |
| 5 | 持久→交互 | NotificationIntent | 次日到手机/企微，collapse_key=合同 |
| 6 | 投影→提交 | UserEditOp 状态=等待 | 回执「已记入账本」，AI 后续一致 |

任一步旁路（表格直写、提醒私发渠道、假成功 Reply）均为 **合同违约**。

---

## 5. 仍建议 P1 补的边（本次未强行展开）

- `上下文引擎 → 投影`（「你刚才用了哪些记忆」轻量解释）  
- `能力注册表 → 各执行模块` 的 contains/validates 细化（工具实现归属）  
- `运维 → 全部模块` 完整 tracing 扇出（现为关键出口 related_to）  

---

## 6. 变更摘要

| 项 | 数量 |
| --- | --- |
| 新增关系 | 9 |
| Boundary Contract | 12 |
| 关系总数 | 26 |
| generation | `g000077` → **`g000098`** |
