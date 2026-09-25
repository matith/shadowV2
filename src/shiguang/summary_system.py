# -*- coding: utf-8 -*-
"""summary-system: capsule-store + incremental-reducer + dirty-tracker."""
from __future__ import annotations

import json
from typing import Any, Optional

from .ledgers import EventLedger, MatterLedger
from .storage import Store
from .types import now_ms


class DirtyTracker:
    def __init__(self, store: Store):
        self.store = store

    def mark(self, node_id: str, node_kind: str = "matter") -> None:
        self.store.execute(
            "INSERT OR REPLACE INTO dirty_nodes(node_id,node_kind,marked_at) VALUES(?,?,?)",
            (node_id, node_kind, now_ms()),
        )
        self.store.commit()

    def list_dirty(self) -> list[dict]:
        return self.store.query("SELECT * FROM dirty_nodes")

    def clear(self, node_id: str) -> None:
        self.store.execute("DELETE FROM dirty_nodes WHERE node_id=?", (node_id,))
        self.store.commit()


class IncrementalReducer:
    """old + patch → new; default is incremental, full rewrite only for repair."""

    def reduce(self, old: dict, patch: dict) -> dict:
        out = dict(old or {})
        for k, v in patch.items():
            if v is None:
                out.pop(k, None)
            else:
                out[k] = v
        return out


class CapsuleStore:
    STRUCTURE = ("goal", "current", "recent", "open_items", "files", "evidence")

    def __init__(self, store: Store):
        self.store = store
        self.reducer = IncrementalReducer()

    def get(self, matter_id: str) -> Optional[dict]:
        row = self.store.query_one("SELECT * FROM capsules WHERE matter_id=?", (matter_id,))
        if not row:
            return None
        return {
            "matter_id": row["matter_id"],
            "goal": row["goal"],
            "current": row["current"],
            "recent": json.loads(row["recent"] or "[]"),
            "open_items": json.loads(row["open_items"] or "[]"),
            "files": json.loads(row["files"] or "[]"),
            "evidence": json.loads(row["evidence"] or "[]"),
            "basis_revision": row["basis_revision"],
            "updated_at": row["updated_at"],
        }

    def upsert_incremental(self, matter_id: str, patch: dict, *, basis_revision: int) -> dict:
        old = self.get(matter_id) or {
            "matter_id": matter_id,
            "goal": "",
            "current": "",
            "recent": [],
            "open_items": [],
            "files": [],
            "evidence": [],
            "basis_revision": 0,
        }
        merged = self.reducer.reduce(old, patch)
        self.store.execute(
            "INSERT INTO capsules(matter_id,goal,current,recent,open_items,files,evidence,basis_revision,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(matter_id) DO UPDATE SET goal=excluded.goal,current=excluded.current,recent=excluded.recent,"
            "open_items=excluded.open_items,files=excluded.files,evidence=excluded.evidence,"
            "basis_revision=excluded.basis_revision,updated_at=excluded.updated_at",
            (
                matter_id,
                merged.get("goal") or "",
                merged.get("current") or "",
                json.dumps(merged.get("recent") or [], ensure_ascii=False),
                json.dumps(merged.get("open_items") or [], ensure_ascii=False),
                json.dumps(merged.get("files") or [], ensure_ascii=False),
                json.dumps(merged.get("evidence") or [], ensure_ascii=False),
                basis_revision,
                now_ms(),
            ),
        )
        self.store.commit()
        return self.get(matter_id)


class SummarySystem:
    def __init__(self, store: Store, matter: MatterLedger, event: EventLedger):
        self.store = store
        self.matter = matter
        self.event = event
        self.capsule = CapsuleStore(store)
        self.dirty = DirtyTracker(store)

    def sync_with_matter(self, matter_id: str) -> dict:
        m = self.matter.get(matter_id)
        if not m:
            raise KeyError(matter_id)
        events = self.event.list_for_matter(matter_id)[-5:]
        fields = m.get("fields") or {}
        open_items = []
        if m["status"] not in ("DONE", "ARCHIVED"):
            if m.get("next_action"):
                open_items.append(m["next_action"])
            if m.get("due_at"):
                open_items.append(f"截止：{m['due_at']}")
        patch = {
            "goal": m["title"],
            "current": f"状态 {m['status']}" + (f"；下一步 {m['next_action']}" if m.get("next_action") else ""),
            "recent": [e["summary"] for e in events],
            "open_items": open_items,
            "files": fields.get("files") or [],
            "evidence": fields.get("evidence") or [
                {"source_id": e.get("source_id")} for e in events if e.get("source_id")
            ],
        }
        cap = self.capsule.upsert_incremental(matter_id, patch, basis_revision=m.get("revision") or 1)
        self.dirty.clear(matter_id)
        return cap

    def process_dirty(self) -> list[str]:
        done = []
        for node in self.dirty.list_dirty():
            if node["node_kind"] == "matter":
                self.sync_with_matter(node["node_id"])
                done.append(node["node_id"])
        return done

    def is_stale(self, matter_id: str) -> bool:
        cap = self.capsule.get(matter_id)
        m = self.matter.get(matter_id)
        if not cap or not m:
            return True
        return cap.get("basis_revision") != m.get("revision")
