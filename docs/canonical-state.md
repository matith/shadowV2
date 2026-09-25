# Canonical State & Data Model

## 1. 状态所有权

| 状态 | Owner | 是否真源 |
| --- | --- | --- |
| Event / Matter / People / Knowledge / Product / Directive / Archive | Personal Ledger Core | **是** |
| Raw Source / Attachment / Provenance | Source & Evidence | **是** |
| Reminder / Delayed / Scheduled Task | Durable Task Runtime | **是** |
| Correction / Commit 轨迹 | State / Commit Engine | **是** |
| Context Capsule | Summary System | Derived（可重建） |
| Embedding / Index / HOT-WARM-COLD | Memory Fabric | Derived |
| WPS / Web / App 表格 | Projection Layer | Projection |
| Chat / Agent Session | Interaction / Runtime | 日志，不是业务真源 |
| Mem0 / Graphiti / Vector DB | Memory Fabric Provider | 可插拔缓存 |

---

## 2. Event / Matter / Source 三分

```text
Source (原文, immutable)
   │ explains / evidence
   ▼
Event (发生了什么, timestamped interpretation)
   │ feeds
   ▼
Matter (现在是什么状态, current state)
   │ summarized as
   ▼
Context Capsule (derived, incremental)
```

### Source

```text
source_id
kind            # file | message | web | tool_result | ...
raw_content / storage_ref
received_at
channel / provenance
hash / version
attachment_refs[]
```

- 不可被 AI Interpretation 改写
- 纠正发生在 Interpretation 层，Source 保留

### Event

```text
event_id
timestamp
source_ref
raw_content_summary
attachments[]
related_matters[]
interpretation   # 模型理解结果，可被 Correction 失效
actors[]         # people refs
created_by       # user | agent
```

- Event 是历史事实流（含模型解释）
- 一个 Event 可关联 0..n 个 Matter / People / File

### Matter

```text
matter_id
title
summary / capsule_ref
state            # open | waiting | active | paused | done | archived
goal
next_action
parent_matter_id?
people_refs[]
event_refs[]
file_refs[]
children[]
lifecycle
importance / pin
last_update
archive_capsule?
```

- Matter 表达 **当前状态**，不是全部历史的堆场
- 历史通过 Event 查阅
- 支持树：主事项 → 子事项 → 子事项

---

## 3. 关系与引用

- 一条用户消息可同时产生：People + Product + Knowledge + File + Event + Matter 关联
- 用 **引用（ref）** 连接，不复制原始数据
- Source → Event → Matter → Capsule 保持单向证据链
- Capsule / Summary 中的结论必须能落到 evidence 指针（event / file / source）

---

## 4. Context Capsule（非普通总结）

示例形状：

```text
Matter: 春促启动会
Goal: 完成启动会材料和现场流程。
Current State: ...
Recent Changes: ...
Open Items: ...
Important Files: ...
Evidence: event_31, event_89, file_09
```

读取路径：

```text
Capsule → Evidence Pointer → Event / File → Raw Source
```

平时只读 Capsule；需要证据时再下钻。

---

## 5. 增量摘要与树传播

### 增量

```text
Old Capsule + New Event / State Patch → New Capsule
```

禁止每事件全量重总结。历史变长不应使处理成本线性爆炸。

### 父子传播

```text
春促启动会
 ├─ PPT
 │   ├─ 领导页
 │   └─ 颁奖页
 └─ 主持稿
```

领导页变化：

```text
领导页 Capsule → PPT Capsule → 春促启动会 Capsule
```

某级摘要无实质变化则 **停止传播**。Dirty Tracking 标记脏节点，不重扫整树。

---

## 6. Correction 语义

用户纠正是一等公民，不是异常。

**允许：**

- “不是周一，是周三”
- “那个项目不是完成，只是暂停”
- “刚才说错了，是另外一个客户”
- “这条以后不要记”

**执行：**

1. Source 保留
2. 旧 Interpretation 失效 / 降权
3. 记录 Correction 轨迹（审计）
4. 更新 Current State（Matter / People / fields）
5. 可删除错误 Derived Memory
6. 后续 Context 使用纠正后的值

---

## 7. Archive 语义

| 做 | 不做 |
| --- | --- |
| 事项进入 Archive Ledger | 物理删除历史 |
| 保留极小 Archive Capsule | 丢掉 Source / Event |
| 保留指针到完整 Matter | 假装从不记得 |
| 提起时可展开全量 | 每次都塞全量进上下文 |

---

## 8. 一次 Turn 顺带产生 State Patch

不强制五次 LLM：

```text
LLM 理解 → LLM 回复 → LLM 总结 → LLM 写记忆 → LLM 更新状态
```

允许单 Turn 输出：

```text
Reply
Ledger Operations:
- create_event
- update_matter
- create_fact
- create_reminder
- attach_file
Optional Memory Proposals
```

程序执行确定性操作。批量消息走 Conversation Burst → Consolidation → Matter Patch，而非每条重总结。

---

## 9. 失败语义 / 幂等

- Ledger Operation 必须可幂等重试（client_request_id / op_id）
- Commit 失败不产生半套关联
- Correction 与 Commit 一样需要审计与可追溯
- Derived 失败不影响 Canonical；可重建
- Durable Task 触发失败要能 resume，而不是静默丢失
