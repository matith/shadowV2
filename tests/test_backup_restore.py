# -*- coding: utf-8 -*-
"""Backup / Restore: Canonical + Source recoverable; Derived rebuildable."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import BackupRestore  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402


class TestBackupRestore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = ShiGuangApp.open(
            ROOT, Path(self._tmp.name) / "live.sqlite", clock=FakeClock(1_758_806_400_000)
        )
        self.addCleanup(self.app.close)
        self.bk = BackupRestore(self.app.store)

        # seed real state
        self.app.ingest_text("明天下午提醒我联系李经理，合同还没盖章。")
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="bk_k",
                    kind=OpKind.UPSERT_KNOWLEDGE.value,
                    payload={"topic": "偏好", "content": "邮件确认"},
                )
            ]
        )
        self.mid = self.app.store.query_one("SELECT matter_id FROM matters")["matter_id"]

    def test_export_covers_canonical_and_source(self):
        dest = Path(self._tmp.name) / "backup1"
        manifest = self.bk.export_backup(dest)
        self.assertGreater(manifest["canonical"]["raw_sources"], 0)
        self.assertGreater(manifest["canonical"]["matters"], 0)
        self.assertGreater(manifest["canonical"]["reminders"], 0)
        self.assertGreater(manifest["canonical"]["knowledge"], 0)
        self.assertTrue((dest / "raw_sources.json").exists())
        self.assertTrue((dest / "manifest.json").exists())
        # source text is in the backup
        sources = json.loads((dest / "raw_sources.json").read_text(encoding="utf-8"))
        self.assertTrue(any("李经理" in (s.get("text_content") or "") for s in sources))

    def test_precheck_missing_table(self):
        dest = Path(self._tmp.name) / "backup_bad"
        self.bk.export_backup(dest)
        (dest / "matters.json").unlink()
        check = self.bk.precheck(dest)
        self.assertFalse(check["ok"])
        self.assertIn("matters", check["missing"])

    def test_restore_roundtrip_and_rebuild_derived(self):
        dest = Path(self._tmp.name) / "backup2"
        self.bk.export_backup(dest)

        # wipe derived + some canonical to prove restore
        self.app.store.execute("DELETE FROM capsules")
        self.app.store.execute("DELETE FROM dirty_nodes")
        self.app.store.commit()

        result = self.bk.restore_backup(dest, rebuild_derived=True)
        self.assertIn("matters", result["restored"])
        self.assertTrue(result["rebuilt"])

        # canonical restored
        m = self.app.matter.get(self.mid)
        self.assertIsNotNone(m)
        n_src = self.app.store.query("SELECT COUNT(*) c FROM raw_sources")[0]["c"]
        self.assertGreater(n_src, 0)
        n_rem = self.app.store.query("SELECT COUNT(*) c FROM reminders")[0]["c"]
        self.assertGreater(n_rem, 0)

        # derived rebuilt from canonical
        cap = self.app.summary.capsule.get(self.mid)
        self.assertIsNotNone(cap)
        self.assertFalse(self.app.summary.is_stale(self.mid))

    def test_restore_rejects_incomplete_backup(self):
        dest = Path(self._tmp.name) / "backup3"
        self.bk.export_backup(dest)
        (dest / "op_log.json").unlink()
        with self.assertRaises(RuntimeError):
            self.bk.restore_backup(dest)

    def test_derived_loss_alone_is_recoverable(self):
        self.app.summary.process_dirty()
        self.app.store.execute("DELETE FROM capsules")
        self.app.store.commit()
        self.assertTrue(self.app.summary.is_stale(self.mid))

        rebuilt = self.bk.rebuild_derived()
        self.assertIn(self.mid, rebuilt)
        cap = self.app.summary.capsule.get(self.mid)
        self.assertIsNotNone(cap)
        self.assertFalse(self.app.summary.is_stale(self.mid))

    def test_restore_keeps_source_immutable_content(self):
        dest = Path(self._tmp.name) / "backup4"
        self.bk.export_backup(dest)
        before = self.app.store.query_one(
            "SELECT hash, text_content FROM raw_sources LIMIT 1"
        )
        self.app.store.execute("DELETE FROM raw_sources")
        self.app.store.commit()
        self.bk.restore_backup(dest, rebuild_derived=False)
        after = self.app.store.query_one(
            "SELECT hash, text_content FROM raw_sources LIMIT 1"
        )
        self.assertEqual(before["hash"], after["hash"])
        self.assertEqual(before["text_content"], after["text_content"])


if __name__ == "__main__":
    unittest.main()
