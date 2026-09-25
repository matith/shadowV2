# -*- coding: utf-8 -*-
"""Nightly P0 integration fixture T0–T5 (任务书 §八)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402


def blob(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)


class TestNightlyFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_T0_to_T5_full_script(self):
        clock = FakeClock(1_758_806_400_000)  # T0 baseline
        db = Path(self._tmp.name) / "nightly.sqlite"
        app = ShiGuangApp.open(ROOT, db, clock=clock)
        self.addCleanup(app.close)

        # ---- T0 ----
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(t0["intent"], "reminder")
        mid = t0["receipt"].matter_ref
        self.assertIsNotNone(mid)
        self.assertEqual(t0["receipt"].status, "COMMITTED")

        # Event created
        events = app.event.list_for_matter(mid)
        self.assertGreaterEqual(len(events), 1)

        # Matter created/reused
        matter = app.matter.get(mid)
        self.assertIsNotNone(matter)
        self.assertIn("合同", blob(matter))

        # People 李经理
        person = app.people.find_by_name("李经理")
        self.assertIsNotNone(person)

        # Reminder created
        rem = app.store.query_one("SELECT * FROM reminders WHERE matter_id=?", (mid,))
        self.assertIsNotNone(rem)
        self.assertEqual(rem["status"], "SCHEDULED")

        # Source preserved
        src = app.source.raw.get(t0["source_id"])
        self.assertEqual(src["text_content"], "明天下午提醒我联系李经理，合同还没盖章。")

        # Capsule generated
        cap = app.summary.capsule.get(mid)
        self.assertIsNotNone(cap)
        self.assertEqual(cap["goal"], matter["title"])

        # Projection visible
        view = app.projection.render_default_my_matters()
        self.assertTrue(any(r["matter_id"] == mid for r in view["rows"]))

        # ---- T1 ----
        t1 = app.ingest_text("补充一下，是周三之前要确认。")
        self.assertEqual(t1["intent"], "supplement")
        # still same Matter
        n_matters = app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n_matters, 1)
        self.assertTrue(t1["receipt"].matter_ref in (None, mid) or t1["receipt"].matter_ref == mid)

        # new Event append
        events1 = app.event.list_for_matter(mid)
        self.assertGreaterEqual(len(events1), 2)

        # current state updated
        matter1 = app.matter.get(mid)
        self.assertIn("周三", blob(matter1))

        # Capsule incrementally updated
        cap1 = app.summary.capsule.get(mid)
        self.assertFalse(app.summary.is_stale(mid))
        self.assertTrue(cap1["current"] or cap1["open_items"] or cap1["recent"])

        # ---- T2 ----
        t2 = app.ingest_text("刚才说错了，不是周三，是周四。")
        self.assertEqual(t2["intent"], "correction")

        # Raw sources all preserved
        sources = app.store.query("SELECT * FROM raw_sources ORDER BY created_at")
        self.assertGreaterEqual(len(sources), 3)
        texts = " ".join(r["text_content"] or "" for r in sources)
        self.assertIn("周三", texts)
        self.assertIn("周四", texts)
        self.assertIn("说错了", texts)

        # old interpretation / state replaced
        matter2 = app.matter.get(mid)
        self.assertIn("周四", blob(matter2))
        self.assertNotIn("周三之前", blob(matter2))

        corrs = app.store.query("SELECT * FROM corrections")
        self.assertGreaterEqual(len(corrs), 1)

        # subsequent context no longer uses 周三 as current
        q_ctx = app.ingest_text("李经理那个合同现在怎么样？")
        matter_now = app.matter.get(mid)
        self.assertIn("周四", q_ctx["reply"] + blob(matter_now))
        # current fields must not still say 周三之前; historical events may retain it
        fields_now = blob(matter_now.get("fields") or {})
        self.assertNotIn("周三之前", fields_now)
        self.assertNotIn("周三之前", matter_now.get("next_action") or "")
        cap_now = app.summary.capsule.get(mid)
        self.assertNotIn("周三之前", (cap_now.get("current") or "") + json.dumps(cap_now.get("open_items") or [], ensure_ascii=False))

        # ---- T3: FakeClock advance to reminder due ----
        rem = app.store.query_one("SELECT * FROM reminders WHERE matter_id=? ORDER BY updated_at DESC", (mid,))
        # use the latest deadline reminder if created by correction/supplement
        rems = app.store.query("SELECT * FROM reminders WHERE matter_id=?", (mid,))
        target = max(rems, key=lambda r: r["updated_at"] if r["status"] == "SCHEDULED" else 0)
        # pick a SCHEDULED one
        scheduled = [r for r in rems if r["status"] == "SCHEDULED"]
        self.assertTrue(scheduled)
        target = scheduled[0]
        app.clock.set(int(target["due_at"]) + 1000)

        results = app.run_due_tasks()
        fired = [r for r in results if r.get("status") == "FIRED"]
        self.assertEqual(len(fired), 1)

        # only once
        results_again = app.run_due_tasks()
        self.assertEqual(len([r for r in results_again if r.get("status") == "FIRED"]), 0)

        # directive policy + delivery router + correct payload
        payload = fired[0]["payload"]
        self.assertEqual(payload.get("matter_id"), mid)
        self.assertTrue(payload.get("text"))
        notifs = [s for s in app.delivery_adapter.sent if s["kind"] == "notification" and s.get("reminder_ref")]
        self.assertGreaterEqual(len(notifs), 1)
        # collapse/dedup: same reminder not delivered twice
        self.assertEqual(len([n for n in notifs if n.get("reminder_ref") == target["reminder_id"]]), 1)

        # delivery receipt / effect receipt trackable
        delivs = app.store.query("SELECT * FROM deliveries WHERE reminder_ref=?", (target["reminder_id"],))
        self.assertEqual(len(delivs), 1)
        self.assertEqual(delivs[0]["status"], "SENT")
        effects = app.store.query("SELECT * FROM effect_receipts WHERE capability='deliver_notification'")
        self.assertGreaterEqual(len(effects), 1)

        # ---- T4: user clicks 完成 ----
        done = app.complete_reminder(target["reminder_id"])
        self.assertEqual(done["receipt"].status, "COMMITTED")
        # Matter updated via commit (not direct durable write)
        matter_done = app.matter.get(mid)
        # at least reminder completed; if this was the main reminder, matter may be DONE
        rem_done = app.store.query_one("SELECT status FROM reminders WHERE reminder_id=?", (target["reminder_id"],))
        self.assertEqual(rem_done["status"], "COMPLETED")
        # prove durable did not write matter without commit: op_log has COMPLETE_REMINDER
        op_rows = app.store.query("SELECT * FROM op_log WHERE kind='complete_reminder'")
        self.assertGreaterEqual(len(op_rows), 1)

        # ---- T5: restart / rebuild runtime session ----
        app.close()
        clock2 = FakeClock(app.clock.now() if False else 1_758_900_000_000)
        # reopen
        clock2 = FakeClock(1_758_900_000_000)
        app2 = ShiGuangApp.open(ROOT, db, clock=clock2)
        self.addCleanup(app2.close)

        q = app2.ingest_text("李经理那个合同现在怎么样？")
        self.assertIn("合同", q["reply"])
        # recover current state and evidence without chat session
        timeline = app2.matter_timeline(mid)
        self.assertIsNotNone(timeline["matter"])
        self.assertIn("周四", blob(timeline["matter"]))
        self.assertTrue(timeline["evidence_chain"] or timeline["events"])
        self.assertFalse(timeline["stale"])


class TestBoundaryContracts(unittest.TestCase):
    """Boundary-level checks matching BBM guarantees."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_commit_success_only_after_durable_write(self):
        app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "b.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        # invalid op must not commit
        from shiguang.types import CommitError, LedgerOp, OpKind, ValidationReject

        bad = LedgerOp(op_id="bad1", kind=OpKind.CREATE_REMINDER.value, payload={"matter_id": "x"})
        with self.assertRaises(Exception):
            app.commit.commit_ops([bad])
        self.assertEqual(app.store.query("SELECT COUNT(*) c FROM op_log")[0]["c"], 0)

    def test_high_risk_requires_confirmation(self):
        from shiguang.types import CommitError, LedgerOp, OpKind

        app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "b2.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        op = LedgerOp(
            op_id="hr1",
            kind=OpKind.CREATE_MATTER.value,
            payload={"title": "外发合同"},
            risk="high",
        )
        with self.assertRaises(CommitError):
            app.commit.commit_ops([op], require_confirm=True)

    def test_effect_receipt_on_delivery(self):
        app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "b3.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        effs = app.store.query("SELECT * FROM effect_receipts")
        self.assertGreaterEqual(len(effs), 1)

    def test_projection_edit_goes_through_commit(self):
        app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "b4.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app.close)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        res = app.projection.apply_cell_edit(mid, "status", "IN_PROGRESS")
        self.assertEqual(res["receipt"].status, "COMMITTED")
        self.assertEqual(app.matter.get(mid)["status"], "IN_PROGRESS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
