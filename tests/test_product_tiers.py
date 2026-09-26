# -*- coding: utf-8 -*-
"""Product ledger + HOT/WARM/COLD memory tiers."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shiguang.durable_task import FakeClock  # noqa: E402
from shiguang.p1_slices import MemoryTier, ProductLedger  # noqa: E402
from shiguang.runtime import ShiGuangApp  # noqa: E402
from shiguang.types import LedgerOp, OpKind  # noqa: E402

T0 = 1_758_806_400_000


class TestProductAndTiers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.clock = FakeClock(T0)
        self.app = ShiGuangApp.open(
            ROOT, Path(self._tmp.name) / "pt.sqlite", clock=self.clock
        )
        self.addCleanup(self.app.close)
        self.p = ProductLedger(self.app.store, self.app.p1_bridge)
        self.tier = MemoryTier(self.app.store, self.clock)

    def test_product_upsert_and_search(self):
        r = self.p.upsert(
            product_id="cloud_vpn",
            name="云联网",
            kind="product",
            summary="政企云联网，按带宽计费",
            params={"bandwidth": "100M", "price": "面议"},
            source_id=None,
        )
        self.assertEqual(r["receipt"].status, "COMMITTED")
        got = self.p.get("cloud_vpn")
        self.assertIsNotNone(got)
        self.assertEqual(got["meta"]["name"], "云联网")
        self.assertEqual(got["meta"]["params"]["bandwidth"], "100M")
        hits = self.p.search("带宽")
        self.assertTrue(any(h["meta"]["product_id"] == "cloud_vpn" for h in hits))
        listed = self.p.list()
        self.assertTrue(any(x["meta"]["product_id"] == "cloud_vpn" for x in listed))

    def test_product_upsert_is_idempotent_topic(self):
        self.p.upsert(product_id="p1", name="A", summary="v1")
        self.p.upsert(product_id="p1", name="A", summary="v2")
        n = self.app.store.query(
            "SELECT COUNT(*) c FROM knowledge WHERE topic='product:p1'"
        )[0]["c"]
        self.assertEqual(n, 1)
        self.assertEqual(self.p.get("p1")["meta"]["summary"], "v2")

    def test_product_writes_via_commit(self):
        self.p.upsert(product_id="p2", name="B", summary="s")
        kinds = {r["kind"] for r in self.app.store.query("SELECT kind FROM op_log")}
        self.assertIn("upsert_knowledge", kinds)

    def _stamp(self, mid: str) -> None:
        """Align row timestamps to FakeClock so age-based tiers are testable."""
        self.app.store.execute(
            "UPDATE matters SET created_at=?, updated_at=? WHERE matter_id=?",
            (self.clock.now(), self.clock.now(), mid),
        )
        self.app.store.commit()

    def test_hot_by_recency(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_hot",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "新事项", "matter_id": "m_hot", "force_new": True},
                )
            ]
        )
        self._stamp("m_hot")
        self.assertEqual(self.tier.tier_of("m_hot"), "HOT")

    def test_warm_then_cold_by_age(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_age",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "旧事项", "matter_id": "m_age", "force_new": True},
                )
            ]
        )
        self._stamp("m_age")
        self.assertEqual(self.tier.tier_of("m_age"), "HOT")
        self.clock.advance_hours(24 * 10)  # 10 days
        self.assertEqual(self.tier.tier_of("m_age"), "WARM")
        self.clock.advance_hours(24 * 25)  # 35 days total
        self.assertEqual(self.tier.tier_of("m_age"), "COLD")

    def test_long_term_stays_hot_even_when_old(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_lt",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": "长期重点",
                        "matter_id": "m_lt",
                        "fields": {"long_term": True},
                        "force_new": True,
                    },
                )
            ]
        )
        self._stamp("m_lt")
        self.clock.advance_hours(24 * 400)
        self.assertEqual(self.tier.tier_of("m_lt"), "HOT")
        self.assertTrue(self.tier.ensure_visible("m_lt"))

    def test_cold_is_demoted_not_deleted(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_cold",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "将变冷", "matter_id": "m_cold", "force_new": True},
                )
            ]
        )
        self._stamp("m_cold")
        self.clock.advance_hours(24 * 40)
        self.assertEqual(self.tier.tier_of("m_cold"), "COLD")
        # still exists
        self.assertTrue(self.tier.ensure_visible("m_cold"))
        self.assertIsNotNone(self.app.matter.get("m_cold"))

    def test_archived_is_cold(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_arch",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "归档了", "matter_id": "m_arch", "force_new": True},
                )
            ]
        )
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="arch_op",
                    kind=OpKind.ARCHIVE_MATTER.value,
                    payload={"matter_id": "m_arch"},
                    matter_ref="m_arch",
                )
            ]
        )
        self.assertEqual(self.tier.tier_of("m_arch"), "COLD")

    def test_classify_all(self):
        self.app.commit.commit_ops(
            [
                LedgerOp(
                    op_id="m_c1",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={"title": "A", "matter_id": "m_c1", "force_new": True},
                ),
                LedgerOp(
                    op_id="m_c2",
                    kind=OpKind.CREATE_MATTER.value,
                    payload={
                        "title": "B",
                        "matter_id": "m_c2",
                        "fields": {"pin": True},
                        "force_new": True,
                    },
                ),
            ]
        )
        rows = {r["matter_id"]: r for r in self.tier.classify_all()}
        self.assertEqual(rows["m_c1"]["tier"], "HOT")
        self.assertEqual(rows["m_c2"]["tier"], "HOT")


if __name__ == "__main__":
    unittest.main()
