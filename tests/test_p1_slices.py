# -*- coding: utf-8 -*-
"""P1 slice tests — all writes through State/Commit bridge; P0 regression stays green."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import ArchiveLedger, KnowledgeLedger, MatterTree, P1WriteBridge  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


class TestP1Slices(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "p1.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(self.app.close)
        self.bridge = self.app.p1_bridge

    def _create_matter(self, title: str, matter_id: str | None = None, parent: str | None = None, next_action: str = ""):
        return self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id=f"op_{matter_id or title}",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": title,
                        "matter_id": matter_id,
                        "parent_matter_id": parent,
                        "next_action": next_action,
                        "force_new": True,
                    },
                )
            ]
        )

    def test_matter_tree_expand(self):
        self._create_matter("春促项目", matter_id="matter_parent")
        self._create_matter("物料设计", matter_id="matter_c1", parent="matter_parent")
        self._create_matter("渠道沟通", matter_id="matter_c2", parent="matter_parent")
        tree = MatterTree(self.app.store, self.app.matter, self.bridge)
        node = tree.expand_tree("matter_parent")
        self.assertEqual(node["matter_id"], "matter_parent")
        self.assertEqual(len(node["children"]), 2)
        titles = {c["title"] for c in node["children"]}
        self.assertEqual(titles, {"物料设计", "渠道沟通"})

    def test_set_parent_goes_through_commit(self):
        self._create_matter("父", matter_id="p1")
        self._create_matter("子", matter_id="c1")
        tree = MatterTree(self.app.store, self.app.matter, self.bridge)
        res = tree.set_parent("c1", "p1")
        self.assertEqual(res["receipt"].status, "COMMITTED")
        # op_log proves unique write path
        rows = self.app.store.query("SELECT * FROM op_log WHERE kind='set_matter_parent'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.app.matter.get("c1")["parent_matter_id"], "p1")

    def test_archive_mini_capsule_and_recall(self):
        self._create_matter("春促活动收尾", matter_id="matter_arch", next_action="写复盘")
        arch = ArchiveLedger(self.app.store, self.app.matter, self.bridge)
        cap = {"goal": "春促", "current": "复盘中"}
        res = arch.archive("matter_arch", mini_capsule=cap)
        self.assertEqual(res["receipt"].status, "COMMITTED")
        hits = arch.recall("春促")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["mini_capsule"]["goal"], "春促")
        self.assertEqual(hits[0]["pointer"], "matter:matter_arch")
        self.assertEqual(self.app.matter.get("matter_arch")["status"], "ARCHIVED")

    def test_knowledge_upsert_via_commit(self):
        k = KnowledgeLedger(self.app.store, self.bridge)
        r1 = k.upsert(topic="李经理偏好", content="喜欢邮件确认")
        self.assertEqual(r1["receipt"].status, "COMMITTED")
        r2 = k.upsert(topic="李经理偏好", content="喜欢微信确认")
        self.assertEqual(r2["receipt"].status, "COMMITTED")
        self.assertEqual(r1["knowledge_id"], r2["knowledge_id"])
        hits = k.search("微信")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["content"], "喜欢微信确认")
        # must appear in op_log (unique write path)
        self.assertGreaterEqual(
            self.app.store.query("SELECT COUNT(*) c FROM op_log WHERE kind='upsert_knowledge'")[0]["c"], 2
        )

    def test_p0_regression_still_green(self):
        r = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(r["intent"], "reminder")
        mid = r["receipt"].matter_ref
        n = self.app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n, 1)
        self.assertIsNotNone(self.app.people.find_by_name("李经理"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
