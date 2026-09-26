# -*- coding: utf-8 -*-
"""Audit remediation tests: failure paths, write gate, idempotency, directive."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import DirectivePolicyEvaluator, FakeClock  # noqa: E402
from shiguang.ledgers import MatterLedger  # noqa: E402
from shiguang.p1_slices import KnowledgeLedger, P1WriteBridge  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.state_commit import CORRECTABLE_FIELDS  # noqa: E402
from shiguang.storage import open_store  # noqa: E402
from shiguang.source_evidence import SourceEvidenceService  # noqa: E402
from shiguang.state_commit import StateCommitEngine  # noqa: E402
from shiguang.types import CommitError, LedgerOp, OpKind, ValidationReject  # noqa: E402


class TestTransactionAtomicity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = open_store(Path(self._tmp.name) / "t.sqlite")
        self.addCleanup(self.store.close)
        self.src = SourceEvidenceService(self.store)
        self.eng = StateCommitEngine(self.store, self.src)

    def test_F001_multi_op_rollback_leaves_zero_residue(self):
        ops = [
            LedgerOp(op_id="o1", kind=OpKind.CREATE_MATTER.value, payload={"title": "m_a", "matter_id": "matter_a"}),
            LedgerOp(op_id="o2", kind=OpKind.UPDATE_MATTER.value, payload={"matter_id": "matter_missing", "fields": {"x": 1}}),
        ]
        with self.assertRaises(CommitError):
            self.eng.commit_ops(ops)
        self.assertEqual(self.store.query("SELECT COUNT(*) c FROM matters")[0]["c"], 0)
        self.assertEqual(self.store.query("SELECT COUNT(*) c FROM op_log")[0]["c"], 0)
        self.assertEqual(self.store.query("SELECT COUNT(*) c FROM events")[0]["c"], 0)
        # REJECTED receipt exists
        rejected = self.store.query("SELECT * FROM change_receipts WHERE status='REJECTED'")
        self.assertGreaterEqual(len(rejected), 1)

    def test_F001_retry_same_op_ids_after_rollback(self):
        ops = [
            LedgerOp(op_id="retry1", kind=OpKind.CREATE_MATTER.value, payload={"title": "m_b", "matter_id": "matter_b"}),
            LedgerOp(op_id="retry2", kind=OpKind.UPDATE_MATTER.value, payload={"matter_id": "nope", "fields": {"x": 1}}),
        ]
        with self.assertRaises(CommitError):
            self.eng.commit_ops(ops)
        # fix second op and retry same first op_id — must succeed without UNIQUE crash
        ops2 = [
            LedgerOp(op_id="retry1", kind=OpKind.CREATE_MATTER.value, payload={"title": "m_b", "matter_id": "matter_b"}),
            LedgerOp(op_id="retry2b", kind=OpKind.APPEND_EVENT.value, payload={"summary": "ok", "matter_id": "matter_b"}),
        ]
        r = self.eng.commit_ops(ops2)
        self.assertEqual(r.status, "COMMITTED")
        self.assertEqual(self.store.query("SELECT COUNT(*) c FROM matters")[0]["c"], 1)

    def test_ledger_direct_write_rejected(self):
        m = MatterLedger(self.store)
        with self.assertRaises(RuntimeError):
            m.create(title="bypass")


class TestCorrectionSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = open_store(Path(self._tmp.name) / "t.sqlite")
        self.addCleanup(self.store.close)
        self.src = SourceEvidenceService(self.store)
        self.eng = StateCommitEngine(self.store, self.src)
        self.eng.commit_ops(
            [LedgerOp(op_id="m1", kind=OpKind.CREATE_MATTER.value, payload={"title": "T", "matter_id": "matter_a"})]
        )
        self.store.execute(
            "INSERT INTO reminders(reminder_id,matter_id,title,body,due_at,status,fire_count,last_fired_at,collapse_key,next_action,created_at,updated_at)"
            " VALUES('r1','matter_a','T','B',100,'SCHEDULED',0,NULL,'k','n',1,1)"
        )
        self.store.commit()

    def test_F002_illegal_field_rejected(self):
        op = LedgerOp(
            op_id="c1",
            kind=OpKind.CORRECT_FIELD.value,
            payload={"target_kind": "reminder", "target_id": "r1", "field": "title='POISON', status", "new_value": "X"},
        )
        with self.assertRaises(ValidationReject):
            self.eng.commit_ops([op])
        row = self.store.query_one("SELECT title,status FROM reminders WHERE reminder_id='r1'")
        self.assertEqual(row["title"], "T")
        self.assertEqual(row["status"], "SCHEDULED")

    def test_F002_wrong_target_kind(self):
        op = LedgerOp(
            op_id="c2",
            kind=OpKind.CORRECT_FIELD.value,
            payload={"target_kind": "nonsense", "target_id": "r1", "field": "title", "new_value": "X"},
        )
        with self.assertRaises(ValidationReject):
            self.eng.commit_ops([op])

    def test_F002_legal_field_whitelist(self):
        self.assertIn("due_label", CORRECTABLE_FIELDS["matter"])
        self.assertIn("title", CORRECTABLE_FIELDS["reminder"])
        self.assertNotIn("matter_id", CORRECTABLE_FIELDS["matter"])

    def test_F011_correction_invalidates_interps(self):
        self.store.execute(
            "INSERT INTO interpretations(interp_id,source_id,matter_id,kind,fields,status,created_at)"
            " VALUES('i1','s1','matter_a','reminder','{}','ACTIVE',1)"
        )
        self.store.commit()
        op = LedgerOp(
            op_id="c3",
            kind=OpKind.CORRECT_FIELD.value,
            payload={"target_kind": "matter", "target_id": "matter_a", "field": "due_label", "new_value": "周四"},
        )
        self.eng.commit_ops([op])
        rows = self.store.query("SELECT status FROM interpretations WHERE interp_id='i1'")
        self.assertEqual(rows[0]["status"], "INVALIDATED")


class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "p0.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(self.app.close)

    def test_F005_same_message_replay(self):
        r1 = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertFalse(r1["replay"])
        # same clock + same text → same message_id
        r2 = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertTrue(r2["replay"])
        self.assertEqual(r2["receipt"].status, "DUPLICATE")
        self.assertEqual(self.app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"], 1)

    def test_F003_duplicate_reminder_same_text(self):
        self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        # different message (different text) but same reminder identity via ops
        self.app.clock.advance_hours(1)
        self.app.ingest_text("补充一下，是周三之前要确认。")
        rems = self.app.store.query("SELECT * FROM reminders")
        # at most one non-cancelled reminder per identity; allow deadline reminder + initial
        titles = [r["title"] for r in rems]
        self.assertLessEqual(len(titles), 2)
        # create identical reminder op twice with different op_id → reuse
        ops1 = [LedgerOp(op_id="ra", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": rems[0]["matter_id"], "title": "X", "due_at": 12345})]
        ops2 = [LedgerOp(op_id="rb", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": rems[0]["matter_id"], "title": "X", "due_at": 12345})]
        self.app.commit.commit_ops(ops1)
        self.app.commit.commit_ops(ops2)
        n = self.app.store.query("SELECT COUNT(*) c FROM reminders WHERE title='X'")[0]["c"]
        self.assertEqual(n, 1)

    def test_F003_completed_not_reused_new_due(self):
        """COMPLETED reminder must not swallow a new commitment with same title."""
        mid = "matter_x"
        self.app.commit.commit_ops(
            [LedgerOp(op_id="cm", kind=OpKind.CREATE_MATTER.value, payload={"title": "T", "matter_id": mid, "force_new": True})]
        )
        self.app.commit.commit_ops(
            [LedgerOp(op_id="r1", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": mid, "title": "X", "due_at": 100})]
        )
        rid = self.app.store.query_one("SELECT reminder_id FROM reminders WHERE title='X'")["reminder_id"]
        self.app.commit.commit_ops(
            [LedgerOp(op_id="done", kind=OpKind.COMPLETE_REMINDER.value, payload={"reminder_id": rid})]
        )
        self.app.commit.commit_ops(
            [LedgerOp(op_id="r2", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": mid, "title": "X", "due_at": 200})]
        )
        rows = self.app.store.query("SELECT due_at,status FROM reminders WHERE title='X' ORDER BY due_at")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "COMPLETED")
        self.assertEqual(rows[1]["due_at"], 200)
        self.assertEqual(rows[1]["status"], "SCHEDULED")

    def test_same_op_replay(self):
        op = LedgerOp(op_id="fixed", kind=OpKind.CREATE_MATTER.value, payload={"title": "A", "matter_id": "ma"})
        r1 = self.app.commit.commit_ops([op])
        r2 = self.app.commit.commit_ops([op])
        self.assertEqual(r1.status, "COMMITTED")
        self.assertEqual(r2.status, "DUPLICATE")


class TestDirectiveAndFire(unittest.TestCase):
    def test_F006_parentheses(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = open_store(Path(tmp.name) / "pol.sqlite")
        self.addCleanup(store.close)
        clock = FakeClock(0)
        ev = DirectivePolicyEvaluator(store, clock)
        # hour 7: reply must NOT be deferred
        clock.set(7 * 3600000)
        self.assertEqual(ev.evaluate_delivery(kind="reply", target="", text="合同").action, "allow")
        self.assertEqual(ev.evaluate_delivery(kind="notification", target="", text="合同").action, "defer")
        self.assertEqual(ev.evaluate_delivery(kind="notification", target="", text="哈哈").action, "allow")
        clock.set(23 * 3600000)
        self.assertEqual(ev.evaluate_delivery(kind="reply", target="", text="合同").action, "allow")
        self.assertEqual(ev.evaluate_delivery(kind="notification", target="", text="合同").action, "defer")
        clock.set(10 * 3600000)
        self.assertEqual(ev.evaluate_delivery(kind="notification", target="", text="合同").action, "allow")

    def test_F017_policy_before_fire_defer_no_fire_count(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = ShiGuangApp.open(ROOT, Path(tmp.name) / "d.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        rem = app.store.query_one("SELECT * FROM reminders")
        # set due at night hour 23
        night = (app.clock.now() // 86400000) * 86400000 + 23 * 3600000
        app.store.execute("UPDATE reminders SET due_at=?, status='SCHEDULED' WHERE reminder_id=?", (night, rem["reminder_id"]))
        app.store.commit()
        app.clock.set(night + 1000)
        results = app.run_due_tasks()
        self.assertTrue(any(r.get("status") == "DEFERRED" for r in results))
        row = app.store.query_one("SELECT status,fire_count FROM reminders WHERE reminder_id=?", (rem["reminder_id"],))
        self.assertEqual(row["fire_count"], 0)
        self.assertNotEqual(row["status"], "FIRED")

    def test_restart_then_fire_once(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "r.sqlite"
        clock = FakeClock(1_758_806_400_000)
        app = ShiGuangApp.open(ROOT, db, clock=clock)
        app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        rem = app.store.query_one("SELECT * FROM reminders")
        due = rem["due_at"]
        app.close()

        clock2 = FakeClock(due + 1000)
        app2 = ShiGuangApp.open(ROOT, db, clock=clock2)
        self.addCleanup(app2.close)
        r1 = app2.run_due_tasks()
        self.assertEqual(len([x for x in r1 if x.get("status") == "FIRED"]), 1)
        r2 = app2.run_due_tasks()
        self.assertEqual(len([x for x in r2 if x.get("status") == "FIRED"]), 0)

    def test_N002_delivery_fail_is_recoverable(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = ShiGuangApp.open(ROOT, Path(tmp.name) / "n2.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        rem = app.store.query_one("SELECT * FROM reminders")
        app.clock.set(rem["due_at"] + 1000)
        app.delivery_adapter.fail_next = True
        results = app.run_due_tasks()
        self.assertTrue(any(r.get("status") == "DELIVERY_FAILED" for r in results))
        # must NOT be stuck at FIRED
        row = app.store.query_one("SELECT status FROM reminders WHERE reminder_id=?", (rem["reminder_id"],))
        self.assertNotEqual(row["status"], "FIRED")
        # retry succeeds
        results2 = app.run_due_tasks()
        self.assertEqual(len([x for x in results2 if x.get("status") == "FIRED"]), 1)
        notifs = [s for s in app.delivery_adapter.sent if s["kind"] == "notification"]
        self.assertEqual(len(notifs), 1)


class TestDirtyMultiMatter(unittest.TestCase):
    def test_F013_all_matters_marked(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = open_store(Path(tmp.name) / "t.sqlite")
        self.addCleanup(store.close)
        src = SourceEvidenceService(store)
        eng = StateCommitEngine(store, src)
        eng.commit_ops(
            [
                LedgerOp(op_id="c1", kind=OpKind.CREATE_MATTER.value, payload={"title": "a", "matter_id": "m1", "force_new": True}),
                LedgerOp(op_id="c2", kind=OpKind.CREATE_MATTER.value, payload={"title": "b", "matter_id": "m2", "force_new": True}),
            ]
        )
        dirty = {r["node_id"] for r in store.query("SELECT node_id FROM dirty_nodes")}
        self.assertIn("m1", dirty)
        self.assertIn("m2", dirty)


class TestWriteBypassDetection(unittest.TestCase):
    def test_F004_p1_requires_bridge(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = open_store(Path(tmp.name) / "t.sqlite")
        self.addCleanup(store.close)
        k = KnowledgeLedger(store)
        with self.assertRaises(RuntimeError):
            k.upsert(topic="t", content="c")
        # with bridge, appears in op_log
        src = SourceEvidenceService(store)
        eng = StateCommitEngine(store, src)
        k2 = KnowledgeLedger(store, P1WriteBridge(eng.commit_ops))
        r = k2.upsert(topic="t", content="c")
        self.assertEqual(r["receipt"].status, "COMMITTED")
        self.assertGreaterEqual(
            store.query("SELECT COUNT(*) c FROM op_log WHERE kind='upsert_knowledge'")[0]["c"], 1
        )


class TestScenarioCConvergence(unittest.TestCase):
    def test_multi_turn_near_synonym_converges(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = ShiGuangApp.open(ROOT, Path(tmp.name) / "c.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        app.clock.advance_hours(2)
        t1 = app.ingest_text("补充一下，是周三之前要确认。")
        app.clock.advance_hours(2)
        t2 = app.ingest_text("另外，合同盖章还要等对方回传。")
        n = app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n, 1)
        self.assertTrue(t1["receipt"].matter_ref in (None, mid) or t1["receipt"].matter_ref == mid)
        events = app.event.list_for_matter(mid)
        self.assertGreaterEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
