# -*- coding: utf-8 -*-
"""Matter Tree propagation: child change → parent dirty → incremental update → stop when unchanged."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import MatterTree, P1WriteBridge  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


class TestMatterTreePropagation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(
            ROOT, Path(self._tmp.name) / "tree.sqlite", clock=FakeClock(1_758_806_400_000)
        )
        self.addCleanup(self.app.close)
        self.bridge = self.app.p1_bridge
        self.tree = MatterTree(self.app.store, self.app.matter, self.bridge)

    def _create(self, title: str, mid: str, parent: str | None = None, next_action: str = ""):
        return self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id=f"op_{mid}",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": title,
                        "matter_id": mid,
                        "parent_matter_id": parent,
                        "next_action": next_action,
                        "force_new": True,
                    },
                )
            ]
        )

    def _update(self, mid: str, next_action: str):
        return self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id=f"op_upd_{mid}_{next_action}",
                    kind=OpKind.UPDATE_MATTER.value,
                    payload={"matter_id": mid, "next_action": next_action},
                    matter_ref=mid,
                )
            ]
        )

    def test_child_change_marks_parent_dirty_and_rolls_up(self):
        self._create("春促项目", "p1", next_action="盯整体")
        self._create("物料设计", "c1", parent="p1", next_action="出图")
        self.app.summary.process_dirty()

        # simulate a later child-only change
        self._update("c1", "改完终稿")
        self.app.summary.process_dirty()

        parent_cap = self.app.summary.capsule.get("p1")
        self.assertIsNotNone(parent_cap)
        blob = " ".join(parent_cap.get("open_items") or [])
        self.assertIn("物料设计", blob)
        self.assertIn("改完终稿", blob)
        self.assertFalse(self.app.summary.is_stale("p1"))
        self.assertFalse(self.app.summary.is_stale("c1"))

    def test_no_change_stops_propagation(self):
        self._create("根", "root", next_action="看结果")
        self._create("中层", "mid", parent="root", next_action="协调")
        self._create("叶子", "leaf", parent="mid", next_action="执行")
        self.app.summary.process_dirty()

        # clear all dirty, then re-sync leaf with identical content
        for n in list(self.app.summary.dirty.list_dirty()):
            self.app.summary.dirty.clear(n["node_id"])

        before_root = self.app.summary.capsule.get("root")
        before_mid = self.app.summary.capsule.get("mid")

        # force leaf dirty and sync with no real content change
        self.app.summary.dirty.mark("leaf", "matter")
        done = self.app.summary.process_dirty()
        self.assertIn("leaf", done)

        # parent must NOT be re-dirtied / rewritten when child content is unchanged
        dirty_ids = {n["node_id"] for n in self.app.summary.dirty.list_dirty()}
        self.assertNotIn("mid", dirty_ids)
        self.assertNotIn("root", dirty_ids)
        self.assertEqual(self.app.summary.capsule.get("root"), before_root)
        self.assertEqual(self.app.summary.capsule.get("mid"), before_mid)

    def test_propagates_up_only_while_content_changes(self):
        self._create("根", "root2", next_action="看结果")
        self._create("子", "child2", parent="root2", next_action="旧动作")
        self.app.summary.process_dirty()

        self._update("child2", "新动作")
        done = self.app.summary.process_dirty()
        self.assertIn("child2", done)
        self.assertIn("root2", done)
        root_cap = self.app.summary.capsule.get("root2")
        self.assertIn("新动作", " ".join(root_cap.get("open_items") or []))

        # further noop sync of root must not loop
        dirty_after = {n["node_id"] for n in self.app.summary.dirty.list_dirty()}
        self.assertEqual(dirty_after, set())

    def test_reparent_dirties_both_sides(self):
        self._create("旧父", "old_p", next_action="旧")
        self._create("新父", "new_p", next_action="新")
        self._create("子项", "kid", parent="old_p", next_action="干活")
        self.app.summary.process_dirty()

        self.tree.set_parent("kid", "new_p")
        self.app.summary.process_dirty()

        old_cap = self.app.summary.capsule.get("old_p")
        new_cap = self.app.summary.capsule.get("new_p")
        self.assertNotIn("子项", " ".join(old_cap.get("open_items") or []))
        self.assertIn("子项", " ".join(new_cap.get("open_items") or []))

    def test_tree_expand_after_propagation(self):
        self._create("项目A", "pa", next_action="总")
        self._create("子A1", "ca1", parent="pa", next_action="一")
        self._create("子A2", "ca2", parent="pa", next_action="二")
        self.app.summary.process_dirty()
        node = self.tree.expand_tree("pa")
        self.assertEqual(len(node["children"]), 2)
        self.assertFalse(self.app.summary.is_stale("pa"))

    def test_cycle_parent_does_not_hang(self):
        self._create("A", "ma", next_action="a")
        self._create("B", "mb", parent="ma", next_action="b")
        # illegal cycle via direct set_parent attempts — must not hang process_dirty
        self.tree.set_parent("ma", "mb")
        self.app.summary.process_dirty()
        self.assertTrue(True)  # reached = no hang

    def test_p0_regression_still_green(self):
        # keep a thin smoke of the P0 path on the same app
        r = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(r["receipt"].status, "COMMITTED")
        self.assertFalse(self.app.summary.is_stale(r["receipt"].matter_ref))


if __name__ == "__main__":
    unittest.main()
