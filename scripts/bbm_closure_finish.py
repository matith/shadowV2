# -*- coding: utf-8 -*-
"""Finish remaining sub-blackboxes, evidence, summary lag, missing edges."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4319"
PID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}
TMPL = "general-module-v1"


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


def spec(purpose, summary):
    return {
        "purpose": purpose,
        "acceptance_experience": {
            "kind": "expected_system_behavior",
            "narrative": f"作为独立小黑盒：{summary}",
            "expected_outcomes": ["接口语义稳定", "可独立测试/替换", "不越权写其他真源"],
            "failure_signals": ["职责越界", "接口漂移", "静默吞错"],
        },
        "constraints": [
            "可保持 PLANNED 不施工",
            "遵守父级 Boundary Contract",
            "不拥有父级以外的 Canonical 真源",
        ],
        "custom": {"planned_not_implemented": True},
    }


def mod(mid, name, summary, purpose, group, x=40, y=40):
    return {
        "id": mid,
        "name": name,
        "summary": summary,
        "x": x,
        "y": y,
        "visual_group_id": group,
        "spec": spec(purpose, summary),
        "lifecycle": "PLANNED",
    }


# Remaining children not yet in graph
REMAINING = [
    # personal-ledger-core rest
    mod("product-ledger", "产品业务账本", "产品/政策/资费/参数资料语义目录", "长期业务资料的语义与版本目录；bytes 归 Source。", "group-core", 40, 40),
    mod("file-ledger", "资料目录账本", "资料是什么、关联谁/何事", "File 语义与关联（类型/产品/Matter）；原始 bytes 与哈希归 Source & Evidence。", "group-core", 260, 40),
    mod("directive-ledger", "指令账本", "用户长期规则与执行策略源", "Directive 存储；供 Policy Evaluator 与 Context 消费。", "group-core", 480, 40),
    mod("archive-ledger", "归档账本", "极小召回摘要与指针", "Archive Capsule + pointer；归档≠删除。", "group-core", 700, 40),
    # source-evidence
    mod("raw-source-store", "原文存储", "不可变原始内容", "hash+bytes/文本；只读。", "group-evidence", 40, 40),
    mod("attachment-store", "附件存储", "文件对象与预览", "附件落盘、预览、失败可见。", "group-evidence", 260, 40),
    mod("provenance-chain", "溯源链", "谁/何时/从哪来", "provenance 记录与证据指针解析。", "group-evidence", 480, 40),
    mod("source-versioning", "源版本", "多版本与过期", "版本目录；禁止同名覆盖。", "group-evidence", 700, 40),
    mod("effect-receipt-store", "副作用收据存储", "外部动作 Effect Receipt", "effect_id/capability/target/result/external_ref/evidence_ref。", "group-evidence", 920, 40),
    # state-commit
    mod("op-validator", "操作校验", "Ledger Op 校验与幂等", "schema/权限/op_id 去重。", "group-commit", 40, 40),
    mod("patch-committer", "补丁提交", "原子落账", "CAS 提交与 ChangeSet。", "group-commit", 260, 40),
    mod("correction-applier", "纠正执行", "失效旧解释并更新当前态", "Correction 轨迹；Source 不动。", "group-commit", 480, 40),
    mod("conflict-resolver", "冲突处理", "重复 Matter 与并发字段", "合并建议/拆分；可解释。", "group-commit", 700, 40),
    mod("change-receipt", "变更回执", "成功/失败用户回执", "仅 commit 成功才称成功。", "group-commit", 920, 40),
    # summary
    mod("capsule-store", "胶囊存储", "Context Capsule 读写", "固定结构 Goal/Current/Open/Files/Evidence。", "group-summary", 40, 40),
    mod("incremental-reducer", "增量摘要器", "old+patch→new", "禁止默认全量重写。", "group-summary", 260, 40),
    mod("tree-propagator", "树传播器", "子→父脏传播", "无变化即停。", "group-summary", 480, 40),
    mod("dirty-tracker", "脏跟踪", "待更新节点标记", "与 revision 对齐。", "group-summary", 700, 40),
    # memory
    mod("hot-warm-cold-tier", "热度分层", "HOT/WARM/COLD/RAW", "多因子优先级。", "group-memory", 40, 40),
    mod("semantic-index", "语义索引", "语义/向量召回", "Derived 可重建。", "group-memory", 260, 40),
    mod("relation-index", "关系索引", "实体关系召回", "Derived 可重建。", "group-memory", 480, 40),
    mod("memory-provider-adapter", "记忆 Provider 适配", "Mem0/Graphiti/本地", "可拔插；不写真源。", "group-memory", 700, 40),
    mod("consolidation-proposer", "整理提案器", "去重/降温/合并建议", "仅 Proposal，经提交引擎。", "group-memory", 920, 40),
    # durable
    mod("reminder-scheduler", "提醒调度", "到期提醒", "持久化+幂等。", "group-durable", 40, 40),
    mod("delayed-scheduled-runner", "延迟定时执行", "Delay/Schedule", "重启存活。", "group-durable", 260, 40),
    mod("task-resume", "任务恢复", "中断恢复与补送", "Resume/错过补办。", "group-durable", 480, 40),
    mod("task-action-bridge", "任务动作桥", "complete/snooze→Ledger Op", "经 State/Commit 回写 Matter。", "group-durable", 700, 40),
    # capability
    mod("tool-contract-registry", "工具契约注册", "name/io/side_effects", "未注册显式失败。", "group-capability", 40, 40),
    mod("permission-gate", "权限门禁", "高副作用确认", "external/high-risk 必确认。", "group-capability", 260, 40),
    mod("effect-receipt-emitter", "副作用收据发生器", "调用后写 Receipt", "成功/失败/external_ref。", "group-capability", 480, 40),
    mod("external-service-adapter", "外部服务适配", "MCP/HTTP/本地工具", "实现可替换。", "group-capability", 700, 40),
    # projection
    mod("table-projection", "表格投影", "多维表/Web 表", "默认「我的事项」视图。", "group-projection", 40, 40),
    mod("web-projection", "Web 投影", "浏览器 UI", "可替换界面。", "group-projection", 260, 40),
    mod("edit-to-patch-adapter", "编辑回写适配", "UserEditOp→Ledger Op", "回执后 UI 终值。", "group-projection", 480, 40),
    # ops
    mod("diagnostics", "诊断", "身份/缓存/渠道健康", "脱敏自检。", "group-ops", 40, 40),
    mod("tracing", "链路追踪", "消息→提交→投递", "op_id 可定位。", "group-ops", 260, 40),
    mod("backup-restore", "备份恢复", "Canonical+Source", "恢复预检。", "group-ops", 480, 40),
    mod("migration-runner", "迁移执行", "schema/数据迁移", "幂等可审计。", "group-ops", 700, 40),
    mod("provider-config", "模型 Provider 配置", "换模与连通测试", "不迁业务数据。", "group-ops", 920, 40),
]

PARENT = {
    "group-core": "personal-ledger-core",
    "group-evidence": "source-evidence",
    "group-commit": "state-commit-engine",
    "group-summary": "summary-system",
    "group-memory": "memory-fabric",
    "group-durable": "durable-task-runtime",
    "group-capability": "capability-registry",
    "group-projection": "projection-layer",
    "group-ops": "operations",
    "group-interaction": "interaction-layer",
    "group-runtime": "agent-runtime",
    "group-context": "context-engine",
}


def main():
    print("start", gen())
    # import remaining as one batch
    s, b = write(
        "POST",
        "/api/map-import",
        lambda g: {
            "project_id": PID,
            "expected_generation": g,
            "default_template_version_id": TMPL,
            "modules": REMAINING,
            "relations": [],
            **ACTOR,
        },
    )
    print("batch_import", s)
    if s >= 300:
        print(json.dumps(b, ensure_ascii=False)[:400])
        # fallback one by one
        for m in REMAINING:
            s2, _ = write(
                "POST",
                "/api/map-import",
                lambda g, m=m: {
                    "project_id": PID,
                    "expected_generation": g,
                    "default_template_version_id": TMPL,
                    "modules": [m],
                    "relations": [],
                    **ACTOR,
                },
            )
            print("one", m["id"], s2)

    # contains relations for all known children
    g = call("GET", "/api/graph", None)[1]
    ids = {n["id"] for n in g["nodes"]}
    for m in REMAINING:
        parent = PARENT[m["visual_group_id"]]
        if parent not in ids or m["id"] not in ids:
            print("skip rel", m["id"])
            continue
        s, b = write(
            "POST",
            "/api/relations",
            lambda g, p=parent, c=m["id"]: {
                "project_id": PID,
                "expected_generation": g,
                "source": p,
                "target": c,
                "relation_type": "contains",
                **ACTOR,
            },
        )
        if s >= 300:
            msg = str(b)[:120]
            if "exist" not in msg.lower() and "already" not in msg.lower():
                print("rel_err", parent, m["id"], s, msg)

    # also ensure earlier children have contains
    g = call("GET", "/api/graph", None)[1]
    existing = {(r["source"], r["target"]) for r in g["relations"]}
    child_parent = {
        "inbound-message-gateway": "interaction-layer",
        "message-normalizer": "interaction-layer",
        "delivery-router": "interaction-layer",
        "channel-identity-mapping": "interaction-layer",
        "model-adapter": "agent-runtime",
        "turn-orchestrator": "agent-runtime",
        "tool-invoker": "agent-runtime",
        "ledger-ops-proposer": "agent-runtime",
        "working-context-compiler": "context-engine",
        "ledger-router": "context-engine",
        "memory-retriever": "context-engine",
        "context-budget-policy": "context-engine",
        "directive-policy-evaluator": "context-engine",
        "matter-ledger": "personal-ledger-core",
        "event-ledger": "personal-ledger-core",
        "people-ledger": "personal-ledger-core",
        "knowledge-ledger": "personal-ledger-core",
    }
    for c, p in child_parent.items():
        if (p, c) not in existing and c in ids and p in ids:
            s, _ = write(
                "POST",
                "/api/relations",
                lambda g, p=p, c=c: {
                    "project_id": PID,
                    "expected_generation": g,
                    "source": p,
                    "target": c,
                    "relation_type": "contains",
                    **ACTOR,
                },
            )
            print("contains", p, c, s)

    # evidence + binding docs
    for eid, path, note in [
        ("ev-docs-identity", "docs/IDENTITY.md", "项目身份交叉核对文档"),
        ("ev-docs-acceptance", "docs/scenarios/acceptance.md", "验收场景 A-G / X"),
        ("ev-docs-interaction", "docs/interaction-audit.md", "交互审计轨迹"),
    ]:
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
        print("evidence", eid, s, "" if s < 300 else b)

    # refresh summaries so basis catches current
    for mid, text in [
        ("agent-runtime", "可替换模型发动机：编排 Turn、调用工具契约、产出回复与账本操作提案；不直写真源。子系统：模型适配/Turn 编排/工具调用/操作提案。"),
        ("personal-ledger-core", "唯一业务真源：事项当前状态+事件历史+人物/知识/产品/资料目录/指令/归档；Source 与解释分离。含 8 个账本子黑盒。"),
        ("source-evidence", "原文/附件/版本/溯源/副作用收据；纠正不毁原件；个人状态与文档事实可追溯。"),
        ("state-commit-engine", "唯一写入闸门：校验/补丁/纠正/冲突/回执；接受 Durable 任务动作回写提案。"),
        ("durable-task-runtime", "提醒/延迟/定时/恢复；经交互投递；完成改期经任务动作桥回写提交引擎。"),
        ("capability-registry", "工具契约与权限；高副作用写 Effect Receipt；未注册显式失败。"),
    ]:
        s, _ = write(
            "PUT",
            f"/api/modules/{mid}/summary",
            lambda g, t=text: {"project_id": PID, "expected_generation": g, "text": t, **ACTOR},
        )
        print("summary", mid, s)

    # parent summary for others too
    for mid, text in [
        ("interaction-layer", "消息接入/规范化/投递/跨渠道身份映射管道；不持有事项状态。"),
        ("context-engine", "Working Context 编译、账本路由、检索预算、Directive 策略评估。"),
        ("summary-system", "Capsule 增量与树传播；与 revision 对齐。"),
        ("memory-fabric", "热度分层与可插拔 Provider；只提案不写真源。"),
        ("projection-layer", "表格/Web 投影与编辑回写适配。"),
        ("operations", "诊断/追踪/备份迁移/Provider 配置。"),
    ]:
        s, _ = write(
            "PUT",
            f"/api/modules/{mid}/summary",
            lambda g, t=text: {"project_id": PID, "expected_generation": g, "text": t, **ACTOR},
        )
        print("summary", mid, s)

    g = call("GET", "/api/graph", None)[1]
    print("final nodes", len(g["nodes"]), "rels", len(g["relations"]), "gen", gen())
    pl = call("GET", "/api/planning/ledger", None)[1]
    print(
        "planning plans",
        len(pl.get("plan_versions") or []),
        "dec",
        len(pl.get("decisions") or []),
        "ac",
        len((pl.get("acceptance") or {}).get("criteria") or []),
        "ev",
        len(pl.get("evidence") or []),
    )


if __name__ == "__main__":
    main()
