# -*- coding: utf-8 -*-
"""P0 unit / boundary / scenario tests."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.identity import EXPECTED_UUID, identity_from_repo_root  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


def make_app(tmp: str, clock: FakeClock | None = None) -> ShiGuangApp:
    return ShiGuangApp.open(ROOT, Path(tmp) / "p0.sqlite", clock=clock)


def json_blob(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class _AppCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def open_app(self, clock: FakeClock | None = None) -> ShiGuangApp:
        app = make_app(self._tmp.name, clock)
        self.addCleanup(app.close)
        return app


class TestIdentityGate(unittest.TestCase):
    def test_rejects_wrong_uuid(self):
        from shiguang.identity import ProjectIdentity, verify_identity
        from shiguang.types import IdentityError

        bad = ProjectIdentity(
            project_uuid="wrong",
            project_name="shadowV2",
            repo="matith/shadowV2",
            local_root=str(ROOT),
            canonical_generation="g000259",
        )
        with self.assertRaises(IdentityError):
            verify_identity(bad)

    def test_accepts_expected(self):
        from shiguang.identity import verify_identity

        verify_identity(identity_from_repo_root(ROOT))


class TestSourceImmutable(_AppCase):
    def test_source_not_mutated_by_correction(self):
        app = self.open_app(FakeClock(1_758_806_400_000))
        r1 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        source_id = r1["source_id"]
        src_before = app.source.raw.get(source_id)
        self.assertEqual(src_before["text_content"], "明天下午提醒我联系李经理，合同还没盖章。")

        app.ingest_text("补充一下，是周三之前要确认。")
        app.ingest_text("刚才说错了，不是周三，是周四。")
        src_after = app.source.raw.get(source_id)
        self.assertEqual(src_after["text_content"], src_before["text_content"])
        self.assertEqual(src_after["hash"], src_before["hash"])
        n = app.store.query("SELECT COUNT(*) c FROM raw_sources")[0]["c"]
        self.assertGreaterEqual(n, 3)


class TestIdempotentOps(_AppCase):
    def test_duplicate_op_id_no_double_write(self):
        app = self.open_app(FakeClock(1_758_806_400_000))
        op = LedgerOp(
            op_id="op_fixed_1",
            kind=OpKind.CREATE_MATTER.value,
            payload={"title": "测试事项", "matter_id": "matter_fixed"},
        )
        r1 = app.commit.commit_ops([op])
        r2 = app.commit.commit_ops([op])
        self.assertEqual(r1.status, "COMMITTED")
        self.assertEqual(r2.status, "DUPLICATE")
        n = app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n, 1)


class TestScenarioA(_AppCase):
    def test_full_reminder_lifecycle(self):
        app = self.open_app(FakeClock(1_758_806_400_000))

        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(t0["intent"], "reminder")
        self.assertIsNotNone(t0["receipt"].matter_ref)
        matter_id = t0["receipt"].matter_ref
        matter = app.matter.get(matter_id)
        self.assertIn("合同", matter["title"] + (matter.get("next_action") or ""))

        person = app.people.find_by_name("李经理")
        self.assertIsNotNone(person)

        rem = app.store.query_one("SELECT * FROM reminders WHERE matter_id=?", (matter_id,))
        self.assertIsNotNone(rem)
        self.assertEqual(rem["status"], "SCHEDULED")

        cap = app.summary.capsule.get(matter_id)
        self.assertIsNotNone(cap)
        self.assertFalse(app.summary.is_stale(matter_id))

        view = app.projection.render_default_my_matters()
        self.assertTrue(any(r["matter_id"] == matter_id for r in view["rows"]))

        # advance clock past due
        app.clock.set(rem["due_at"] + 60_000)
        results = app.run_due_tasks()
        fired = [r for r in results if r.get("status") == "FIRED"]
        self.assertEqual(len(fired), 1)
        payload = fired[0]["payload"]
        self.assertIn("合同", payload["text"] + payload.get("title", ""))
        self.assertEqual(payload.get("matter_id"), matter_id)

        # second run_due must not double-fire
        results2 = app.run_due_tasks()
        fired2 = [r for r in results2 if r.get("status") == "FIRED"]
        self.assertEqual(len(fired2), 0)

        sent = app.delivery_adapter.sent
        notifications = [s for s in sent if s["kind"] == "notification"]
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].get("matter_ref"), matter_id)

        done = app.complete_reminder(rem["reminder_id"])
        self.assertEqual(done["receipt"].status, "COMMITTED")
        matter2 = app.matter.get(matter_id)
        self.assertEqual(matter2["status"], "DONE")
        rem2 = app.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rem["reminder_id"],))
        self.assertEqual(rem2["status"], "COMPLETED")


class TestScenarioC(_AppCase):
    def test_same_matter_across_updates(self):
        app = self.open_app(FakeClock(1_758_806_400_000))
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        t1 = app.ingest_text("补充一下，是周三之前要确认。")
        mid2 = t1["receipt"].matter_ref or mid
        n = app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n, 1)
        self.assertEqual(mid2, mid)
        events = app.event.list_for_matter(mid)
        self.assertGreaterEqual(len(events), 2)
        cap = app.summary.capsule.get(mid)
        self.assertFalse(app.summary.is_stale(mid))
        self.assertIsNotNone(cap)


class TestScenarioE(_AppCase):
    def test_correction_updates_current_not_source(self):
        app = self.open_app(FakeClock(1_758_806_400_000))
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        app.ingest_text("补充一下，是周三之前要确认。")
        t2 = app.ingest_text("刚才说错了，不是周三，是周四。")
        self.assertEqual(t2["intent"], "correction")

        matter = app.matter.get(mid)
        blob = json_blob(matter)
        self.assertIn("周四", blob)
        self.assertNotIn("周三之前", blob)

        sources = app.store.query("SELECT text_content FROM raw_sources")
        texts = " ".join(r["text_content"] or "" for r in sources)
        self.assertIn("周三", texts)
        self.assertIn("说错了", texts)

        corrs = app.store.query("SELECT * FROM corrections")
        self.assertGreaterEqual(len(corrs), 1)

        q = app.ingest_text("李经理那个合同现在怎么样？")
        self.assertIn("周四", q["reply"] + json_blob(q.get("extract") or {}) + json_blob(app.matter.get(mid)))


class TestTaskActionBridge(_AppCase):
    def test_complete_does_not_bypass_commit(self):
        app = self.open_app(FakeClock(1_758_806_400_000))
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        rem = app.store.query_one("SELECT * FROM reminders WHERE matter_id=?", (mid,))
        ops = app.durable.bridge.complete(rem["reminder_id"])
        self.assertTrue(all(isinstance(o, LedgerOp) for o in ops))
        self.assertNotEqual(app.matter.get(mid)["status"], "DONE")
        receipt = app.commit.commit_ops(ops)
        self.assertEqual(receipt.status, "COMMITTED")
        self.assertEqual(app.matter.get(mid)["status"], "DONE")


class TestRestartRecovery(_AppCase):
    def test_reopen_from_canonical(self):
        db = Path(self._tmp.name) / "p0.sqlite"
        clock = FakeClock(1_758_806_400_000)
        app = ShiGuangApp.open(ROOT, db, clock=clock)
        t0 = app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        mid = t0["receipt"].matter_ref
        app.close()

        clock2 = FakeClock(clock.now())
        app2 = ShiGuangApp.open(ROOT, db, clock=clock2)
        self.addCleanup(app2.close)
        matter = app2.matter.get(mid)
        self.assertIsNotNone(matter)
        q = app2.ingest_text("李经理那个合同现在怎么样？")
        self.assertIn("合同", q["reply"] + json_blob(matter))


if __name__ == "__main__":
    unittest.main(verbosity=2)
