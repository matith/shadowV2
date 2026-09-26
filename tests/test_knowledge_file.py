# -*- coding: utf-8 -*-
"""Knowledge + File ledgers: Source stored once, referenced by id, never full-text copied."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import FileLedger, KnowledgeLedger, P1WriteBridge  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


class TestKnowledgeFileSourceOnce(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(
            ROOT, Path(self._tmp.name) / "kf.sqlite", clock=FakeClock(1_758_806_400_000)
        )
        self.addCleanup(self.app.close)
        self.k = KnowledgeLedger(self.app.store, self.app.p1_bridge)
        self.f = FileLedger(self.app.store, self.app.p1_bridge)

        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="kf_m",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "合同归档", "matter_id": "matter_kf", "force_new": True},
                )
            ]
        )
        # one real source — used by knowledge + file + event
        self.source_id = self.app.source.raw.store_text(
            "李经理偏好邮件确认，合同用 PDF 盖章。",
            channel="fake",
            user_ref="user",
        )

    def test_source_stored_once_shared_by_refs(self):
        self.k.upsert(topic="李经理偏好", content="喜欢邮件确认", source_id=self.source_id)
        self.f.attach(
            matter_id="matter_kf",
            filename="合同.pdf",
            source_id=self.source_id,
            file_type="pdf",
            product_ref="prod_contract",
        )
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="kf_evt",
                    kind=OpKind.APPEND_EVENT.value,
                    payload={"event_type": "note", "summary": "记下偏好"},
                    matter_ref="matter_kf",
                    source_ref=self.source_id,
                )
            ]
        )
        n = self.app.store.query(
            "SELECT COUNT(*) c FROM raw_sources WHERE source_id=?", (self.source_id,)
        )[0]["c"]
        self.assertEqual(n, 1)
        total_sources = self.app.store.query("SELECT COUNT(*) c FROM raw_sources")[0]["c"]
        self.assertEqual(total_sources, 1)

    def test_knowledge_references_source_not_full_text(self):
        r = self.k.upsert(topic="李经理偏好", content="喜欢邮件确认", source_id=self.source_id)
        self.assertEqual(r["receipt"].status, "COMMITTED")
        row = self.k.get(topic="李经理偏好")
        self.assertEqual(row["source_id"], self.source_id)
        # knowledge content is the fact, not a dump of source text
        self.assertNotIn("合同用 PDF 盖章", row["content"])
        self.assertEqual(self.k.source_pointer(row["knowledge_id"]), self.source_id)
        # source text lives only in raw_sources
        src = self.app.source.raw.get(self.source_id)
        self.assertIn("李经理偏好邮件确认", src["text_content"])

    def test_file_references_source_not_bytes(self):
        r = self.f.attach(
            matter_id="matter_kf",
            filename="合同.pdf",
            source_id=self.source_id,
            file_type="pdf",
            product_ref="prod_contract",
        )
        self.assertEqual(r["receipt"].status, "COMMITTED")
        fid = r["file_id"]
        self.assertIsNotNone(fid)
        row = self.f.get(fid)
        self.assertEqual(row["source_id"], self.source_id)
        self.assertEqual(row["filename"], "合同.pdf")
        self.assertEqual(row["product_ref"], "prod_contract")
        # no bytes/text copy inside files table
        self.assertIsNone(row.get("text_content"))
        self.assertIsNone(row.get("bytes"))
        self.assertEqual(self.f.source_pointer(fid), self.source_id)

    def test_file_list_by_matter_and_product(self):
        self.f.attach(matter_id="matter_kf", filename="a.pdf", source_id=self.source_id, product_ref="p1")
        self.f.attach(matter_id="matter_kf", filename="b.pdf", source_id=self.source_id, product_ref="p1")
        self.f.attach(matter_id="matter_kf", filename="c.docx", source_id=self.source_id, product_ref="p2")
        by_m = self.f.list_for_matter("matter_kf")
        self.assertEqual(len(by_m), 3)
        by_p = self.f.list_for_product("p1")
        self.assertEqual({x["filename"] for x in by_p}, {"a.pdf", "b.pdf"})

    def test_knowledge_upsert_updates_in_place(self):
        r1 = self.k.upsert(topic="T", content="v1", source_id=self.source_id)
        r2 = self.k.upsert(topic="T", content="v2", source_id=self.source_id)
        self.assertEqual(r1["knowledge_id"], r2["knowledge_id"])
        self.assertEqual(self.k.get(topic="T")["content"], "v2")
        n = self.app.store.query("SELECT COUNT(*) c FROM knowledge")[0]["c"]
        self.assertEqual(n, 1)

    def test_writes_go_through_commit(self):
        self.k.upsert(topic="K", content="c", source_id=self.source_id)
        self.f.attach(matter_id="matter_kf", filename="x.pdf", source_id=self.source_id)
        kinds = {r["kind"] for r in self.app.store.query("SELECT kind FROM op_log")}
        self.assertIn("upsert_knowledge", kinds)
        self.assertIn("attach_file", kinds)

    def test_p0_smoke(self):
        r = self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.assertEqual(r["receipt"].status, "COMMITTED")


if __name__ == "__main__":
    unittest.main()
