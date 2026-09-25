# -*- coding: utf-8 -*-
"""g000233 independent-review fix pass: contains, policy edges, contracts, plan binding, question/RC semantics."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4319"
PID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}


def gen():
    with urllib.request.urlopen(BASE + "/api/repo-status") as r:
        return json.loads(r.read().decode())["repository_generation"]


def call(method, path, body=None):
    data = None
    headers = {"X-BBM-Expected-Project-Id": PID, "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def write(method, path, make_body, attempts=8):
    last = None
    for _ in range(attempts):
        g = gen()
        s, b = call(method, path, make_body(g))
        if s < 300:
            return s, b
        code = (b or {}).get("error", {}).get("code") if isinstance(b, dict) else None
        last = (s, b)
        if code == "GENERATION_CONFLICT":
            time.sleep(0.08)
            continue
        return s, b
    return last


def contract(summary, provides, requires, assumptions, guarantees, side_effects,
             failure_impacts, change_impacts, forbidden_couplings, mitigation_notes):
    return {
        "summary": summary,
        "provides": provides,
        "requires": requires,
        "assumptions": assumptions,
        "guarantees": guarantees,
        "side_effects": side_effects,
        "failure_impacts": failure_impacts,
        "change_impacts": change_impacts,
        "forbidden_couplings": forbidden_couplings,
        "mitigation_notes": mitigation_notes,
    }


def main():
    print("start", gen())

    # 1) missing contains for 4 core ledgers
    print("== contains ==")
    for c in ["matter-ledger", "event-ledger", "people-ledger", "knowledge-ledger"]:
        s, b = write(
            "POST",
            "/api/relations",
            lambda g, c=c: {
                "project_id": PID,
                "expected_generation": g,
                "source": "personal-ledger-core",
                "target": c,
                "relation_type": "contains",
                **ACTOR,
            },
        )
        print("contains", c, s)

    # 2) directive policy evaluation edges
    print("== policy edges ==")
    for src, tgt, rt in [
        ("durable-task-runtime", "directive-policy-evaluator", "depends_on"),
        ("capability-registry", "directive-policy-evaluator", "depends_on"),
        ("projection-layer", "directive-policy-evaluator", "depends_on"),
        ("agent-runtime", "directive-policy-evaluator", "depends_on"),
    ]:
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
        print("policy", src, "->", tgt, s)

    # 3) boundary contracts on critical cross-box protocols
    print("== contracts ==")
    contracts = {
        "rel-durable-task-runtime-state-commit-engine-produces_for": contract(
            summary="持久任务完成/改期/取消只产生 TaskActionProposal / TaskLifecycleEvent，经 State/Commit 写入 Matter；Durable 绝不直写账本。",
            provides=[
                "TaskActionProposal{action=complete|snooze|reschedule|cancel, task_id, matter_ref, due?, op_id}",
                "TaskLifecycleEvent{task_id, phase=created|due|fired|failed|closed, at, receipt_ref?}",
                "幂等键：op_id（客户端/调度器生成，重复投递不双写）",
            ],
            requires=[
                "State/Commit 校验并原子提交；返回 change receipt",
                "提交失败时任务状态保持 pending/retry，不得标完成",
            ],
            assumptions=["task_id 与 matter_ref 可解析", "时钟与时区明确"],
            guarantees=["Matter 只经 Commit 变更", "complete 后下一步/状态可同步", "失败可观测可重试"],
            side_effects=["账本 generation 变化", "可能触发摘要 Dirty", "可能触发后续提醒关闭"],
            failure_impacts=["直写 Matter 会破坏唯一写入口", "假 complete 会导致状态与提醒不一致"],
            change_impacts=["TaskAction schema 变更影响提醒卡片与提交引擎"],
            forbidden_couplings=["Durable 直接 update Matter 字段", "无 op_id 的裸触发写入", "失败仍标记 completed"],
            mitigation_notes=["op 幂等", "retry/backoff", "完成后写 Effect/Change receipt"],
        ),
        "rel-capability-registry-source-evidence-produces_for": contract(
            summary="高副作用工具执行后必须写 Effect Receipt 到 Source/Evidence 侧存储；账本可审计，对外动作也可证明。",
            provides=[
                "EffectReceipt{effect_id, capability, request_digest, target, result, external_ref, timestamp, evidence_ref?}",
                "失败/取消也写 receipt（result=failed|cancelled）",
            ],
            requires=["Source/Evidence 持久化 receipt 并可按 effect_id 检索", "成功后才允许 Reply 声称外部动作完成"],
            assumptions=["capability 已注册且 permission 通过", "目标外部系统可回传 ref 或明确无 ref"],
            guarantees=["对外副作用有 canonical 证明链", "无 receipt 的高副作用调用视为未完成"],
            side_effects=["外部系统真实副作用", "Evidence 存储增长"],
            failure_impacts=["无收据则无法证明发过邮件/改过外部文件"],
            change_impacts=["Receipt 字段变更影响审计与追踪"],
            forbidden_couplings=["只写本地 tool log 当收据", "成功但不写 receipt", "用 Receipt 反写 Source 原文"],
            mitigation_notes=["receipt 与 op_id/turn_id 关联", "存储缺失报证据损坏", "P0 可先只对 high-risk 启用"],
        ),
        "rel-durable-task-runtime-directive-policy-evaluator-depends_on": contract(
            summary="提醒到期投递前必须经 Directive Policy Evaluation（如晚上十点后不发工作提醒）。",
            provides=["PolicyDecision{allow|deny|defer, directive_ids, reason}"],
            requires=["Durable 在 fire/deliver 前调用；deny/defer 不得静默丢失任务，改为改期或进未送达策略"],
            assumptions=["Directive Ledger 有可评估规则"],
            guarantees=["Directive 优先于单纯到点触发"],
            side_effects=["提醒可能被推迟或合并"],
            failure_impacts=["忽略 Policy 会违反用户长期规则"],
            change_impacts=["规则语言变更影响评估器"],
            forbidden_couplings=["绕过 Policy 直发", "deny 后任务静默消失"],
            mitigation_notes=["决策留痕", "defer 有明确下次评估时间"],
        ),
        "rel-capability-registry-directive-policy-evaluator-depends_on": contract(
            summary="高副作用外部能力执行前过 Directive Policy（如不要自动外发合同类内容）。",
            provides=["PolicyDecision for capability invoke"],
            requires=["Permission + Policy 双门禁", "deny 时不得调用外部服务"],
            assumptions=["Directive 含外部动作约束"],
            guarantees=["策略拒绝可解释"],
            side_effects=["可能阻止外部动作"],
            failure_impacts=["违策外发不可逆"],
            change_impacts=["Directive 结构变更影响门禁"],
            forbidden_couplings=["跳过 Policy", "用 Retry 规避 deny"],
            mitigation_notes=["deny 记入 receipt/tracing"],
        ),
    }
    for rid, c in contracts.items():
        # try base 0 then existing revision
        s, b = write(
            "PUT",
            f"/api/relations/{rid}/boundary-contract",
            lambda g, rid=rid, c=c: {
                "project_id": PID,
                "expected_generation": g,
                "relation_id": rid,
                "base_revision": 0,
                "contract": c,
                **ACTOR,
            },
        )
        if s >= 300:
            st, existing = call("GET", f"/api/relations/{rid}/boundary-contract", None)
            rev = 0
            if st < 300 and isinstance(existing, dict):
                rev = int(existing.get("revision") or existing.get("current_revision") or 0)
            s, b = write(
                "PUT",
                f"/api/relations/{rid}/boundary-contract",
                lambda g, rid=rid, c=c, rev=rev: {
                    "project_id": PID,
                    "expected_generation": g,
                    "relation_id": rid,
                    "base_revision": rev,
                    "contract": c,
                    **ACTOR,
                },
            )
        print("contract", rid, s)

    # 4) planning: new plan versions with affected_module_ids + module-owned AC bindings
    print("== planning bind ==")
    p0_modules = [
        "interaction-layer",
        "agent-runtime",
        "context-engine",
        "personal-ledger-core",
        "state-commit-engine",
        "source-evidence",
        "summary-system",
        "durable-task-runtime",
        "projection-layer",
        "inbound-message-gateway",
        "message-normalizer",
        "turn-orchestrator",
        "ledger-ops-proposer",
        "matter-ledger",
        "event-ledger",
        "people-ledger",
        "op-validator",
        "patch-committer",
        "correction-applier",
        "reminder-scheduler",
        "task-action-bridge",
        "incremental-reducer",
        "capsule-store",
    ]
    p1_modules = [
        "personal-ledger-core",
        "summary-system",
        "knowledge-ledger",
        "product-ledger",
        "archive-ledger",
        "file-ledger",
        "memory-fabric",
        "operations",
        "tree-propagator",
        "hot-warm-cold-tier",
    ]
    p2_modules = [
        "interaction-layer",
        "capability-registry",
        "memory-fabric",
        "projection-layer",
        "operations",
        "durable-task-runtime",
        "context-engine",
        "effect-receipt-emitter",
        "external-service-adapter",
    ]
    for sid, goal, mods in [
        ("p0", "P0 闭环：消息→Event→Matter→People→Reminder→Capsule→Correction→表格 Inspector（Scenario A/C/E）。绑定直接施工黑盒，避免执行者从文本猜范围。", p0_modules),
        ("p1", "P1：子事项传播、Archive 召回、Knowledge/Product、多 Ledger 扇出、备份迁移。", p1_modules),
        ("p2", "P2：多渠道、能力注册全面接入、后台智能、多投影。", p2_modules),
    ]:
        s, b = write(
            "POST",
            "/api/planning/plan-versions",
            lambda g, sid=sid, goal=goal, mods=mods: {
                "project_id": PID,
                "expected_generation": g,
                "id": f"plan-{sid}-v2",
                "planning_scope_id": sid,
                "goal": goal,
                "affected_module_ids": mods,
                "target_entity_ids": mods,
                "non_goals": ["不提前施工非本阶段能力", "不把第三方框架当 Core"],
                **ACTOR,
            },
        )
        print("plan-v2", sid, s)

    # AC module bindings (add module-owned criteria for P0 core scenarios)
    ac_binds = [
        ("ac-a-binding", "MODULE", "personal-ledger-core", "Scenario A 执行绑定：P0 必须打通 Matter/Event/People/Reminder/Capsule 最小闭环。"),
        ("ac-c-binding", "MODULE", "matter-ledger", "Scenario C 执行绑定：多轮更新收敛同一 Matter，不重复建项。"),
        ("ac-e-binding", "MODULE", "state-commit-engine", "Scenario E 执行绑定：Correction 经 Commit，Source 不改。"),
        ("ac-x1-binding", "MODULE", "op-validator", "X1 执行绑定：op_id 幂等，重试不双写。"),
    ]
    for cid, ot, oid, desc in ac_binds:
        s, b = write(
            "POST",
            "/api/planning/acceptance",
            lambda g, cid=cid, ot=ot, oid=oid, desc=desc: {
                "project_id": PID,
                "expected_generation": g,
                "id": cid,
                "owner_type": ot,
                "owner_id": oid,
                "description": desc,
                "origin_source": "USER",
                "status": "ACTIVE",
                "verification": "UNVERIFIED",
                **ACTOR,
            },
        )
        print("ac-bind", cid, s)

    # 5) q-template-v2: resolve as deferred / non-blocking
    s, b = write(
        "POST",
        "/api/planning/questions/q-template-v2/resolve",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "resolution": "DEFERRED_NON_BLOCKING：architecture-module-v2 属于 BBM 质量改进，不阻塞拾光 P0。原 blocking=true 不当，按产品取向改为 deferred。",
            **ACTOR,
        },
    )
    print("resolve q-template-v2", s)
    s, b = write(
        "POST",
        "/api/planning/questions",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "id": "q-template-v2-deferred",
            "owner_type": "PROJECT",
            "question": "architecture-module-v2 模板 schema 化（responsibilities/actions/in_scope）何时做？",
            "impact": "BBM 质量，不挡 P0",
            "blocking": False,
            **ACTOR,
        },
    )
    print("q-template deferred", s)

    # 6) Identity RC: supersede with explicit ACCEPTED_BUT_NOT_IMPLEMENTED semantics
    s, b = write(
        "POST",
        "/api/planning/requirement-changes",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "id": "rc-identity-gate-status",
            "planning_scope_id": "project",
            "title": "Identity 硬门禁状态更正：目标已确认，实现未完成",
            "before": "rc-identity-gate 的 after 易被读成「Identity Gate 已实现」；实际上 project.description 为空、bindings=[]，仅有 planning 意图记录。",
            "after": "状态=ACCEPTED_BUT_NOT_IMPLEMENTED。目标不变：canonical 固定 project_key/uuid/root/canonical/repo 且启动校验不匹配 STOP；但原生 schema/API 完成前不得宣称门禁已存在。q-project-desc-api 仍为前置。",
            "reason": "项目刚发生过绑错 BBM 事故；目标态与实现态必须区分，避免后续 Agent 误判。",
            "impact_class": "HIGH",
            "affected_owner_ids": ["operations"],
            "source": "independent-review-8a685d3",
        },
    )
    print("rc identity status", s)

    # evidence linking review fix
    s, b = write(
        "POST",
        "/api/planning/evidence",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "id": "ev-review-fix-g000233",
            "owner_type": "PROJECT",
            "owner_id": PID,
            "evidence_type": "OBSERVATION",
            "claim": "独立审核六项收边已核并修复",
            "result": "补 4 contains；补 Policy 边；补 Durable/Capability Boundary Contract；Plan v2 绑定模块；q-template-v2 改 deferred；Identity RC 标 ACCEPTED_BUT_NOT_IMPLEMENTED",
            "source_ref": "docs/bbm-closure-audit.md",
            "limitations": "Identity 原生 API 仍未实现",
            **ACTOR,
        },
    )
    print("evidence", s)

    print("end", gen())


if __name__ == "__main__":
    main()
