# -*- coding: utf-8 -*-
"""Rewrite 拾光 V2 BBM module specs: Chinese names, detailed purpose/scenarios/constraints."""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:4319"
PROJECT_ID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}

def req(method, path, body=None):
    data = None
    headers = {
        "Content-Type": "application/json",
        "X-BBM-Expected-Project-Id": PROJECT_ID,
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")

def spec(purpose, kind, narrative, outcomes, failures, constraints, custom):
    return {
        "purpose": purpose,
        "acceptance_experience": {
            "kind": kind,
            "narrative": narrative,
            "expected_outcomes": outcomes,
            "failure_signals": failures,
        },
        "constraints": constraints,
        "custom": custom,
    }

MODULES = {
    "interaction-layer": {
        "name": "交互层",
        "summary": "把企业微信、App、Web、分享、语音、邮件等入口的收发统一成拾光内部消息信封；只负责管道，不负责账本业务状态。",
        "spec": spec(
            purpose=(
                "交互层是用户触达拾光的唯一外部管道。它把不同渠道的原始输入（文字、附件、语音转写、系统事件）"
                "规范成内部统一的 Message Envelope，再把 Agent 的 Reply / 通知按原渠道送回用户。"
                "它的存在意义是：渠道可以随时增减或替换，而拾光的现实状态账本、提醒和证据链完全不受渠道变更影响。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户早上在企业微信说「下午三点提醒我给李经理回电话」，中午在 Web 补充「合同还没盖章」，"
                "晚上在 App 上传一份报价单 PDF。交互层必须把这三次输入标成同一用户、同一会话语境可关联的事件信封"
                "（含渠道、时间、附件、身份映射），交给下游；不得把「回电话」写成仅存在于企微会话里的草稿，"
                "也不得因为换了 App 就丢掉中午那句补充。回复与次日提醒也要能送回用户实际使用的渠道。"
            ),
            outcomes=[
                "同一用户在企微/Web/App 的输入都能进入同一条内部处理链路，并带完整渠道与身份映射",
                "附件（PDF/图片/语音）以原始文件进入 Source 通道，而不是只截取聊天可见文本",
                "Agent 回复与系统提醒可路由回原渠道，或按用户偏好送到指定渠道",
                "渠道故障（如企微限流）不会导致账本写入失败被当成消息丢失；可重试且幂等",
                "新增一个 Channel 时，只需实现 Gateway 适配，不改 Personal Ledger Core",
            ],
            failures=[
                "把事项状态写死在某个渠道的会话草稿或未发送消息里",
                "用户切换渠道后，同一事项被当成两个无关用户/两套状态",
                "附件被丢弃或只保存预览图，导致 Source 无法追溯原文",
                "Channel 直接调用账本写入，绕过 State/Commit Engine",
                "为兼容某一渠道私有格式，污染内部 Message Schema",
            ],
            constraints=[
                "Channel 只允许做：收消息、标识来源、发回复/通知、传附件、身份映射；禁止持有 Matter 当前状态",
                "所有输入必须变成内部 Message Envelope（含 message_id、channel、user_id、ts、payload、attachments、provenance）",
                "渠道重试不得造成重复 Event（需幂等键）",
                "禁止把企业微信/App/Web 的私有字段当作拾光业务主键",
                "身份映射表属于 Interaction 私有配置，不是 People Ledger 真源；冲突时以 People Ledger 为准并告警",
            ],
            custom={
                "responsibilities": ["消息进入规范化", "消息送出与通知投递", "附件管道", "渠道身份映射", "渠道级重试与幂等"],
                "actions": ["normalize_inbound_message", "deliver_reply", "deliver_notification", "attach_binary_payload", "map_external_identity"],
                "in_scope": ["Channel Gateway", "Message Normalizer", "Delivery"],
                "out_of_scope": ["账本字段读写", "摘要生成", "提醒调度策略", "模型理解"],
                "real_scenarios": [
                    "企微说事项 + Web 补充 + App 传附件 → 同一用户上下文可关联",
                    "次日提醒从 Durable 触发后送到用户常用渠道",
                ],
            },
        ),
    },
    "agent-runtime": {
        "name": "智能体运行时",
        "summary": "可替换的大模型循环发动机：读 Working Context、调工具、产出回复与账本操作提案；不拥有真源，不绑定某一家 harness。",
        "spec": spec(
            purpose=(
                "智能体运行时是「理解与操作」的发动机，不是拾光的主人。它把 Context Engine 编译好的 Working Context"
                "交给模型，让模型自行决定：是否打开某个事项胶囊、是否下钻证据、是否搜索知识、是否创建提醒、是否请求确认。"
                "运行时只消费 Tool Contract，只产出 Reply 与 Ledger Operations 提案，绝不直接改 Canonical 账本。"
                "换模型、换 harness（自建 / Codex / DeepSeek 开源 harness / 混合）不得改变 Personal Ledger 语义。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户说「主持人已经改成王雨和胥晴，亮总的措施放在代理商分享之后」。"
                "运行时应在一次 Turn 内：①回复用户确认；②产出 Matter Patch（更新春促启动会的主持人字段与流程备注）；"
                "③可选产出 Capsule 增量摘要提案。不要拆成「先理解、再回复、再总结、再写记忆、再改状态」五次无关模型调用。"
                "若用户接着说「不是王雨，是王雨晴」，运行时必须发起 Correction 而不是新建事项或改写原消息。"
            ),
            outcomes=[
                "一次用户输入可同时产生 Reply + 多条确定性 Ledger Operations",
                "模型可按需读取 Capsule / Event / Source / Directive，也可在证据不足时只提问不瞎写",
                "替换模型 Provider 后，Personal Ledger Core 数据与语义不变",
                "工具调用 100% 经过 Capability Registry 的命名契约，无隐式副作用",
                "边界外未知（如未接入的日历）只记 Feedback/TODO，不阻断本轮记账",
            ],
            failures=[
                "业务状态只存在于 harness 私有会话/上下文，进程退出即丢",
                "绕过 State/Commit Engine 直接改账本文件或数据库",
                "为过测试写死分类决策树，使模型无法灵活组合工具",
                "把 Codex/DeepSeek/PydanticAI 等产品概念反向命名成拾光顶层模块",
                "每条消息串行 4–5 次模型调用才能完成一次普通记账",
            ],
            constraints=[
                "运行时是可替换组件：禁止把某家 Agent CLI/SDK 的 Session 当作 Matter 真源",
                "只允许通过 Capability Registry 调用工具；禁止私自读写 blackbox/ 业务存储",
                "单 Turn 输出必须可解析为 Reply + LedgerOperations[]（幂等 op_id）",
                "高风险动作（删除/对外发送/金额）必须先走 Permission，不得「先斩后奏」",
                "实现选型（自建薄 harness / 订阅型 CLI / 开源 harness）只在本模块内评估，不得改写产品边界",
            ],
            custom={
                "responsibilities": ["模型循环", "工具调用协议", "Turn 编排", "操作提案输出"],
                "actions": ["run_turn", "call_tool", "emit_ledger_ops", "request_user_confirmation"],
                "in_scope": ["Model Adapter", "Tool Calling", "Turn Orchestration"],
                "out_of_scope": ["Canonical 存储", "摘要算法", "渠道收发", "持久任务调度"],
                "real_scenarios": [
                    "改主持字段 + 回复用户（单 Turn）",
                    "纠正人名（Correction）",
                    "证据不足时反问而不是编造",
                ],
            },
        ),
    },
    "context-engine": {
        "name": "上下文引擎",
        "summary": "编译每次对话的 Working Context，并把新信息路由到多个账本；控制 token 预算与热度分层，防止历史无限膨胀。",
        "spec": spec(
            purpose=(
                "上下文引擎回答两个问题：①这次模型该看见什么；②这条新信息该写到哪些账本。"
                "它综合当前消息、活跃事项、相关人物、时间窗、重要度、用户固定（pin）、Directive 与 Token Budget，"
                "生成 Working Context；并调用 Ledger Router 把输入扇出到 Matter/Event/People/Knowledge/Product/File/Directive 等"
                "（允许多账本同时命中，用引用连接）。长期数据增长不得让单次上下文线性膨胀。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户说「李经理发了一份新的云电脑产品政策 PDF，下月生效，和我们在谈的项目有关」。"
                "上下文引擎应：路由到 People（李经理）、Product（云电脑）、Knowledge/File（新政策）、Event（收到资料），"
                "若识别到进行中项目则关联 Matter；同时编译的 Working Context 只需带上该项目的 Compact Capsule、"
                "李经理的 People 卡片摘要、最近相关政策，而不是把两年聊天全塞进上下文。"
                "半年前签的两年合同仍是 HOT/WARM 重要事项，不能因为「旧」就被纯时间规则冷掉。"
            ),
            outcomes=[
                "同一消息可同时关联多个 Ledger，且原文只存一份（Source）",
                "Token 超预算时按 Recency×Lifecycle×Relevance×Importance×Pin×Activity 裁剪，而不是简单砍掉最旧的",
                "活跃事项优先提供完整 Capsule + 最近 Event；次要事项只给 Compact Capsule",
                "Directive（如「闲聊不长期保存」）在路由阶段生效",
                "检索失败可降级为只读 Capsule，不阻断回复",
            ],
            failures=[
                "每次对话把全部历史塞进上下文，成本与延迟随数据量爆炸",
                "强制单分类，丢掉人物/资料/事项中的其他维度",
                "只按「七天内=HOT」处理，导致重要长期合同被误判为冷数据",
                "路由错误后无法 Correction，错误账本绑定永久化",
                "上下文里出现无法追溯到 Source 的「凭空事实」",
            ],
            constraints=[
                "Working Context 必须由 Context Compiler 生成，禁止手拼全量账本",
                "Ledger Router 结果是建议性的、可纠正的，不是唯一锁死分类",
                "必须遵守 Context Budget；超限必须显式裁剪并可解释裁剪顺序",
                "热度分层禁止纯时间阈值一刀切",
                "只读 Canonical/Derived；禁止在编译阶段写业务状态（写入归 State/Commit）",
            ],
            custom={
                "responsibilities": ["Working Context 编译", "Ledger 路由", "检索调度", "预算与热度"],
                "actions": ["compile_working_context", "route_to_ledgers", "retrieve_related", "apply_context_budget"],
                "in_scope": ["Context Compiler", "Ledger Router", "Memory Retrieval", "Context Budget"],
                "out_of_scope": ["提交账本变更", "永久摘要写入", "渠道投递"],
                "real_scenarios": ["多账本扇出（李经理+政策+项目）", "长期合同不被时间规则误冷"],
            },
        ),
    },
    "personal-ledger-core": {
        "name": "个人账本核心",
        "summary": "拾光唯一业务真源：事项、事件、人物、知识、产品、文件、指令、归档等多账本；AI 与用户共同维护的现实状态。",
        "spec": spec(
            purpose=(
                "个人账本核心维护「用户生活与工作的现实状态」，而不是聊天流水。"
                "它分离历史（Event）与当前状态（Matter），分离原文（Source）与解释（Interpretation），"
                "并用多账本承载不同类型信息：事项、事件、人物、知识、产品资料、文件源、用户指令、归档。"
                "AI 与用户通过结构化操作共同更新账本；表格、向量库、第三方记忆产品都只是投影或缓存，绝不是真源。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景 A（多轮事项）：周一「李经理说合同预计周一盖章」→ 建 Matter「合同盖章」；"
                "周三「他说改周一盖」→ 更新同一 Matter，而不是新建「合同盖章2」；"
                "周五「盖了」→ 状态 done，并归档保留极小摘要。"
                "真实场景 B（纠正）：「不是王经理，是李经理」→ 原消息不改，失效旧解释，Matter.people 改为李经理。"
                "真实场景 C（归档召回）：两年后「当年那个春促…」→ Archive 命中「有这回事」，可再展开完整历史。"
            ),
            outcomes=[
                "同一持续事项在数天/数月更新后收敛为同一 Matter（允许子事项）",
                "一条消息可同时建立 People/File/Knowledge/Matter 引用，原文不复制多份",
                "任意 Capsule/字段可追溯到 Event/Source 证据",
                "关闭 WPS/Web UI 后，账本仍完整可恢复",
                "纠正后后续上下文一律使用新值，并保留审计轨迹",
            ],
            failures=[
                "重复 Matter 扩散，用户找不到「当前真相」",
                "把聊天记录当唯一状态，没有 Matter 当前字段",
                "Mem0/Graphiti/向量库/表格反向覆盖账本字段",
                "纠正后系统继续用旧人名/旧日期",
                "归档后完全失联，或归档即物理删除",
            ],
            constraints=[
                "唯一写入口是 State/Commit Engine；禁止旁路写入",
                "Source 原文不可被 AI 解释覆盖或就地改写",
                "Matter 表达当前状态；历史进 Event，禁止把 Matter 行做成无限历史堆",
                "多账本关联必须用引用 ID，禁止复制原文",
                "归档 ≠ 删除：Archive Capsule + 指针必须保留",
                "Derived（Capsule/索引）可重建，不得成为恢复账本的唯一途径",
            ],
            custom={
                "responsibilities": ["多账本实体管理", "Matter 当前状态", "Event 历史", "跨账本引用", "生命周期与归档"],
                "actions": ["create_event", "create_or_update_matter", "upsert_person", "link_entities", "archive_matter", "read_capsule"],
                "in_scope": ["Matter/Event/People/Knowledge/Product/File/Directive/Archive"],
                "out_of_scope": ["向量索引实现", "渠道收发", "模型循环", "表格渲染"],
                "real_scenarios": ["合同盖章多轮收敛", "人名纠正", "春促归档召回"],
            },
        ),
    },
    "source-evidence": {
        "name": "来源与证据",
        "summary": "保存不可变原文、附件与溯源链；AI 解释可失效，Source 永不改写；支撑「摘要能指回原文」。",
        "spec": spec(
            purpose=(
                "来源与证据模块保证拾光「说过的每句重要结论都能指回原文」。"
                "它接收聊天原文、上传文件、网页摘录、工具结果，写入 Raw Source（不可变）+ Provenance（谁/何时/从哪来）+ Version。"
                "AI 的摘要、分类、实体、推论都只是 Interpretation，可被纠正失效，但 Source 本体永远保留。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户上传《云电脑产品政策V3.pdf》。系统保存文件哈希与存储引用；"
                "三天后用户说「你摘要里写的资费不对，应该是 29 元/月」。正确做法是：PDF 原文不动，"
                "标记旧摘要失效，记 Correction，更新 Knowledge/Product 中的资费字段，新摘要指向该 PDF 页码/段落证据。"
                "若之后再问「政策依据是什么」，应能打开 Source 而不是复述可能过期的摘要。"
            ),
            outcomes=[
                "任意重要结论可下钻 Capsule → Event/File → Raw Source",
                "用户纠正不修改原消息/原文件",
                "附件版本（V2/V3）可区分，旧版本仍可取证",
                "来源链包含渠道、时间、操作者",
                "存储损坏时能报告缺证据，而不是编造原文",
            ],
            failures=[
                "为了「让摘要更顺」而改写用户原话",
                "只存摘要不存原文，事后无法核对",
                "同名文件覆盖旧版本导致证据丢失",
                "把 AI 推论写回 Source 字段",
                "无法回答「这句话出自哪份材料」",
            ],
            constraints=[
                "Raw Source 创建后只读；禁止 update_source_text",
                "Interpretation 必须带 source_ref / evidence_refs",
                "附件写入需内容哈希与版本号",
                "Correction 只能作用于 Interpretation/Ledger State，不能 delete_source",
                "证据缺失时必须显式失败信号，禁止静默空引用",
            ],
            custom={
                "responsibilities": ["原文存储", "附件与版本", "溯源链", "证据指针"],
                "actions": ["store_raw_source", "store_attachment", "attach_provenance", "resolve_evidence", "mark_interpretation_invalid"],
                "in_scope": ["Raw Source", "Attachment", "Provenance", "Version"],
                "out_of_scope": ["语义摘要生成", "账本状态合并", "渠道 UI"],
                "real_scenarios": ["政策 PDF 资费纠正且原文保留", "摘要指回页码证据"],
            },
        ),
    },
    "state-commit-engine": {
        "name": "状态提交引擎",
        "summary": "把模型/用户意图落成可审计、可幂等的账本变更；负责 Patch、Correction、冲突与高风险确认。",
        "spec": spec(
            purpose=(
                "状态提交引擎是 Canonical 的唯一合法写入闸门。它接收 Ledger Operations（create_event、update_matter、"
                "create_fact、create_reminder、attach_file、correct_field…），校验权限与幂等键，处理冲突，"
                "在一次原子提交中写入 Personal Ledger + Source 指针 + Durable Task，并留下 ChangeSet/审计。"
                "Correction 在这里是一级公民，不是异常分支。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景 1：用户连发三条「明天提醒我…还有合同…李经理」。引擎应允许 Conversation Burst 合并后一次提交，"
                "而不是产生三条互相冲突的 Matter。"
                "真实场景 2：「不是周一，是周三」→ 提交 Correction patch，旧解释失效，Matter.due 更新，原 Event 保留。"
                "真实场景 3：模型想发邮件给客户 → 高风险，必须先 Permission 确认；而「更新摘要」不应弹窗打断用户。"
                "网络重试同一 op_id → 不得双写 Reminder。"
            ),
            outcomes=[
                "重复提交同一 op_id 不产生重复 Matter/Event/Reminder",
                "Correction 后当前状态与后续上下文立即一致",
                "半失败（写了一半崩溃）可续传或回滚，无悬空引用",
                "高风险动作有确认记录；常规整理零打扰",
                "每次成功提交可回读 ChangeSet 与 generation",
            ],
            failures=[
                "改写 Source 或静默丢弃用户纠正",
                "重试导致双提醒、双事项",
                "高风险删除/对外发送未确认",
                "部分写入成功导致 Matter 指向不存在的 Event",
                "把 Proposal 当已提交状态展示给用户",
            ],
            constraints=[
                "所有写入必须带 project_id + expected_generation（CAS）或等价原子门禁",
                "Ledger Operation 必须幂等（client op_id）",
                "Correction 必须可审计：旧行标记失效，新行生效，原 Source 不动",
                "高风险类别（删除/对外/金额）默认需确认，可在 Directive 中收紧不得放松到静默",
                "禁止在本模块内做自然语言理解；只执行确定性操作",
            ],
            custom={
                "responsibilities": ["提案校验", "补丁提交", "纠正", "冲突处理", "幂等与审计"],
                "actions": ["commit_ledger_ops", "apply_correction", "detect_conflict", "require_confirmation", "emit_changeset"],
                "in_scope": ["Proposal", "Patch", "Correction", "Conflict", "Commit"],
                "out_of_scope": ["模型推理", "原文解析", "未来任务触发执行"],
                "real_scenarios": ["burst 合并提交", "日期纠正", "高风险确认", "重试不双写"],
            },
        ),
    },
    "summary-system": {
        "name": "摘要系统",
        "summary": "维护事项 Context Capsule 与增量摘要；子事项变化向上递归传播，无变化即停；摘要必须可追溯证据。",
        "spec": spec(
            purpose=(
                "摘要系统产出「AI 能稳定读取的小上下文包」Context Capsule，而不是每次长篇重新总结。"
                "更新公式是 Old Capsule + New Event/State Patch → New Capsule；父事项只接收子事项的脏传播，"
                "某级摘要无实质变化则停止。每个 Capsule 必须带 Goal/Current/Open Items/Recent Changes/Important Files/Evidence。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：「春促启动会」下有 PPT（领导页、颁奖页）与主持稿。用户改了领导页排版说明。"
                "系统只应更新：领导页 Capsule → 若影响 PPT 开放项则更新 PPT Capsule → 若影响启动会开放项再向上；"
                "若主持稿 Capsule 无变化则不动。禁止打开全部历史重写整棵树。"
                "两周后问「启动会还差什么」，读 Capsule 应直接答出开放项，并能点进 event_38/file_09 证据。"
            ),
            outcomes=[
                "历史变长后，单次摘要更新成本近似常数（增量）",
                "Capsule 字段完整：目标/当前/变化/开放项/文件/证据",
                "子变更只传播受影响的祖先路径",
                "摘要与证据指针一致，无「空中结论」",
                "Derived 丢失后可从 Source+Events+Patch 轨迹重建",
            ],
            failures=[
                "每条消息全量重总结，费用随历史线性涨",
                "摘要无法指出证据",
                "父摘要与子摘要矛盾且无人发现",
                "无脏标记，整树重扫",
                "把 Capsule 当唯一数据存储，丢了就无法恢复事项",
            ],
            constraints=[
                "默认增量更新，全量重建只允许在显式 repair 任务中",
                "传播遇到「摘要无变化」必须停止",
                "Evidence 字段非空且可解析",
                "Capsule 是 Derived，禁止在无 Source/Event 支撑下写入事实",
                "摘要文本不得引入 Source 之外的新事实",
            ],
            custom={
                "responsibilities": ["Capsule 形态", "增量 reducer", "树传播", "脏跟踪"],
                "actions": ["update_capsule_incremental", "propagate_dirty", "rebuild_capsule", "attach_evidence_refs"],
                "in_scope": ["Context Capsule", "Incremental Summary", "Tree Propagation", "Dirty Tracking"],
                "out_of_scope": ["账本字段权威存储", "向量检索"],
                "real_scenarios": ["领导页改动局部传播", "启动会开放项一问即答"],
            },
        ),
    },
    "memory-fabric": {
        "name": "记忆织物",
        "summary": "HOT/WARM/COLD/RAW 分层与可插拔记忆 Provider；只做召回加速，不拥有业务真源，可整体重建。",
        "spec": spec(
            purpose=(
                "记忆织物服务检索与降温，不定义「什么才是真的」。它维护语义索引、关系索引、热度分层，"
                "并允许接入本地 Basic / Mem0 / Graphiti 等 Provider 做联想与模式发现。"
                "任何 Provider 结果都只是召回线索，最终事实以 Personal Ledger + Source 为准。"
                "后台整理可以合并零散线索、降温、去重建议，但不得篡改 Source。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户半年后问「我们和联通的框架合同谈到哪一步了」。"
                "Memory Fabric 应从语义/关系索引召回「框架合同」Matter 与相关 People/Event 线索，"
                "交给 Context Engine 编译；即使 Mem0 当时挂了，也应降级到 Ledger 本地检索，而不是完全失忆。"
                "若 Provider 建议「这俩事项重复」，只能形成 Proposal，不能直接合并真源。"
            ),
            outcomes=[
                "换/关 Memory Provider 后核心问答仍正确",
                "HOT/WARM/COLD/RAW 提供明确的召回预算与降级路径",
                "索引可从 Canonical 全量重建",
                "后台整理产出建议而非静默改史",
                "召回结果标注来源（provider / ledger / archive）",
            ],
            failures=[
                "Provider 成为真源，删库即失忆",
                "把向量近邻直接当事实写入账本",
                "后台任务改写 Source 或 Matter 正式字段却不留痕",
                "热度只看时间，重要合同被冷掉",
                "无降级：Provider 故障导致无法回答",
            ],
            constraints=[
                "Derived-only：索引/缓存/Provider 状态全部可重建",
                "Provider 输出必须经 State/Commit 才能影响 Canonical",
                "禁止后台静默改写 Source/Correction",
                "热度评估必须多因子（含 importance/pin/lifecycle）",
                "删除 Provider 数据不得删除账本",
            ],
            custom={
                "responsibilities": ["热度分层", "语义/关系索引", "Provider 适配", "后台整理建议"],
                "actions": ["recall", "reindex", "degrade_or_cool", "propose_consolidation"],
                "in_scope": ["HOT/WARM/COLD/RAW", "Semantic Index", "Relation Index", "Memory Provider", "Background Consolidation"],
                "out_of_scope": ["业务真源", "用户可见确认策略"],
                "real_scenarios": ["合同语义召回", "Provider 故障降级"],
            },
        ),
    },
    "durable-task-runtime": {
        "name": "持久任务运行时",
        "summary": "保证提醒、延迟任务、计划任务与中断恢复真实发生；Agent 只决定做什么，Runtime 保证未来执行。",
        "spec": spec(
            purpose=(
                "持久任务运行时把「以后要做」从模型上下文里拿出来，变成可持久、可触发、可恢复的系统任务。"
                "覆盖提醒、延迟任务、定时任务、等待外部事件后的 Resume。"
                "原则：Agent 决定意图，Runtime 保证发生。进程重启、会话结束、模型更换都不得导致任务静默消失。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：「三天后提醒我跟进李经理的合同」。创建后即使拾光进程重启、对话清空，"
                "第三天仍必须触发提醒并携带 Matter 胶囊上下文；若用户当时说「再等两天」，应创建新的持久任务并关闭旧的，"
                "而不是只改聊天记录。若触发时渠道失败，应重试并记录失败，不得假装已提醒。"
            ),
            outcomes=[
                "到期任务可靠触发，并带足量上下文（Matter 摘要）",
                "重启后任务队列不丢",
                "取消/改期可审计",
                "重复触发有幂等保护",
                "任务可关联 Matter，完成/改期回写状态",
            ],
            failures=[
                "提醒只写在聊天里，过期没人管",
                "进程重启后任务表清空",
                "触发失败静默，用户以为没提醒是自己忘了",
                "同一提醒重复轰炸",
                "任务无法关联到具体事项",
            ],
            constraints=[
                "任务必须落盘持久化，禁止仅内存队列",
                "触发与重试必须幂等",
                "Agent 创建任务需明确 due/payload/matter_ref",
                "失败必须可观测（状态+最近错误）",
                "Resume 语义要能接上「等客户回复后继续」类任务",
            ],
            custom={
                "responsibilities": ["提醒", "延迟/定时任务", "恢复", "与 Matter 同步"],
                "actions": ["schedule_reminder", "run_due_tasks", "reschedule", "cancel_task", "resume_waiting"],
                "in_scope": ["Reminder", "Delayed Task", "Scheduled Task", "Resume"],
                "out_of_scope": ["模型决策内容", "渠道协议实现细节"],
                "real_scenarios": ["三天后提醒合同", "重启后仍触发", "改期不双发"],
            },
        ),
    },
    "capability-registry": {
        "name": "能力注册表",
        "summary": "统一登记工具/MCP/外部服务的契约与权限；让运行时可替换，并为 OCR、Office、日历等长期能力留位。",
        "spec": spec(
            purpose=(
                "能力注册表是拾光的「工具柜清单」。每个能力（读文件、搜知识、建提醒、读 PDF、调 MCP、发消息…）"
                "都有名称、输入输出契约、副作用等级、权限要求、实现绑定。"
                "Agent Runtime 只看见契约，不看见底层 SDK；实现可替换，语义保持稳定。"
                "长期能力（OCR/语音/Office/邮件/日历/浏览器/企微/网盘/PC 上下文）通过注册扩展，而不是推翻账本核心。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户说「把这份 PDF 里的资费存进知识库」。运行时应调用已注册的 `pdf.read` + `knowledge.upsert`"
                "等契约工具；若 PDF 能力尚未接入，应返回明确的「能力未注册」并引导，而不是假装成功。"
                "若工具是 `send_email`，注册表必须标为高副作用，强制 Permission，防止模型直接对外发送。"
            ),
            outcomes=[
                "工具可发现、可理解、可测试（契约稳定）",
                "高副作用工具有强制权限策略",
                "替换某工具实现不影响上层 Turn 逻辑",
                "未注册能力有明确失败语义",
                "新能力以插件登记，不改 Personal Ledger Core",
            ],
            failures=[
                "运行时直接依赖某家 SDK 内部 API",
                "高风险工具无权限就可调",
                "工具语义模糊（一个 `do_something`）导致模型乱用",
                "未实现能力被静默当成成功",
                "每次加能力都要改核心表结构",
            ],
            constraints=[
                "所有工具必须注册：name/version/io_schema/side_effects/permissions",
                "无注册不得调用；调用必须走 Registry",
                "副作用等级（read/write/external/high-risk）强制校验",
                "第三方适配器不得泄露到产品模块命名",
                "废弃工具要标记 deprecated，不得突然消失导致旧 Turn 失败不可解释",
            ],
            custom={
                "responsibilities": ["工具契约", "权限", "MCP/外部服务接入", "能力预留"],
                "actions": ["register_capability", "invoke_tool", "check_permission", "list_capabilities"],
                "in_scope": ["Native Tools", "MCP", "External Service", "Permission"],
                "out_of_scope": ["账本存储", "上下文编译"],
                "real_scenarios": ["PDF→知识库", "高风险发信需确认", "能力未注册显式失败"],
            },
        ),
    },
    "projection-layer": {
        "name": "投影层",
        "summary": "把账本投影成人可读可改的多维表格/Web/App；外部表格产品可更换，永不成为真源。",
        "spec": spec(
            purpose=(
                "投影层让人一眼看懂自己的生活/工作状态：事项、状态、摘要、下一步、子事项、人物、附件、历史。"
                "Canonical Ledger 通过 Projection Adapter 映射到 WPS 多维表格、自研 Web、未来 App。"
                "用户在表格里的编辑必须映射回 Ledger Patch，而不是让 WPS 变成第二真源。"
            ),
            kind="expected_visual_result",
            narrative=(
                "真实场景：用户打开表格，看到「春促启动会｜进行中｜主持稿 V6.1 已完成主体｜下一步：最终核对｜最后更新 9/25」，"
                "展开子事项与附件，直接把状态改成「等待获奖名单」。该修改必须写回 Matter 并可被 AI 读取。"
                "若明天改用 Web 或停用 WPS，状态不能丢。"
            ),
            outcomes=[
                "表格展示字段与账本语义一一对应（可映射文档化）",
                "单元格编辑/行新增/归档操作变成合法 Ledger Patch",
                "可筛选、排序、展开子事项、查看证据链接",
                "更换投影产品不需要迁移真源",
                "无投影时，API/CLI 仍可读写账本",
            ],
            failures=[
                "WPS 被当成主库，离开 WPS 无法恢复",
                "表格公式/自动化直接改派生库并覆盖真源",
                "列含义与账本字段漂移，AI 读到和人看到的不一致",
                "只读展示，用户无法纠正",
                "投影刷新把用户手工改的字段覆盖回去却不提示",
            ],
            constraints=[
                "Projection 只经 Adapter 访问 Canonical",
                "用户编辑必须走 State/Commit 语义（含审计）",
                "字段映射表是接口合同，变更需版本化",
                "禁止在投影层实现独立业务规则引擎",
                "冲突时以 Canonical 为准并提示用户",
            ],
            custom={
                "responsibilities": ["表格/Web/App 投影", "编辑回写", "字段映射", "冲突提示"],
                "actions": ["render_ledger_table", "apply_user_edit", "sync_projection", "show_evidence_link"],
                "in_scope": ["WPS/多维表", "Web", "Future App"],
                "out_of_scope": ["Canonical 存储", "模型理解"],
                "real_scenarios": ["表格改状态回写 Matter", "停用 WPS 不丢数据"],
            },
        ),
    },
    "operations": {
        "name": "运维与配置",
        "summary": "诊断、追踪、备份、迁移与模型/Provider 配置；支撑长期可换模型、可恢复、可升级。",
        "spec": spec(
            purpose=(
                "运维与配置保证拾光是长期产品而不是一次性脚本。它提供链路追踪（从渠道消息到账本提交）、"
                "诊断、备份/恢复、schema 迁移、模型与 Memory Provider 配置。"
                "换模型、升级版本、换电脑，都应有明确路径而不是靠人肉拷文件。"
            ),
            kind="user_journey",
            narrative=(
                "真实场景：用户换了 DeepSeek API Key 并想试本地模型。运维层应允许只改 Model Provider 配置并验证连通，"
                "账本数据零迁移。若磁盘损坏，应能从备份恢复 Canonical（含 Source），Derived 重建。"
                "若某次提交失败，Trace 应能回答「卡在哪个黑盒、哪个 op_id」。"
            ),
            outcomes=[
                "可备份/恢复 Canonical 与 Source",
                "可切换模型/Provider 不迁移账本",
                "失败请求可追踪定位",
                "schema 迁移有版本与回滚说明",
                "诊断接口能报告 cache/identity/generation 健康",
            ],
            failures=[
                "无备份导致磁盘故障全灭",
                "换模型需要改业务代码",
                "问题只能靠翻聊天猜",
                "备份只备份了向量库没备份真源",
                "升级后 generation/identity 不一致仍继续写",
            ],
            constraints=[
                "备份以 Canonical+Source 为准，Derived 可附带但可丢",
                "配置变更不得隐式改写业务数据",
                "身份/generation 校验失败必须 fail-closed",
                "迁移脚本必须幂等且可审计",
                "诊断输出不得包含明文密钥",
            ],
            custom={
                "responsibilities": ["诊断", "追踪", "备份恢复", "迁移", "模型/Provider 配置"],
                "actions": ["export_backup", "restore_backup", "set_model_provider", "trace_turn", "run_migration"],
                "in_scope": ["Diagnostics", "Trace", "Backup", "Migration", "Model/Provider Config"],
                "out_of_scope": ["业务规则", "日常记账"],
                "real_scenarios": ["切换模型不迁数据", "备份恢复账本", "失败链路定位"],
            },
        ),
    },
}

def main():
    status, body = req("GET", "/api/repo-status")
    print("status", status, body if isinstance(body, str) else body.get("repository_generation"))
    gen = body["repository_generation"] if isinstance(body, dict) else None
    ok = 0
    for mid, data in MODULES.items():
        # rename
        s, b = req("PATCH", f"/api/modules/{mid}", {"name": data["name"], **ACTOR})
        print("rename", mid, s)
        # summary
        s, b = req("PUT", f"/api/modules/{mid}/summary", {"text": data["summary"], **ACTOR})
        print("summary", mid, s)
        # spec commit
        payload = {
            "project_id": PROJECT_ID,
            "expected_generation": gen,
            "base_revision": 1,
            "spec": data["spec"],
            **ACTOR,
        }
        s, b = req("POST", f"/api/modules/{mid}/spec", payload)
        print("spec", mid, s)
        if s < 300:
            ok += 1
            if isinstance(b, dict):
                gen = b.get("repository_generation") or gen
        else:
            print("  ERR", b if isinstance(b, str) else json.dumps(b, ensure_ascii=False)[:500])
            # refresh gen and retry once
            st, sb = req("GET", "/api/repo-status")
            if isinstance(sb, dict):
                gen = sb.get("repository_generation") or gen
            payload["expected_generation"] = gen
            s, b = req("POST", f"/api/modules/{mid}/spec", payload)
            print("spec retry", mid, s)
            if s < 300:
                ok += 1
                if isinstance(b, dict):
                    gen = b.get("repository_generation") or gen
    print(f"done ok={ok}/{len(MODULES)} gen={gen}")

if __name__ == "__main__":
    main()
