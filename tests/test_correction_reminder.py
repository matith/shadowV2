# -*- coding: utf-8 -*-
"""Correction(due/time) must reschedule linked active reminders.

Contract under test:
- Correction → find active Reminder linked to the Matter / old due
  → reschedule in-place (no second active row)
- Source stays immutable
- Canonical writes stay on State/Commit
- restart keeps the corrected due
- old due does not fire; new due does
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402

T0 = 1_758_806_400_000
OLD_DUE = T0 + 2 * 86_400_000  # "周三"
NEW_DUE = T0 + 3 * 86_400_000  # "周四"


def _open(tmp: str, db_name: str = "crl.sqlite", clock: FakeClock | None = None) -> ShiGuangApp:
    app = ShiGuangApp.open(ROOT, Path(tmp) / db_name, clock=clock or FakeClock(T0))
    return app


class TestCorrectionReminderReschedule(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _seed_matter_with_reminder(self, app: ShiGuangApp, *, mid: str = "matter_c1") -> str:
        """Matter + one active reminder at OLD_DUE (the original 周三 commitment)."""
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="seed_m",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": "联系李经理合同盖章",
                        "matter_id": mid,
                        "due_at": OLD_DUE,
                        "next_action": "确认（周三之前）",
                        "force_new": True,
                    },
                )
            ]
        )
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="seed_r",
                    kind=OpKind.CREATE_REMINDER.value,
                    payload={
                        "matter_id": mid,
                        "title": "截止确认",
                        "body": "周三之前要确认",
                        "due_at": OLD_DUE,
                        "collapse_key": f"{mid}:deadline",
                        "next_action": "确认",
                    },
                )
            ]
        )
        return mid

    def _active_reminders(self, app: ShiGuangApp, mid: str) -> list[dict]:
        rows = app.store.query(
            "SELECT * FROM reminders WHERE matter_id=? AND status IN "
            "('SCHEDULED','SNOOZED','MISSED') ORDER BY due_at",
            (mid,),
        )
        return [dict(r) for r in rows]

    def test_correction_reschedules_linked_active_reminder(self):
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        mid = self._seed_matter_with_reminder(app)

        r = app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                )
            ]
        )
        self.assertEqual(r.status, "COMMITTED")
        # receipt carries old → new for the reminder too
        fields = {c.get("field") for c in r.old_to_new}
        self.assertIn("due_at", fields)
        self.assertIn("reminder.due_at", fields)

        actives = self._active_reminders(app, mid)
        self.assertEqual(len(actives), 1, "must not leave a second active reminder")
        self.assertEqual(actives[0]["due_at"], NEW_DUE)
        self.assertEqual(actives[0]["status"], "SCHEDULED")

        matter = app.matter.get(mid)
        self.assertEqual(matter["due_at"], NEW_DUE)

    def test_no_double_active_after_correction_creates_reminder(self):
        """Correction path also emits CREATE_REMINDER with the new due — must reuse, not double."""
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        mid = self._seed_matter_with_reminder(app)

        r = app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due2",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                ),
                LedgerOp(
                    op_id="corr_rem",
                    kind=OpKind.CREATE_REMINDER.value,
                    payload={
                        "matter_id": mid,
                        "title": "周四",
                        "body": "改成周四确认",
                        "due_at": NEW_DUE,
                        "collapse_key": f"{mid}:deadline",
                        "next_action": "确认（周四之前）",
                    },
                    matter_ref=mid,
                ),
            ]
        )
        self.assertEqual(r.status, "COMMITTED")
        actives = self._active_reminders(app, mid)
        self.assertEqual(len(actives), 1, f"double active reminder: {actives}")
        self.assertEqual(actives[0]["due_at"], NEW_DUE)

        # completed/cancelled history is allowed, but only one scannable row
        all_rows = app.store.query("SELECT status, due_at FROM reminders WHERE matter_id=?", (mid,))
        scannable = [dict(x) for x in all_rows if x["status"] in ("SCHEDULED", "SNOOZED", "MISSED")]
        self.assertEqual(len(scannable), 1)

    def test_old_due_does_not_fire_new_due_fires(self):
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        mid = self._seed_matter_with_reminder(app)
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due3",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                )
            ]
        )

        # walk the clock to just past the OLD due — must not fire
        app.clock.set(OLD_DUE + 1_000)
        results = app.run_due_tasks()
        fired_old = [x for x in results if x.get("status") == "FIRED"]
        self.assertEqual(fired_old, [], "old due must not fire after correction")

        # walk to the NEW due — must fire exactly once
        app.clock.set(NEW_DUE + 1_000)
        results2 = app.run_due_tasks()
        fired_new = [x for x in results2 if x.get("status") == "FIRED"]
        self.assertEqual(len(fired_new), 1)
        self.assertEqual(fired_new[0]["payload"]["matter_id"], mid)

        # no second fire on a later scan
        app.clock.set(NEW_DUE + 60_000)
        results3 = app.run_due_tasks()
        self.assertEqual([x for x in results3 if x.get("status") == "FIRED"], [])

    def test_restart_keeps_corrected_due(self):
        db = Path(self._tmp.name) / "crl_restart.sqlite"
        app = ShiGuangApp.open(ROOT, db, clock=FakeClock(T0))
        mid = self._seed_matter_with_reminder(app)
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due4",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                )
            ]
        )
        app.close()

        app2 = ShiGuangApp.open(ROOT, db, clock=FakeClock(OLD_DUE + 1_000))
        self.addCleanup(app2.close)
        actives = self._active_reminders(app2, mid)
        self.assertEqual(len(actives), 1)
        self.assertEqual(actives[0]["due_at"], NEW_DUE)
        self.assertEqual(app2.matter.get(mid)["due_at"], NEW_DUE)

        # after restart, old due still must not fire
        results = app2.run_due_tasks()
        self.assertEqual([x for x in results if x.get("status") == "FIRED"], [])

        app2.clock.set(NEW_DUE + 1_000)
        results2 = app2.run_due_tasks()
        self.assertEqual(len([x for x in results2 if x.get("status") == "FIRED"]), 1)

    def test_unrelated_reminder_not_moved(self):
        """A second reminder at a different time is a different commitment."""
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        mid = self._seed_matter_with_reminder(app)
        other_due = T0 + 86_400_000
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="seed_r2",
                    kind=OpKind.CREATE_REMINDER.value,
                    payload={
                        "matter_id": mid,
                        "title": "联系李经理",
                        "due_at": other_due,
                        "body": "明天下午联系",
                    },
                )
            ]
        )
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due5",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                )
            ]
        )
        actives = {r["title"]: r for r in self._active_reminders(app, mid)}
        self.assertEqual(actives["截止确认"]["due_at"], NEW_DUE)
        self.assertEqual(actives["联系李经理"]["due_at"], other_due)

    def test_source_immutable_and_write_via_commit(self):
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        mid = self._seed_matter_with_reminder(app)
        before = app.store.query("SELECT reminder_id, due_at, status FROM reminders WHERE matter_id=?", (mid,))
        before_rows = [dict(r) for r in before]

        r = app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="corr_due6",
                    kind=OpKind.CORRECT_FIELD.value,
                    payload={
                        "target_kind": "matter",
                        "target_id": mid,
                        "field": "due_at",
                        "new_value": NEW_DUE,
                    },
                    matter_ref=mid,
                )
            ]
        )
        self.assertEqual(r.status, "COMMITTED")
        # original reminder_id is kept (in-place reschedule, not delete+insert)
        after = app.store.query("SELECT reminder_id, due_at FROM reminders WHERE matter_id=?", (mid,))
        after_rows = [dict(r) for r in after]
        self.assertEqual(len(after_rows), len(before_rows))
        self.assertEqual(after_rows[0]["reminder_id"], before_rows[0]["reminder_id"])
        # op_log proves unique write path
        ops = app.store.query("SELECT * FROM op_log WHERE kind='correct_field'")
        self.assertEqual(len(ops), 1)

    def test_e2e_ingest_not_wednesday_is_thursday(self):
        """Real product path: speech correction must not leave the old Wednesday deadline active."""
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        app.ingest_text("补充一下，是周三之前要确认。")

        deadline_before = [
            dict(r)
            for r in app.store.query(
                "SELECT * FROM reminders WHERE matter_id=? AND (collapse_key LIKE '%:deadline' OR title LIKE '%周三%' OR title LIKE '%截止%')",
                (mid,),
            )
        ]
        self.assertTrue(deadline_before, "supplement should create a deadline reminder")
        old_deadline_due = deadline_before[0]["due_at"]

        t2 = app.ingest_text("刚才说错了，不是周三，是周四。")
        self.assertEqual(t2["intent"], "correction")

        actives = self._active_reminders(app, mid)
        deadline = [
            r
            for r in actives
            if (r.get("collapse_key") or "").endswith(":deadline")
            or "周四" in (r.get("title") or "")
            or "截止" in (r.get("title") or "")
        ]
        self.assertLessEqual(len(deadline), 1, f"double deadline reminder: {deadline}")
        if deadline:
            self.assertNotEqual(
                deadline[0]["due_at"],
                old_deadline_due,
                "deadline reminder must leave the corrected old time",
            )

        # the *old deadline* must not fire; other commitments (e.g. 明天下午) may
        app.clock.set(old_deadline_due + 1_000)
        fired = [x for x in app.run_due_tasks() if x.get("status") == "FIRED"]
        fired_ids = {x["reminder_id"] for x in fired}
        self.assertFalse(
            any(rid == deadline_before[0]["reminder_id"] for rid in fired_ids),
            "corrected deadline reminder must not fire at the old due",
        )
        for row in app.store.query(
            "SELECT reminder_id, due_at FROM reminders WHERE matter_id=? AND collapse_key LIKE '%:deadline'",
            (mid,),
        ):
            self.assertNotEqual(row["due_at"], old_deadline_due)

    def test_ingest_main_chain_no_double_active(self):
        """Audit gap: production ingest, NOT pre-seeded collapse_key.

        msg1 creates one commitment; correction must not leave a second
        active reminder / second notification for the same commitment.
        """
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        self.assertEqual(len(self._active_reminders(app, mid)), 1)

        t2 = app.ingest_text("刚才说错了，不是周三，是周四。")
        self.assertEqual(t2["intent"], "correction")

        actives = self._active_reminders(app, mid)
        self.assertEqual(
            len(actives),
            1,
            f"correction ingest must leave one active reminder, got {actives}",
        )
        new_due = int(actives[0]["due_at"])
        # corrected due fires exactly once; total notifications stay 1
        app.clock.set(new_due + 1_000)
        fired_new = [x for x in app.run_due_tasks() if x.get("status") == "FIRED"]
        self.assertEqual(len(fired_new), 1, f"expected single fire, got {fired_new}")

        notifications = [s for s in app.delivery_adapter.sent if s["kind"] == "notification"]
        self.assertEqual(len(notifications), 1, f"double notification: {notifications}")

    def test_ingest_main_chain_with_supplement_keeps_distinct_commitments(self):
        """Supplement adds a real second commitment; only the deadline moves."""
        app = _open(self._tmp.name)
        self.addCleanup(app.close)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        app.ingest_text("补充一下，是周三之前要确认。")
        before = self._active_reminders(app, mid)
        self.assertEqual(len(before), 2)

        app.ingest_text("刚才说错了，不是周三，是周四。")
        actives = self._active_reminders(app, mid)
        # contact reminder stays; deadline is moved, not duplicated
        self.assertEqual(len(actives), 2, actives)
        deadline = [r for r in actives if (r.get("collapse_key") or "").endswith(":deadline")]
        self.assertEqual(len(deadline), 1, deadline)
        contact = [r for r in actives if not (r.get("collapse_key") or "").endswith(":deadline")]
        self.assertEqual(len(contact), 1)
        self.assertNotEqual(deadline[0]["due_at"], contact[0]["due_at"])

        # total notifications after both dues = 2 (two real commitments), never 3
        app.clock.set(int(actives[0]["due_at"]) + 1_000)
        app.run_due_tasks()
        app.clock.set(int(actives[1]["due_at"]) + 1_000)
        app.run_due_tasks()
        notifications = [s for s in app.delivery_adapter.sent if s["kind"] == "notification"]
        self.assertEqual(len(notifications), 2, notifications)


if __name__ == "__main__":
    unittest.main()
