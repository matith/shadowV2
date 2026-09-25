# -*- coding: utf-8 -*-
"""P1 slice tests — must not break P0 regression."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import ArchiveLedger, KnowledgeLedger, MatterTree  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402


class TestP1Slices(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(ROOT, Path(self._tmp.name) / "p1.sqlite", clock=FakeClock(1_758_806_400_000))
        self.addCleanup(self.app.close)

    def test_matter_tree_expand(self):
        tree = MatterTree(self.app.store, self.app.matter)
        parent = self.app.matter.create(title="春促项目", matter_id="matter_parent")
        c1 = self.app.matter.create(title="物料设计", matter_id="matter_c1", parent_matter_id=parent)
        c2 = self.app.matter.create(title="渠道沟通", matter_id="matter_c2", parent_matter_id=parent)
        node = tree.expand_tree(parent)
        self.assertEqual(node["matter_id"], parent)
        self.assertEqual(len(node["children"]), 2)
        titles = {c["title"] for c in node["children"]}
        self.assertEqual(titles, {"物料设计", "渠道沟通"})

    def test_archive_mini_capsule_and_recall(self):
        arch = ArchiveLedger(self.app.store, self.app.matter)
        mid = self.app.matter.create(title="春促活动收尾", next_action="写复盘")
        cap = {"goal": "春促", "current": "复盘中"}
        arch.archive(mid, mini_capsule=cap)
        hits = arch.recall("春促")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["mini_capsule"]["goal"], "春促")
        self.assertEqual(hits[0]["pointer"], f"matter:{mid}")
        self.assertEqual(self.app.matter.get(mid)["status"], "ARCHIVED")

    def test_knowledge_upsert(self):
        k = KnowledgeLedger(self.app.store)
        kid = k.upsert(topic="李经理偏好", content="喜欢邮件确认")
        kid2 = k.upsert(topic="李经理偏好", content="喜欢微信确认")
        self.assertEqual(kid, kid2)
        hits = k.search("微信")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["content"], "喜欢微信确认")

    def test_p0_regression_still_green(self):
        r = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(r["intent"], "reminder")
        mid = r["receipt"].matter_ref
        n = self.app.store.query("SELECT COUNT(*) c FROM matters")[0]["c"]
        self.assertEqual(n, 1)
        self.assertIsNotNone(self.app.people.find_by_name("李经理"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
