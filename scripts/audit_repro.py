# -*- coding: utf-8 -*-
"""Minimal deterministic reproductions for audit findings F-001..F-017."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\LIB\mimo\shadowV2\src")
from shiguang.storage import open_store
from shiguang.source_evidence import SourceEvidenceService
from shiguang.state_commit import StateCommitEngine
from shiguang.types import LedgerOp, OpKind


def main():
    tmp = tempfile.mkdtemp()
    store = open_store(Path(tmp) / "t.sqlite")
    src = SourceEvidenceService(store)
    eng = StateCommitEngine(store, src)

    print("=== F-001 multi-op partial failure ===")
    ops = [
        LedgerOp(op_id="o1", kind=OpKind.CREATE_MATTER.value, payload={"title": "m_a", "matter_id": "matter_a"}),
        LedgerOp(op_id="o2", kind=OpKind.UPDATE_MATTER.value, payload={"matter_id": "matter_missing", "fields": {"x": 1}}),
    ]
    try:
        eng.commit_ops(ops)
        print("  no error")
    except Exception as e:
        print("  error:", type(e).__name__, e)
    print("  matters:", store.query("SELECT matter_id FROM matters"))
    print("  op_log:", store.query("SELECT op_id FROM op_log"))

    print("=== F-002 correction field SQL ===")
    store.execute(
        "INSERT INTO reminders(reminder_id,matter_id,title,body,due_at,status,fire_count,last_fired_at,collapse_key,next_action,created_at,updated_at)"
        " VALUES('r1','matter_a','T','B',100,'SCHEDULED',0,NULL,'k','n',1,1)"
    )
    store.commit()
    op = LedgerOp(
        op_id="o3",
        kind=OpKind.CORRECT_FIELD.value,
        payload={"target_kind": "reminder", "target_id": "r1", "field": "title='POISON', status", "new_value": "X"},
    )
    try:
        r = eng.commit_ops([op])
        print("  status", r.status, r.summary)
    except Exception as e:
        print("  error:", type(e).__name__, e)
    print("  reminder:", store.query_one("SELECT title,status FROM reminders WHERE reminder_id='r1'"))

    print("=== F-011 correction interp_id ===")
    store.execute(
        "INSERT INTO interpretations(interp_id,source_id,matter_id,kind,fields,status,created_at)"
        " VALUES('i1','s1','matter_a','reminder','{}','ACTIVE',1)"
    )
    store.commit()
    op = LedgerOp(
        op_id="o4",
        kind=OpKind.CORRECT_FIELD.value,
        payload={
            "target_kind": "matter",
            "target_id": "matter_a",
            "field": "due_label",
            "new_value": "周四",
            # no interp_id
        },
    )
    try:
        eng.commit_ops([op])
    except Exception as e:
        print("  error", e)
    print("  interp:", store.query("SELECT interp_id,status FROM interpretations"))

    print("=== F-003 duplicate reminder same text ===")
    # simulate two CREATE_REMINDER same matter/title/due via commit
    for i, oid in enumerate(["r_a", "r_b"]):
        eng.commit_ops(
            [
                LedgerOp(
                    op_id=oid,
                    kind=OpKind.CREATE_REMINDER.value,
                    payload={"matter_id": "matter_a", "title": "联系李经理", "due_at": 999, "body": "same"},
                )
            ]
        )
    print("  reminders:", store.query("SELECT reminder_id,title,collapse_key FROM reminders"))

    print("=== F-006 directive and/or ===")
    # hour=10 notification -> should allow; hour=7 -> defer for work text
    from shiguang.durable_task import DirectivePolicyEvaluator, FakeClock

    clock = FakeClock(0)
    # set hour via now: hour = (now//3600000)%24
    for hour in (7, 10, 23):
        clock.set(hour * 3600000)
        ev = DirectivePolicyEvaluator(store, clock)
        d1 = ev.evaluate_delivery(kind="reply", target="", text="合同")
        d2 = ev.evaluate_delivery(kind="notification", target="", text="合同")
        d3 = ev.evaluate_delivery(kind="notification", target="", text="哈哈")
        print(f"  hour={hour} reply={d1.action} notif_work={d2.action} notif_fun={d3.action}")

    print("=== F-017 mark_fired before policy ===")
    # inspect source order - just print line refs later

    print("=== F-013 dirty multi matter ===")
    store.execute("INSERT OR IGNORE INTO matters(matter_id,title,status,priority,due_at,owner_person_id,parent_matter_id,next_action,fields,revision,created_at,updated_at) VALUES('m1','a','OPEN',NULL,NULL,NULL,NULL,'','{}',1,1,1)")
    store.execute("INSERT OR IGNORE INTO matters(matter_id,title,status,priority,due_at,owner_person_id,parent_matter_id,next_action,fields,revision,created_at,updated_at) VALUES('m2','b','OPEN',NULL,NULL,NULL,NULL,'','{}',1,1,1)")
    store.commit()
    eng.commit_ops(
        [
            LedgerOp(op_id="d1", kind=OpKind.APPEND_EVENT.value, payload={"summary": "e1", "matter_id": "m1"}),
            LedgerOp(op_id="d2", kind=OpKind.APPEND_EVENT.value, payload={"summary": "e2", "matter_id": "m2"}),
        ]
    )
    print("  dirty:", store.query("SELECT node_id FROM dirty_nodes"))

    print("=== F-004 P1 bypass ===")
    from shiguang.p1_slices import KnowledgeLedger, MatterTree

    k = KnowledgeLedger(store)
    kid = k.upsert(topic="t", content="c")
    print("  knowledge direct:", kid, store.query("SELECT knowledge_id FROM knowledge"))
    print("  op_log knowledge:", store.query("SELECT op_id,kind FROM op_log WHERE kind LIKE '%knowledge%' OR kind LIKE '%parent%'"))


if __name__ == "__main__":
    main()
