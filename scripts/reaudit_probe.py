# -*- coding: utf-8 -*-
"""Re-audit verification probes — real defects vs over-engineering."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\LIB\mimo\shadowV2\src")
from shiguang.storage import open_store
from shiguang.source_evidence import SourceEvidenceService
from shiguang.state_commit import StateCommitEngine
from shiguang.types import LedgerOp, OpKind
from shiguang.durable_task import FakeClock, DirectivePolicyEvaluator, DurableTaskRuntime
from shiguang.runtime import ShiGuangApp

ROOT = Path(r"D:\LIB\mimo\shadowV2")


def section(title):
    print("\n===" + title + "===")


def main():
    tmp = tempfile.mkdtemp()
    store = open_store(Path(tmp) / "t.sqlite")
    src = SourceEvidenceService(store)
    eng = StateCommitEngine(store, src)

    section("N-003 nested txn")
    print("depth before", store._txn_depth)
    with store.transaction():
        print("outer depth", store._txn_depth)
        with store.transaction():
            print("inner depth", store._txn_depth)
        print("after inner", store._txn_depth)
    print("after outer", store._txn_depth)
    # who actually nests? count call sites later

    section("ValidationReject receipt")
    try:
        eng.commit_ops(
            [LedgerOp(op_id="x", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": "m"})]
        )
    except Exception as e:
        print(type(e).__name__, e)
    print("receipts", store.query("SELECT status FROM change_receipts"))

    section("F-003 COMPLETED reuse / collapse_key")
    eng.commit_ops(
        [LedgerOp(op_id="c1", kind=OpKind.CREATE_MATTER.value, payload={"title": "T", "matter_id": "ma", "force_new": True})]
    )
    eng.commit_ops(
        [LedgerOp(op_id="r1", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": "ma", "title": "X", "due_at": 100})]
    )
    rid = store.query_one("SELECT reminder_id FROM reminders WHERE title='X'")["reminder_id"]
    eng.commit_ops([LedgerOp(op_id="done", kind=OpKind.COMPLETE_REMINDER.value, payload={"reminder_id": rid})])
    print("after complete", store.query_one("SELECT status FROM reminders WHERE reminder_id=?", (rid,)))
    eng.commit_ops(
        [LedgerOp(op_id="r2", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": "ma", "title": "X", "due_at": 200})]
    )
    print("reminders X", store.query("SELECT reminder_id,due_at,status FROM reminders WHERE title='X'"))
    # same title different due_at should be 2 if identity correct; currently maybe 1 via collapse_key

    section("N-002 FIRED then deliver fail")
    tmp2 = tempfile.mkdtemp()
    app = ShiGuangApp.open(ROOT, Path(tmp2) / "n2.sqlite", clock=FakeClock(1_758_806_400_000))
    app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
    rem = app.store.query_one("SELECT * FROM reminders")
    app.clock.set(rem["due_at"] + 1000)
    app.delivery_adapter.fail_next = True
    results = app.run_due_tasks()
    print("fail-delivery results", results)
    print("reminder after fail", app.store.query_one("SELECT status,fire_count FROM reminders"))
    # next run must recover
    results2 = app.run_due_tasks()
    print("second run", results2)
    print("reminder after second", app.store.query_one("SELECT status,fire_count FROM reminders"))
    app.close()

    section("N-001 crash window message_inbox")
    # simulate: ops committed but inbox not written (manual)
    tmp3 = tempfile.mkdtemp()
    app = ShiGuangApp.open(ROOT, Path(tmp3) / "n1.sqlite", clock=FakeClock(1_758_806_400_000))
    r1 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
    print("inbox rows", app.store.query("SELECT message_id,status FROM message_inbox"))
    print("events", app.store.query("SELECT COUNT(*) c FROM events"))
    # same clock re-ingest = replay
    r2 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
    print("replay", r2.get("replay"), "events", app.store.query("SELECT COUNT(*) c FROM events"))
    # +61s same text = NEW message_id
    app.clock.advance_ms(61_000)
    r3 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
    print("after 61s replay?", r3.get("replay"), "intent", r3.get("intent"), "events", app.store.query("SELECT COUNT(*) c FROM events"))
    app.close()

    section("who nests transactions")
    # grep-like: we already know only StateCommitEngine and tests use transaction()
    print("see code: only StateCommitEngine.commit_ops opens business txn")


if __name__ == "__main__":
    main()
