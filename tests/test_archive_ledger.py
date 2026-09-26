# -*- coding: utf-8 -*-
"""Archive Ledger completion: mini capsule in daily context, recall, drill-down."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import ArchiveLedger, P1WriteBridge  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


class TestArchiveLedgerComplete(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(
            ROOT, Path(self._tmp.name) / "arch.sqlite", clock=FakeClock(1_758_806_400_000)
        )
        self.addCleanup(self.app.close)
        self.arch = ArchiveLedger(self.app.store, self.app.matter, self.app.p1_bridge)

    def _seed_matter_with_history(self, mid: str = "matter_arch1"):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="am",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": "春促活动收尾",
                        "matter_id": mid,
                        "next_action": "写复盘",
                        "force_new": True,
                    },
                )
            ]
        )
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="ae1",
                    kind=OpKind.APPEND_EVENT.value,
                    payload={"event_type": "note", "summary": "预算已批"},
                    matter_ref=mid,
                ),
                LedgerOp(
                    op_id="ae2",
                    kind=OpKind.APPEND_EVENT.value,
                    payload={"event_type": "note", "summary": "物料已发"},
                    matter_ref=mid,
                ),
            ]
        )
        return mid

    def test_daily_context_carries_mini_capsule_only(self):
        mid = self._seed_matter_with_history()
        self.app.summary.process_dirty()
        self.arch.archive(mid, mini_capsule={"goal": "春促", "current": "复盘中", "open_items": ["写复盘"]})

        ctx = self.app.working_context.compile(query="春促活动怎么样")
        arch_caps = [c for c in ctx["capsules"] if c.get("matter_id") == mid]
        self.assertTrue(arch_caps)
        cap = arch_caps[0]
        self.assertTrue(cap.get("archived"))
        self.assertEqual(cap["goal"], "春促")
        # full history must NOT ride along in daily context
        self.assertEqual(cap.get("recent"), [])
        self.assertEqual(cap.get("evidence"), [])
        blob = str(cap)
        self.assertNotIn("预算已批", blob)
        self.assertIn("写复盘", str(cap.get("open_items")))

        # sources mark it as archive_mini with a pointer
        srcs = [s for s in ctx["sources"] if s.get("matter_id") == mid]
        self.assertTrue(srcs)
        self.assertEqual(srcs[0]["type"], "archive_mini")
        self.assertTrue(srcs[0].get("pointer"))

    def test_recall_hits_mini_capsule(self):
        mid = self._seed_matter_with_history()
        self.arch.archive(mid, mini_capsule={"goal": "春促复盘", "current": "已完成", "open_items": []})
        hits = self.arch.recall("春促")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["matter_id"], mid)
        self.assertEqual(hits[0]["mini_capsule"]["goal"], "春促复盘")
        self.assertEqual(hits[0]["pointer"], f"matter:{mid}")

        # keyword miss returns empty
        self.assertEqual(self.arch.recall("完全无关的词xyz"), [])

    def test_drill_down_returns_full_matter_event_source(self):
        mid = self._seed_matter_with_history()
        self.arch.archive(mid, mini_capsule={"goal": "春促", "current": "复盘中"})
        full = self.arch.drill_down(mid)

        self.assertEqual(full["matter"]["matter_id"], mid)
        self.assertEqual(full["matter"]["status"], "ARCHIVED")
        summaries = [e["summary"] for e in full["events"]]
        self.assertIn("预算已批", summaries)
        self.assertIn("物料已发", summaries)
        self.assertIsNotNone(full["mini_capsule"])
        self.assertEqual(full["pointer"], f"matter:{mid}")
        self.assertIn("reminders", full)

    def test_archive_is_not_delete(self):
        mid = self._seed_matter_with_history()
        self.arch.archive(mid, mini_capsule={"goal": "春促"})
        # original events still queryable
        n = self.app.store.query("SELECT COUNT(*) c FROM events WHERE matter_id=?", (mid,))[0]["c"]
        self.assertEqual(n, 2)
        # matter row still present
        self.assertIsNotNone(self.app.matter.get(mid))
        # sources / raw rows untouched in count
        self.assertGreaterEqual(
            self.app.store.query("SELECT COUNT(*) c FROM raw_sources")[0]["c"], 0
        )

    def test_open_matters_exclude_archived_from_list_open(self):
        mid = self._seed_matter_with_history()
        self.arch.archive(mid, mini_capsule={"goal": "春促"})
        open_ids = {m["matter_id"] for m in self.app.matter.list_open()}
        self.assertNotIn(mid, open_ids)

    def test_recall_after_restart(self):
        db = Path(self._tmp.name) / "arch_restart.sqlite"
        app = ShiGuangApp.open(ROOT, db, clock=FakeClock(1_758_806_400_000))
        arch = ArchiveLedger(app.store, app.matter, app.p1_bridge)
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="am_rr",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "重启归档", "matter_id": "matter_rr", "force_new": True},
                )
            ]
        )
        app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="ae_rr",
                    kind=OpKind.APPEND_EVENT.value,
                    payload={"event_type": "note", "summary": "重启前的事件"},
                    matter_ref="matter_rr",
                )
            ]
        )
        arch.archive("matter_rr", mini_capsule={"goal": "重启后仍可召回"})
        app.close()

        app2 = ShiGuangApp.open(ROOT, db, clock=FakeClock(1_758_806_400_000))
        self.addCleanup(app2.close)
        arch2 = ArchiveLedger(app2.store, app2.matter, app2.p1_bridge)
        hits = arch2.recall("重启后")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["mini_capsule"]["goal"], "重启后仍可召回")
        full = arch2.drill_down("matter_rr")
        self.assertTrue(full["events"])
        self.assertEqual(full["events"][0]["summary"], "重启前的事件")


if __name__ == "__main__":
    unittest.main()
