# -*- coding: utf-8 -*-
"""Verified BBM closure: planning ledger + summary freshness + sub-blackboxes + interface gaps."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4319"
PID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}
TMPL = "general-module-v1"


def gen():
    req = urllib.request.Request(BASE + "/api/repo-status")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["repository_generation"]


def call(method, path, body=None):
    data = None
    headers = {"X-BBM-Expected-Project-Id": PID, "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def write(method, path, make_body, attempts=10):
    last = None
    for _ in range(attempts):
        g = gen()
        s, b = call(method, path, make_body(g))
        if s < 300:
            return s, b
        code = (b or {}).get("error", {}).get("code") if isinstance(b, dict) else None
        last = (s, b)
        if code == "GENERATION_CONFLICT":
            time.sleep(0.1)
            continue
        return s, b
    return last


def spec(purpose, narrative, outcomes, failures, constraints, custom=None):
    return {
        "purpose": purpose,
        "acceptance_experience": {
            "kind": "expected_system_behavior",
            "narrative": narrative,
            "expected_outcomes": outcomes,
            "failure_signals": failures,
        },
        "constraints": constraints,
        "custom": custom or {},
    }


# ---------- 1) Planning ledger ----------
def seed_planning():
    print("== planning ==")
    plan = write(
        "POST",
        "/api/planning/plan-versions",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "id": "plan-project-v1",
            "planning_scope_id": "project",
            "goal": "完成拾光 V2 房屋图纸级完整规划（Identity/Planning/子黑盒/关键闭环），P0 只装修「日常承诺」最小真实闭环，不提前施工其他能力。",
            "non_goals": [
                "本轮不写业务产品代码",
                "不接入 Mem0/Graphiti/WPS 作为真源",
                "不展开 OCR/语音/企微等 P2 能力实现",
            ],
            "assumptions": [
                "Personal Ledger 为唯一业务真源",
                "Agent harness / Memory Provider / Projection 可替换",
                "P0 场景以 Scenario A 为验收主轴",
            ],
            "risks": [
                "Planning 若继续只活在 docs/ 会导致新 Agent 失明",
                "Summary 与 revision 脱节会误导快速阅读",
                "子黑盒不落图会在 P1 时从大黑盒里凭空长出结构",
            ],
            "affected_module_ids": [
                "personal-ledger-core",
                "agent-runtime",
                "state-commit-engine",
                "durable-task-runtime",
                "interaction-layer",
            ],
            **ACTOR,
        },
    )
    print("plan", plan[0])

    # P0/P1/P2 as separate plan scopes
    for sid, goal, non_goals in [
        (
            "p0",
            "P0：消息→Event→Matter→People→Reminder→Capsule→纠正→表格 Inspector 最小闭环（Scenario A/C/E）。",
            ["不做全渠道", "不做向量记忆", "不做 WPS 深度集成", "不做背景智能"],
        ),
        (
            "p1",
            "P1：子事项树传播、Archive 召回、Knowledge/Product 正式启用、多 Ledger 扇出、备份/迁移。",
            ["不做多 Channel 产品化", "不做完整 Background Intelligence"],
        ),
        (
            "p2",
            "P2：多渠道、能力注册表全面接入、后台智能、可插拔 Memory 对比、多投影与工作流。",
            ["避免复杂 RBAC 官僚化"],
        ),
    ]:
        s, b = write(
            "POST",
            "/api/planning/plan-versions",
            lambda g, sid=sid, goal=goal, ng=non_goals: {
                "project_id": PID,
                "expected_generation": g,
                "id": f"plan-{sid}-v1",
                "planning_scope_id": sid,
                "goal": goal,
                "non_goals": ng,
                **ACTOR,
            },
        )
        print("plan", sid, s)

    # Acceptance A-G + X1-X6
    criteria = [
        ("ac-a", "Scenario A 日常承诺：用户说「明天下午提醒我联系李经理，合同还没盖章」→ Event+Matter+People+Reminder+Capsule；次日提醒送达；后续更新收敛同一 Matter；可恢复当前状态。"),
        ("ac-b", "Scenario B 长期资料：上传重要产品政策 → File/Source+Product/Knowledge；长期可检索；回答可追溯 Source，不烧成临时聊天 Matter。"),
        ("ac-c", "Scenario C 多轮事项：同一事项数日更新 → 始终同一 Matter；Event 追加；Capsule 增量；不生成重复事项。"),
        ("ac-d", "Scenario D 子事项：主项目含子项；子项变化只增量影响父摘要；无变化停止传播；不重扫整树。"),
        ("ac-e", "Scenario E 纠正：用户纠正人名/日期 → Source 不改；旧 Interpretation 失效；Correction 记录；后续 Context 用新值。"),
        ("ac-f", "Scenario F 归档召回：数月后提起旧事 → Archive 极小摘要命中；可展开完整历史；成本可控。"),
        ("ac-g", "Scenario G 多 Ledger：一条消息含人物+资料+事项+附件 → 多账本引用连接，非强制单分类；原文只存一份。"),
        ("ac-x1", "X1 幂等：重复提交/渠道重试不双写 Matter/Event/Reminder。"),
        ("ac-x2", "X2 可追溯：Capsule→Evidence→Source 链路可点开。"),
        ("ac-x3", "X3 可替换：换模型/Provider 后 Core 语义不变。"),
        ("ac-x4", "X4 可恢复：Derived 全丢可从 Canonical 重建。"),
        ("ac-x5", "X5 预算：长期数据增长后单次 Working Context 仍受控。"),
        ("ac-x6", "X6 高风险确认：删除/对外发送/金额类有确认；日常整理不刷屏。"),
        ("ac-x7", "X7 Summary 一致：summary.basis_revision == module.current_revision，否则标记 STALE 不得当现况。"),
        ("ac-x8", "X8 Project Identity Gate：project_key/uuid/root/canonical 不匹配则禁止写 canonical。"),
    ]
    for cid, desc in criteria:
        s, b = write(
            "POST",
            "/api/planning/acceptance",
            lambda g, cid=cid, desc=desc: {
                "project_id": PID,
                "expected_generation": g,
                "id": cid,
                "owner_type": "PROJECT",
                "description": desc,
                "origin_source": "USER",
                "status": "ACTIVE",
                "verification": "UNVERIFIED",
                **ACTOR,
            },
        )
        print("ac", cid, s)

    # Decisions
    decisions = [
        (
            "dec-identity",
            "Project Identity 是否必须进入 canonical 并作为硬门禁？",
            "必须进入 canonical（project_key/uuid/root/canonical/identity_hash），启动校验，失败 STOP",
            ["只写 docs/IDENTITY.md", "信任路径名当身份"],
            "docs 不是真源；绑错项目会污染其他工程。",
            ["personal-ledger-core", "operations"],
        ),
        (
            "dec-source-write",
            "Canonical 业务写入路径是什么？",
            "唯一写入口是 State/Commit Engine；读可多路",
            ["投影/Provider 直写", "Runtime 直写 blackbox"],
            "防止双真相与不可审计变更。",
            ["state-commit-engine", "personal-ledger-core", "projection-layer", "memory-fabric"],
        ),
        (
            "dec-subbb",
            "长期子系统是否现在拆成小黑盒？",
            "现在拆到「有独立状态/接口」粒度，lifecycle=PLANNED，不施工",
            ["P1 再拆", "全部塞 custom.in_scope 字符串"],
            "装修一个房间也要有完整图纸；避免 P1 凭空长结构。",
            ["personal-ledger-core", "context-engine", "interaction-layer"],
        ),
        (
            "dec-effect-receipt",
            "外部副作用是否需要 canonical 收据？",
            "高副作用能力必须留下 Effect Receipt（capability/target/result/external_ref）",
            ["只写 tool log", "不做收据"],
            "账本可审计，但对外做过的动作也必须可证明。",
            ["capability-registry", "source-evidence"],
        ),
        (
            "dec-durable-writeback",
            "提醒完成后谁改 Matter？",
            "Durable 只发 TaskLifecycleEvent/Proposal → State/Commit 再写账本",
            ["Durable 直写 Matter", "只关通知不改状态"],
            "保持唯一写入口与提醒-事项一致。",
            ["durable-task-runtime", "state-commit-engine"],
        ),
        (
            "dec-directive-enforcement",
            "Directive 只作用于 Context 吗？",
            "Directive 是策略：Agent 动作/提醒投递/外部能力/投影自动化都过 Policy Evaluation",
            ["只给模型看", "每个模块各自判断"],
            "避免 22:30 仍发出「晚上不提醒工作」。",
            ["context-engine", "durable-task-runtime", "capability-registry"],
        ),
        (
            "dec-file-source-split",
            "File Ledger 与 Source & Evidence 如何分界？",
            "File Ledger=资料语义与关联；Source & Evidence=bytes/版本/哈希/存放",
            ["两模块都管文件实体", "合并成一个"],
            "消除「文件归我管」冲突。",
            ["personal-ledger-core", "source-evidence"],
        ),
        (
            "dec-evidence-scope",
            "evidence_refs 是否对所有回答强制？",
            "仅当回答依赖用户个人状态/用户资料/Ledger/文档事实时要求可追溯；常识问答不锁死",
            ["一切事实主张都强制 evidence_refs", "完全不要证据"],
            "模型是润滑剂，不为防错锁死正常能力。",
            ["source-evidence", "agent-runtime"],
        ),
    ]
    for did, q, choice, alts, rationale, affected in decisions:
        s, b = write(
            "POST",
            "/api/planning/decisions",
            lambda g, did=did, q=q, choice=choice, alts=alts, rationale=rationale, affected=affected: {
                "project_id": PID,
                "expected_generation": g,
                "id": did,
                "owner_type": "PROJECT",
                "question": q,
                "selected_choice": choice,
                "alternatives": alts,
                "rationale": rationale,
                "affected_owner_ids": affected,
                **ACTOR,
            },
        )
        print("dec", did, s)

    # Open questions
    questions = [
        ("q-template-v2", "general-module-v1 的 custom 是否应升级为 architecture-module-v2（正式 schema 化 responsibilities/actions/in_scope）？", True),
        ("q-project-desc-api", "project.description 写入是否缺少稳定 API？Identity 现以 planning binding + decision 记录。", False),
        ("q-wps-projection", "WPS 多维表 Projection Adapter 的字段映射版本化方案（P1）。", False),
    ]
    for qid, q, blocking in questions:
        s, b = write(
            "POST",
            "/api/planning/questions",
            lambda g, qid=qid, q=q, blocking=blocking: {
                "project_id": PID,
                "expected_generation": g,
                "id": qid,
                "owner_type": "PROJECT",
                "question": q,
                "impact": "规划完整性" if blocking else "后续实现",
                "blocking": blocking,
                **ACTOR,
            },
        )
        print("q", qid, s)

    # Evidence pointing at docs
    evidences = [
        ("ev-docs-identity", "docs/IDENTITY.md", "项目身份文档（非唯一真源，供交叉核对）"),
        ("ev-docs-acceptance", "docs/scenarios/acceptance.md", "Scenario A-G 与 X 验收原文"),
        ("ev-docs-interaction", "docs/interaction-audit.md", "黑盒间交互审计与合格轨迹"),
    ]
    for eid, path, note in evidences:
        s, b = write(
            "POST",
            "/api/planning/evidence",
            lambda g, eid=eid, path=path, note=note: {
                "project_id": PID,
                "expected_generation": g,
                "id": eid,
                "kind": "DOCUMENT",
                "path": path,
                "summary": note,
                **ACTOR,
            },
        )
        print("ev", eid, s, b if s >= 300 else "")


# ---------- 2) Refresh parent summaries (fix basis_revision lag) ----------
PARENT_SUMMARIES = {
    "interaction-layer": "多渠道消息进出管道：接收/规范化/投递/跨渠道身份映射；不持有事项状态。子系统：接入、规范化、投递、身份映射。",
    "agent-runtime": "可替换模型发动机：编排 Turn、调用工具契约、产出回复与账本操作提案；不直写真源。",
    "context-engine": "编译 Working Context、多账本路由、检索与预算，并统一评估 Directive/执行策略。",
    "personal-ledger-core": "唯一业务真源：事项当前状态+事件历史+人物/知识/产品/文件目录/指令/归档；Source 与解释分离。",
    "source-evidence": "保存不可变原文、附件版本、哈希与溯源；纠正只失效解释；对外副作用可挂 Effect Receipt 证据。",
    "state-commit-engine": "Canonical 唯一写入闸门：校验/补丁/纠正/冲突/幂等/高风险确认；接受 Durable 任务回写提案。",
    "summary-system": "增量 Context Capsule 与父子脏传播；与 current_revision 对齐，禁止悄悄陈旧。",
    "memory-fabric": "HOT/WARM/COLD 与可插拔 Provider；只做召回加速与提案，可整体重建。",
    "durable-task-runtime": "提醒/延迟/定时/恢复；到期经交互层投递；完成/改期经 TaskAction 回写提交引擎。",
    "capability-registry": "工具契约与权限；高副作用产生 Effect Receipt；未注册能力显式失败。",
    "projection-layer": "表格/Web/App 投影；用户编辑经 UserEditOp→提交引擎；产品可更换。",
    "operations": "诊断/追踪/备份迁移/模型与 Provider 配置；横切可恢复与可换模。",
}


def refresh_summaries():
    print("== summaries ==")
    for mid, text in PARENT_SUMMARIES.items():
        s, b = write(
            "PUT",
            f"/api/modules/{mid}/summary",
            lambda g, t=text: {
                "project_id": PID,
                "expected_generation": g,
                "text": t,
                **ACTOR,
            },
        )
        print("summary", mid, s)


# ---------- 3) Interface gap edges ----------
def add_edges():
    print("== edges ==")
    edges = [
        ("durable-task-runtime", "state-commit-engine", "produces_for"),
        ("capability-registry", "source-evidence", "produces_for"),
        ("capability-registry", "operations", "related_to"),
        ("context-engine", "durable-task-runtime", "references"),
        ("interaction-layer", "personal-ledger-core", "references"),
    ]
    for src, tgt, rt in edges:
        s, b = write(
            "POST",
            "/api/relations",
            lambda g, s=src, t=tgt, rt=rt: {
                "project_id": PID,
                "expected_generation": g,
                "source": s,
                "target": t,
                "relation_type": rt,
                **ACTOR,
            },
        )
        print("rel", src, "->", tgt, s)


# ---------- 4) Loosen over-constraints ----------
def fix_constraints():
    print("== constraints ==")
    # agent-runtime rev 3 exists; commit rev 4 with adjusted constraints
    agent = spec(
        purpose="可替换的模型循环发动机：理解用户输入、选择工具、产出 Reply 与 Ledger Operations；边界严格、内部自由。",
        narrative="用户一句话改主持信息→单轮完成理解+账本操作+回复；纠正一句即对齐；常识问答不因缺个人证据而拒答。",
        outcomes=[
            "换模型不改 Personal Ledger Core",
            "单 Turn 可同时产生 Reply 与 Ledger Operations",
            "工具调用经 Capability Registry",
            "个人状态/资料类主张可追溯；常识问题正常回答",
        ],
        failures=[
            "业务状态锁死在 harness 会话",
            "绕过 Commit 直写账本",
            "因缺 evidence 而拒绝常识问答",
            "第三方框架反向定义产品模块名",
        ],
        constraints=[
            "运行时可替换；禁止把 harness Session 当 Matter 真源",
            "只经 Capability Registry 调用工具",
            "单 Turn 输出可解析为 Reply + LedgerOperations[]（幂等 op_id）",
            "高风险动作先 Permission；常规内部整理免确认",
            "「最多问 3 个问题」「先假设后改」是 UX 启发式，不是架构铁律",
        ],
        custom={
            "responsibilities": ["模型循环", "工具调用", "Turn 编排", "操作提案"],
            "actions": ["run_turn", "emit_ledger_ops", "request_confirmation", "apply_correction_from_speech"],
            "in_scope": ["model-adapter", "turn-orchestrator", "tool-invoker", "ledger-ops-proposer"],
            "out_of_scope": ["Canonical 存储", "提醒调度执行", "表格渲染"],
            "user_moments": ["一句话改完并看懂改动", "纠正立即生效"],
            "ux_scorecard": ["简单修改 1 轮完成", "追问克制", "无假成功"],
        },
    )
    s, _ = write(
        "POST",
        "/api/modules/agent-runtime/spec",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "base_revision": 3,
            "spec": agent,
            **ACTOR,
        },
    )
    print("spec agent-runtime", s)

    source = spec(
        purpose="保存原文/附件/版本/哈希与溯源链；支撑个人状态与文档事实的证据下钻；纠正不销毁原件。",
        narrative="政策 PDF 存源→问答可点到页码；用户更正费率后原件仍在、旧摘要作废；常识问答不需要 ledger 证据。",
        outcomes=[
            "依赖用户资料/Ledger/文档的主张可追溯到 Source",
            "纠正后原件保留且旧解释失效",
            "缺证据时对「应可核验」的问题明说未找到",
            "版本与哈希可核对",
        ],
        failures=[
            "改写原话/原文件",
            "编造页码",
            "对常识问答强行要求 evidence_refs",
            "同名覆盖丢版本",
        ],
        constraints=[
            "Raw Source 只读；纠正只作用于解释层",
            "当回答依赖用户个人状态、用户资料、Ledger 信息或要求可核验的文档事实时，必须能追溯证据",
            "普通常识/技能问答不受 evidence 强制约束",
            "缺失存储报「证据损坏」，不用旧摘要顶替",
        ],
        custom={
            "responsibilities": ["原文只读存储", "附件版本", "溯源", "证据解析"],
            "actions": ["store_raw_source", "resolve_evidence", "mark_interpretation_invalid", "attach_effect_receipt"],
            "in_scope": ["raw-source-store", "attachment-store", "provenance-chain", "source-versioning", "effect-receipt-store"],
            "out_of_scope": ["资料业务语义归类（File Ledger）", "账本字段权威"],
        },
    )
    s, _ = write(
        "POST",
        "/api/modules/source-evidence/spec",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "base_revision": 3,
            "spec": source,
            **ACTOR,
        },
    )
    print("spec source-evidence", s)


# ---------- 5) Sub-blackboxes ----------
def mini(mid, name, summary, purpose, parent, x, y):
    return {
        "id": mid,
        "name": name,
        "summary": summary,
        "x": x,
        "y": y,
        "visual_group_id": parent,
        "spec": spec(
            purpose=purpose,
            narrative=f"作为「{parent}」的子黑盒：{summary}",
            outcomes=["接口语义稳定", "可独立替换/测试", "不越权写其他黑盒真源"],
            failures=["职责越界", "接口漂移无版本", "静默吞错"],
            constraints=["生命周期可为 PLANNED 不施工", "遵守父级 Boundary Contract", "不拥有父级以外的 Canonical 真源"],
            custom={"parent": parent, "planned_not_implemented": True},
        ),
    }


def create_subblackboxes():
    print("== sub blackboxes ==")
    groups = {
        "group-interaction": [
            ("inbound-message-gateway", "消息接入网关", "接收企微/Web/App/邮件等入站消息与附件引用", "把外部入口的收消息能力抽象为独立黑盒：鉴权、限流、原始投递确认。"),
            ("message-normalizer", "消息规范化", "外部消息→统一 Message Envelope", "产出 message_id/channel/user_ref/ts/payload/attachments/provenance。"),
            ("delivery-router", "投递路由", "把 Reply/Notification 送到用户真实入口", "选路、去重、补送、回执；不私连渠道 SDK 之外的业务写。"),
            ("channel-identity-mapping", "渠道身份映射", "跨渠道 Principal 映射与改绑", "长期保存 WeCom/Web/App 身份映射；可拆开/改绑；冲突时以 People 语义为准。"),
        ],
        "group-runtime": [
            ("model-adapter", "模型适配器", "多 Provider 模型接入与降级", "可替换模型；超时降级；不持有账本。"),
            ("turn-orchestrator", "Turn 编排", "单轮理解-工具-操作-回复", "产出 Reply+LedgerOperations；避免无意义串行多次模型调用。"),
            ("tool-invoker", "工具调用器", "经 Registry 调用工具", "只认契约名与 schema；标准化错误。"),
            ("ledger-ops-proposer", "账本操作提案", "把模型意图变成幂等 Ledger Ops", "op_id；高风险标注；不做长总结。"),
        ],
        "group-context": [
            ("working-context-compiler", "Working Context 编译", "按预算组装本次上下文", "活跃 Matter 胶囊+人物+知识+Directive；可解释来源。"),
            ("ledger-router", "账本路由器", "判断信息进入哪些 Ledger", "允许扇出；可纠正；非硬锁。"),
            ("memory-retriever", "记忆检索器", "从 Memory Fabric/账本召回", "降级到 Compact Capsule；标注来源。"),
            ("context-budget-policy", "上下文预算策略", "Token 与优先级裁剪", "多因子热度；禁止纯时间一刀切。"),
            ("directive-policy-evaluator", "指令策略评估", "Directive 作为执行策略统一裁决", "覆盖 Agent 动作、提醒投递、外部能力、投影自动化。"),
        ],
        "group-core": [
            ("matter-ledger", "事项账本", "事项当前状态树与下一步", "单一当前真相；相似合并建议；父子层级。"),
            ("event-ledger", "事件账本", "历史事件流", "追加式；关联 Matter/People/File。"),
            ("people-ledger", "人物账本", "长期人物与关系", "单位/角色/承诺/相关事项。"),
            ("knowledge-ledger", "知识账本", "稳定知识与经验", "按需读取；不与日常事项混写。"),
            ("product-ledger", "产品业务账本", "产品/政策/资费/参数资料", "长期业务资料语义目录。"),
            ("file-ledger", "资料目录账本", "这是什么资料、关联谁/何事", "语义与关联；bytes 归 Source。"),
            ("directive-ledger", "指令账本", "用户长期规则", "被 Policy Evaluator 与 Context 消费。"),
            ("archive-ledger", "归档账本", "极小召回摘要+指针", "归档≠删除。"),
        ],
        "group-evidence": [
            ("raw-source-store", "原文存储", "不可变原始内容", "hash+内容；只读。"),
            ("attachment-store", "附件存储", "文件对象与预览", "版本目录；失败可见。"),
            ("provenance-chain", "溯源链", "谁/何时/从哪来", "证据指针可解析。"),
            ("source-versioning", "源版本", "多版本与过期标记", "禁止同名覆盖。"),
            ("effect-receipt-store", "副作用收据", "外部动作 Receipt", "effect_id/capability/target/result/external_ref。"),
        ],
        "group-commit": [
            ("op-validator", "操作校验", "Ledger Op schema/权限/幂等", "拒绝非法与重复。"),
            ("patch-committer", "补丁提交", "原子落账本与引用", "CAS；ChangeSet。"),
            ("correction-applier", "纠正执行", "失效旧解释并更新当前态", "审计旧→新。"),
            ("conflict-resolver", "冲突处理", "相似 Matter/并发字段", "可拆分合并。"),
            ("change-receipt", "变更回执", "用户可见成功/失败回执", "仅 commit 成功才称成功。"),
        ],
        "group-summary": [
            ("capsule-store", "胶囊存储", "Context Capsule 读写", "结构固定；带 evidence。"),
            ("incremental-reducer", "增量摘要器", "old+patch→new", "禁止默认全量。"),
            ("tree-propagator", "树传播器", "子→父脏传播", "无变化即停。"),
            ("dirty-tracker", "脏跟踪", "标记待更新节点", "与 revision 对齐。"),
        ],
        "group-memory": [
            ("hot-warm-cold-tier", "热度分层", "HOT/WARM/COLD/RAW", "多因子；可重建。"),
            ("semantic-index", "语义索引", "向量/语义召回", "Derived。"),
            ("relation-index", "关系索引", "实体关系召回", "Derived。"),
            ("memory-provider-adapter", "记忆 Provider 适配", "Mem0/Graphiti/本地", "可拔插；不写真源。"),
            ("consolidation-proposer", "整理提案器", "去重/降温/合并建议", "仅 Proposal。"),
        ],
        "group-durable": [
            ("reminder-scheduler", "提醒调度", "到期提醒任务", "持久化+幂等触发。"),
            ("delayed-scheduled-runner", "延迟定时执行", "Delay/Schedule 执行", "重启存活。"),
            ("task-resume", "任务恢复", "中断恢复与补送", "Resume 语义。"),
            ("task-action-bridge", "任务动作桥", "complete/snooze→Ledger Op 提案", "经 State/Commit 回写 Matter，不直写。"),
        ],
        "group-capability": [
            ("tool-contract-registry", "工具契约注册", "name/io/side_effects", "未注册显式失败。"),
            ("permission-gate", "权限门禁", "高副作用确认", "external/high-risk。"),
            ("effect-receipt-emitter", "副作用收据发生器", "调用后写 Receipt", "成功/失败/外部 id。"),
            ("external-service-adapter", "外部服务适配", "MCP/HTTP/本地工具", "实现可替换。"),
        ],
        "group-projection": [
            ("table-projection", "表格投影", "多维表/Web 表渲染", "默认「我的事项」。"),
            ("web-projection", "Web 投影", "浏览器 UI", "可替换。"),
            ("edit-to-patch-adapter", "编辑回写适配", "UserEditOp→Ledger Op", "回执后落 UI 终值。"),
        ],
        "group-ops": [
            ("diagnostics", "诊断", "身份/generation/缓存/渠道健康", "脱敏。"),
            ("tracing", "链路追踪", "消息→提交→投递", "可定位 op_id。"),
            ("backup-restore", "备份恢复", "Canonical+Source", "恢复预检。"),
            ("migration-runner", "迁移执行", "schema/数据迁移", "幂等可审计。"),
            ("provider-config", "模型 Provider 配置", "换模与连通测试", "不迁业务数据。"),
        ],
    }

    created = 0
    for group_id, items in groups.items():
        for i, (mid, name, summary, purpose) in enumerate(items):
            body_mod = mini(mid, name, summary, purpose, group_id, 40 + (i % 4) * 220, 40 + (i // 4) * 140)
            s, b = write(
                "POST",
                "/api/map-import",
                lambda g, mods=[body_mod], rels=[]: {
                    "project_id": PID,
                    "expected_generation": g,
                    "default_template_version_id": TMPL,
                    "modules": mods,
                    "relations": rels,
                    **ACTOR,
                },
            )
            # if map-import requires >=1 modules only, single is fine
            print("sub", mid, s)
            if s < 300:
                created += 1
            elif s == 409 or (isinstance(b, dict) and "ALREADY" in str(b)):
                # try create module endpoint
                s2, b2 = write(
                    "POST",
                    "/api/modules",
                    lambda g, m=body_mod: {
                        "project_id": PID,
                        "expected_generation": g,
                        "id": m["id"],
                        "name": m["name"],
                        "summary": m["summary"],
                        "x": m["x"],
                        "y": m["y"],
                        "visual_group_id": m["visual_group_id"],
                        "template_version_id": TMPL,
                        "spec": m["spec"],
                        **ACTOR,
                    },
                )
                print("sub-fallback", mid, s2)
                if s2 < 300:
                    created += 1
        # parent contains children
        parent = {
            "group-interaction": "interaction-layer",
            "group-runtime": "agent-runtime",
            "group-context": "context-engine",
            "group-core": "personal-ledger-core",
            "group-evidence": "source-evidence",
            "group-commit": "state-commit-engine",
            "group-summary": "summary-system",
            "group-memory": "memory-fabric",
            "group-durable": "durable-task-runtime",
            "group-capability": "capability-registry",
            "group-projection": "projection-layer",
            "group-ops": "operations",
        }[group_id]
        for mid, *_ in items:
            s, b = write(
                "POST",
                "/api/relations",
                lambda g, p=parent, c=mid: {
                    "project_id": PID,
                    "expected_generation": g,
                    "source": p,
                    "target": c,
                    "relation_type": "contains",
                    **ACTOR,
                },
            )
            if s >= 300 and isinstance(b, dict) and "ALREADY" not in str(b):
                # ignore duplicates
                pass
            print("contains", parent, "->", mid, s)
    print("created_subs", created)


def main():
    print("start_gen", gen())
    seed_planning()
    refresh_summaries()
    add_edges()
    fix_constraints()
    create_subblackboxes()
    print("end_gen", gen())


if __name__ == "__main__":
    main()
