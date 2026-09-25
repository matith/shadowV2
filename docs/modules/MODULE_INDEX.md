# Module Index

**权威规格在 BBM canonical**（`blackbox/`，Workbench 可查看）。本页是中文阅读索引；详细 Purpose / 验收场景 / 约束以 Workbench 模块 Spec 为准。

| ID | 中文名 | 一句话职责 | 关键动作（摘） |
| --- | --- | --- | --- |
| `interaction-layer` | 交互层 | 多渠道消息进出管道，不持有事项状态 | normalize_inbound_message / deliver_reply |
| `agent-runtime` | 智能体运行时 | 可替换模型发动机，产出回复与账本操作提案 | run_turn / emit_ledger_ops |
| `context-engine` | 上下文引擎 | 编译 Working Context，多账本路由，预算控制 | compile_working_context / route_to_ledgers |
| `personal-ledger-core` | 个人账本核心 | 唯一业务真源：事项/事件/人物/知识/产品/文件/指令/归档 | create_or_update_matter / create_event |
| `source-evidence` | 来源与证据 | 不可变原文与溯源，解释可纠正 | store_raw_source / mark_interpretation_invalid |
| `state-commit-engine` | 状态提交引擎 | 唯一写入闸门：Patch/Correction/幂等/确认 | commit_ledger_ops / apply_correction |
| `summary-system` | 摘要系统 | 增量 Capsule 与父子传播 | update_capsule_incremental / propagate_dirty |
| `memory-fabric` | 记忆织物 | 分层召回与可插拔 Provider（可重建） | recall / reindex / propose_consolidation |
| `durable-task-runtime` | 持久任务运行时 | 提醒/延迟/定时/恢复真实发生 | schedule_reminder / run_due_tasks |
| `capability-registry` | 能力注册表 | 工具契约与权限，长期能力留位 | register_capability / invoke_tool |
| `projection-layer` | 投影层 | 表格/Web/App 共享操作面，编辑回写 | render_ledger_table / apply_user_edit |
| `operations` | 运维与配置 | 备份/迁移/换模/追踪 | export_backup / set_model_provider |

> 子模块（Channel Gateway、Matter Ledger 等）在顶层模块 Spec 的 `custom.in_scope` 中声明，P1 再拆独立节点。

---

## 关键关系（核心）

```text
message-normalizer → agent-runtime
agent-runtime → context-engine
agent-runtime → capability-registry
agent-runtime → state-commit-engine
context-engine → personal-ledger-core
context-engine → memory-fabric
context-engine → summary-system
state-commit-engine → personal-ledger-core
state-commit-engine → source-evidence
state-commit-engine → durable-task-runtime
summary-system → personal-ledger-core
memory-fabric → personal-ledger-core   (depends_on, derived)
projection-layer → personal-ledger-core
interaction-layer → agent-runtime
operations 横切
```

关系类型语义（与 BBM 一致）：

- `depends_on` A→B：A 依赖 B
- `contains` 父→子
- `produces_for` A→B：A 为 B 产出
- `references` / `related_to` / `validates` 按需

---

## 建议 visual group

- `group-core`: personal-ledger-core + source-evidence + state-commit-engine + summary-system
- `group-runtime`: interaction-layer + agent-runtime + context-engine + capability-registry
- `group-derived`: memory-fabric + projection-layer + durable-task-runtime + operations
