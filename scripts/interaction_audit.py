# -*- coding: utf-8 -*-
"""Inter-blackbox interaction audit: add missing edges + boundary contracts."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4319"
PID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}


def status_gen():
    req = urllib.request.Request(BASE + "/api/repo-status")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["repository_generation"]


def call(method, path, body):
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "X-BBM-Expected-Project-Id": PID},
        method=method,
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def write(method, path, make_body, attempts=8):
    last = None
    for _ in range(attempts):
        gen = status_gen()
        s, b = call(method, path, make_body(gen))
        if s < 300:
            return s, b
        code = (b or {}).get("error", {}).get("code") if isinstance(b, dict) else None
        last = (s, b)
        if code == "GENERATION_CONFLICT":
            time.sleep(0.12)
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


NEW_RELATIONS = [
    # 提醒/通知必须经交互层送达
    ("durable-task-runtime", "interaction-layer", "produces_for"),
    # 表格编辑不得直写账本，必须走提交引擎
    ("projection-layer", "state-commit-engine", "produces_for"),
    # 提交后驱动摘要脏标记/胶囊增量
    ("state-commit-engine", "summary-system", "produces_for"),
    # 记忆整理只能提案，不能直写
    ("memory-fabric", "state-commit-engine", "produces_for"),
    # 运行时可经工具下钻证据
    ("agent-runtime", "source-evidence", "depends_on"),
    # 运维横切关键出口
    ("operations", "interaction-layer", "related_to"),
    ("operations", "durable-task-runtime", "related_to"),
    ("operations", "memory-fabric", "related_to"),
    ("operations", "projection-layer", "related_to"),
    # 上下文编译会读摘要（已有 depends_on summary）— 保留
]

# Critical handoff contracts: relation_id = rel-{source}-{target}-{type}
CONTRACTS = {
    "rel-interaction-layer-agent-runtime-produces_for": contract(
        summary="交互层把多渠道输入规范成统一 Message Envelope 交给智能体运行时；回复/通知由交互层按用户入口投递。业务状态绝不放在渠道会话里。",
        provides=[
            "Message Envelope：message_id, channel, user_ref, ts, text/payload, attachments[], provenance",
            "用户活跃入口偏好（用于提醒投递）",
            "投递回执：delivered | retrying | failed",
        ],
        requires=[
            "运行时消费 Envelope 后必须经 State/Commit 落账，不得把 Envelope 当账本",
            "跨渠道 user_ref 合并错误可被 Correction 拆开",
        ],
        assumptions=["渠道至少可收文本；附件能力可降级但不可假装成功", "同一用户跨渠道身份可映射"],
        guarantees=["幂等 message_id 防重放", "附件哈希可追溯", "失败送达可见并可补送"],
        side_effects=["渠道侧已读/已发状态", "通知可能触发设备响铃"],
        failure_impacts=["运行时拿不到 Envelope 会无法记账", "投递失败用户会错过提醒"],
        change_impacts=["Envelope schema 变更影响全部渠道与运行时", "身份映射变更影响跨渠道连续感"],
        forbidden_couplings=["把 Channel 私有字段当 Matter 主键", "在交互层写 Matter 状态", "用渠道会话历史替代 Event"],
        mitigation_notes=["schema 版本化", "投递重试去重", "身份合并提供改绑入口"],
    ),
    "rel-agent-runtime-context-engine-depends_on": contract(
        summary="运行时每次 Turn 向上下文引擎申请 Working Context；引擎只读账本/记忆/摘要，不写业务状态。",
        provides=[
            "Working Context：活跃 Matter 胶囊、人物卡、相关知识、Directive、token 预算说明",
            "路由建议：本条输入可能落入的 Ledger 列表",
            "证据不足标记（避免运行时编造）",
        ],
        requires=["运行时不得绕过引擎拼全量历史", "路由结果可纠正，不是硬分类锁"],
        assumptions=["上下文引擎可降级到 Compact Capsule", "Directive 优先于相关性"],
        guarantees=["单次 Context 受 Budget 约束", "含 evidence_refs 或明示缺失"],
        side_effects=["可能触发记忆检索缓存更新（Derived）"],
        failure_impacts=["Context 错误会导致答非所问/写错账本", "预算失控导致延迟与费用上涨"],
        change_impacts=["Capsule 字段变更影响摘要与运行时提示词", "热度策略变更影响召回体感"],
        forbidden_couplings=["引擎直接提交账本写入", "把向量近邻当已确认事实交给运行时当真"],
        mitigation_notes=["Context 可解释来源", "低置信线索降权", "引擎故障时用最近 Capsule"],
    ),
    "rel-agent-runtime-capability-registry-depends_on": contract(
        summary="运行时只能通过能力注册表调用工具；注册表定义 IO 契约、副作用等级与权限，隔离具体 SDK。",
        provides=["工具发现与 schema", "invoke 调用与标准化错误", "高风险预览/确认门禁"],
        requires=["未注册能力必须显式失败", "运行时不得 import 实现方 SDK 做业务写入"],
        assumptions=["工具实现可替换", "副作用等级准确标注"],
        guarantees=["高风险 external 必经 Permission", "错误人类可读"],
        side_effects=["工具自身副作用（读文件、发信等）"],
        failure_impacts=["幻觉成功会破坏信任", "权限漏配会导致误发外发"],
        change_impacts=["工具更名/废弃影响旧 Turn 与提示词"],
        forbidden_couplings=["绕过 Registry 直调服务", "把 SDK 异常原文甩给用户"],
        mitigation_notes=["deprecated 过渡期", "能力清单帮助页", "调用审计日志"],
    ),
    "rel-agent-runtime-state-commit-engine-produces_for": contract(
        summary="运行时产出 Reply + Ledger Operations；只有状态提交引擎能写 Canonical。说了改就必须在 commit 后改成功。",
        provides=[
            "LedgerOperations[]（幂等 op_id）：create_event/update_matter/correct_field/create_reminder/attach_file…",
            "可选 MemoryProposals（非正式）",
            "用户可读 Reply 草稿",
        ],
        requires=["提交引擎原子应用并返回变更回执", "高风险操作先 Permission/确认"],
        assumptions=["op schema 稳定", "一次 Turn 可多操作"],
        guarantees=["commit 成功才允许 Reply 声称已保存", "Correction 必然带旧→新"],
        side_effects=["推进 repository_generation", "触发摘要脏标记、可选建 Durable 任务"],
        failure_impacts=["提交失败但 Reply 说成功 = 假成功（严重）", "半失败需回滚"],
        change_impacts=["op schema 变更影响模型输出与提交引擎"],
        forbidden_couplings=["运行时直写 blackbox 文件", "Reply 与 Ops 不一致仍展示成功", "用聊天文本替代 commit"],
        mitigation_notes=["变更回执组件化", "超时降级文案", "op 幂等与重放安全"],
    ),
    "rel-state-commit-engine-personal-ledger-core-produces_for": contract(
        summary="提交引擎是账本核心唯一写入口：校验、合并、幂等、审计后原子落盘。",
        provides=["事务性写入（Matter/Event/People/引用/生命周期）", "ChangeSet 与 generation 推进"],
        requires=["账本提供稳定实体模型与唯一键", "相似 Matter 合并建议接口"],
        assumptions=["账本本地一致性优先", "Source 指针可解析"],
        guarantees=["无双写", "失败无半套状态", "可回读审计"],
        side_effects=["Derived 需重建/失效"],
        failure_impacts=["账本损坏则产品失忆", "错误合并会串事项"],
        change_impacts=["实体字段变更影响投影与摘要"],
        forbidden_couplings=["投影/Provider 直写账本", "用 SQLite 派生当真源"],
        mitigation_notes=["CAS/generation", "合并可拆分", "备份含 Source"],
    ),
    "rel-state-commit-engine-source-evidence-produces_for": contract(
        summary="提交账本变更时同步登记/关联 Source 与解释；纠正只作废解释，不改原文。",
        provides=["source_ref 挂接", "interpretation 与 correction 轨迹"],
        requires=["Source 不可变", "附件哈希/版本"],
        assumptions=["证据可定位到文件/原话"],
        guarantees=["结论可追溯", "纠正不销毁原件"],
        side_effects=["新增 Source/版本文件"],
        failure_impacts=["断链会导致 AI 胡说无法自证"],
        change_impacts=["证据模型变更影响回答与投影链接"],
        forbidden_couplings=["update_source_text", "摘要覆盖 Source"],
        mitigation_notes=["证据缺失显式失败", "版本目录隔离"],
    ),
    "rel-state-commit-engine-durable-task-runtime-produces_for": contract(
        summary="提交成功后创建/更新/取消持久任务（提醒、延迟、定时）；任务落盘不依赖模型记忆。",
        provides=["schedule/cancel/reschedule 指令（含 matter_ref、due、payload）"],
        requires=["持久任务幂等与重启存活", "到期投递交回交互层"],
        assumptions=["时钟可信", "用户时区明确"],
        guarantees=["commit 与 task 创建同失败域尽量原子（或可续传）", "触发可审计"],
        side_effects=["未来通知"],
        failure_impacts=["假成功会漏提醒", "双建会轰炸"],
        change_impacts=["任务 schema 影响提醒卡片"],
        forbidden_couplings=["只写聊天约定当提醒", "任务创建绕过 commit 审计"],
        mitigation_notes=["op 级幂等", "补送/错过可见"],
    ),
    "rel-state-commit-engine-summary-system-produces_for": contract(
        summary="提交成功后向摘要系统发 Dirty 信号；摘要增量更新 Capsule，禁止提交引擎自己长文总结。",
        provides=["dirty_event：matter_id, change_kind, evidence_refs, patch_digest"],
        requires=["摘要系统增量更新并回报新 capsule_ref"],
        assumptions=["摘要失败不回滚业务写入（可异步补）"],
        guarantees=["最终 Capsule 与账本状态一致", "无变化不上传播"],
        side_effects=["父级 Capsule 可能更新"],
        failure_impacts=["摘要过期会让上下文与表不一致"],
        change_impacts=["dirty 协议变更影响更新延迟与成本"],
        forbidden_couplings=["在 commit 事务内做 LLM 长总结", "摘要反写覆盖账本字段"],
        mitigation_notes=["摘要失败可 requeue", "repair 全量重建"],
    ),
    "rel-durable-task-runtime-interaction-layer-produces_for": contract(
        summary="到期任务由持久运行时产生通知，经交互层送到用户实际入口；运行时不做渠道协议。",
        provides=["NotificationIntent：user_ref, title, body, matter_ref, urgency, collapse_key"],
        requires=["交互层选路/去重/回执", "失败可补送"],
        assumptions=["至少一路可达或进「未送达」列表"],
        guarantees=["collapse_key 防轰炸", "送达状态可查询"],
        side_effects=["设备通知/IM 消息"],
        failure_impacts=["送达失败=用户错过截止", "重复投递=骚扰"],
        change_impacts=["Intent 字段影响卡片与文案"],
        forbidden_couplings=["持久层直连企微 SDK", "无去重的裸发"],
        mitigation_notes=["合并窗口", "错过补办入口"],
    ),
    "rel-projection-layer-state-commit-engine-produces_for": contract(
        summary="用户在表格/Web 的编辑必须变成 Ledger Patch 走提交引擎；投影只读也可展示，但不可成为第二真源。",
        provides=["UserEditOp（cell/row/archive/pin）→ 标准化 LedgerOperations"],
        requires=["提交回执与冲突合并", "AI 更新后投影刷新"],
        assumptions=["字段映射版本化"],
        guarantees=["编辑有「已保存」反馈才落 UI 终值", "冲突可见不静默覆盖"],
        side_effects=["generation 变化触发投影同步"],
        failure_impacts=["改表不生效=不信任", "双真相=事故"],
        change_impacts=["列模型变更需迁移视图"],
        forbidden_couplings=["投影库直写 business 表", "用 WPS 自动化覆盖 Canonical"],
        mitigation_notes=["默认「我的事项」视图", "人机冲突合并 UI"],
    ),
    "rel-memory-fabric-state-commit-engine-produces_for": contract(
        summary="记忆整理/去重/降温只产生 Proposal，经用户或策略确认后才能由提交引擎改真源。",
        provides=["ConsolidationProposal / MergeSuggestion / CoolDownHint"],
        requires=["提交引擎的 proposal 通道（默认不自动改史）"],
        assumptions=["Provider 失败不影响真源"],
        guarantees=["无静默改写", "建议可忽略"],
        side_effects=["可能被采纳后产生 commit"],
        failure_impacts=["自动合并会毁事项结构"],
        change_impacts=["提案 schema 影响审核 UI"],
        forbidden_couplings=["Provider 直写 Matter", "后台改 Source"],
        mitigation_notes=["默认 proposal-only", "审计来源=provider"],
    ),
    "rel-agent-runtime-source-evidence-depends_on": contract(
        summary="运行时在需要自证时下钻证据；读 Source 不可变，纠正只影响解释层。",
        provides=["按 evidence_ref 打开原文/页码", "缺证据检测"],
        requires=["运行时对无依据主张明说「没找到」"],
        assumptions=["evidence_ref 可解析"],
        guarantees=["可点回原文"],
        side_effects=["无写入"],
        failure_impacts=["坏链导致胡说"],
        change_impacts=["引用格式变更影响回答组件"],
        forbidden_couplings=["读证据后改写 Source", "编造页码"],
        mitigation_notes=["链接巡检", "缺失即拒答"],
    ),
}


def ensure_relation(source, target, relation_type):
    # create; ignore ALREADY_EXISTS style errors
    def make(g):
        return {
            "source": source,
            "target": target,
            "relation_type": relation_type,
            "project_id": PID,
            "expected_generation": g,
            **ACTOR,
        }
    s, b = write("POST", "/api/relations", make)
    if s < 300:
        rid = (b or {}).get("id") or (b or {}).get("relation", {}).get("id")
        print("create_rel", source, "->", target, s, rid)
        return rid
    # try find existing
    g = call("GET", "/api/graph", None)[1]
    for r in g.get("relations", []):
        if r["source"] == source and r["target"] == target:
            print("exists_rel", source, "->", target, r["id"])
            return r["id"]
    print("create_rel_fail", source, target, s, b)
    return None


def save_contract(relation_id, contract_obj):
    # base_revision 0 for first save
    def make(g):
        return {
            "relation_id": relation_id,
            "base_revision": 0,
            "contract": contract_obj,
            "project_id": PID,
            "expected_generation": g,
            **ACTOR,
        }
    s, b = write("PUT", f"/api/relations/{relation_id}/boundary-contract", make)
    if s < 300:
        print("contract", relation_id, s)
        return True
    # maybe already has revision 1
    st, existing = call("GET", f"/api/relations/{relation_id}/boundary-contract", None)
    rev = 0
    if st < 300 and isinstance(existing, dict):
        rev = int(existing.get("revision") or existing.get("current_revision") or 0)

    def make2(g):
        return {
            "relation_id": relation_id,
            "base_revision": rev,
            "contract": contract_obj,
            "project_id": PID,
            "expected_generation": g,
            **ACTOR,
        }
    s, b = write("PUT", f"/api/relations/{relation_id}/boundary-contract", make2)
    print("contract_retry", relation_id, s, rev)
    return s < 300


def main():
    print("start", status_gen())
    created = []
    for source, target, rtype in NEW_RELATIONS:
        rid = ensure_relation(source, target, rtype)
        if rid:
            created.append(rid)

    ok = 0
    for rid, c in CONTRACTS.items():
        if save_contract(rid, c):
            ok += 1
    print(f"contracts_ok={ok}/{len(CONTRACTS)}")
    g = call("GET", "/api/graph", None)[1]
    print("relations_now", len(g.get("relations", [])))
    print("end", status_gen())


if __name__ == "__main__":
    main()
