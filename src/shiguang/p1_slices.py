# -*- coding: utf-8 -*-
"""P1 slice: matter tree + archive mini-capsule + knowledge ledger (minimal).

Extends P0 without breaking its regression.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .ledgers import MatterLedger
from .storage import Store
from .types import OpKind, new_id, now_ms


class MatterTree:
    def __init__(self, store: Store, matter: MatterLedger):
        self.store = store
        self.matter = matter

    def set_parent(self, child_id: str, parent_id: Optional[str]) -> None:
        self.store.execute(
            "UPDATE matters SET parent_matter_id=?, revision=revision+1, updated_at=? WHERE matter_id=?",
            (parent_id, now_ms(), child_id),
        )
        self.store.commit()

    def children(self, matter_id: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters WHERE parent_matter_id=?", (matter_id,))
        out = []
        for r in rows:
            item = dict(r)
            item["fields"] = json.loads(r["fields"])
            out.append(item)
        return out

    def expand_tree(self, matter_id: str, *, depth: int = 3) -> dict:
        def walk(mid: str, d: int) -> dict:
            m = self.matter.get(mid)
            if not m:
                return {"matter_id": mid, "missing": True, "children": []}
            node = {
                "matter_id": m["matter_id"],
                "title": m["title"],
                "status": m["status"],
                "next_action": m.get("next_action"),
                "children": [],
            }
            if d > 0:
                for c in self.children(mid):
                    node["children"].append(walk(c["matter_id"], d - 1))
            return node

        return walk(matter_id, depth)


class ArchiveLedger:
    """Archive keeps title/state/capsule/pointer; discoverable on recall."""

    def __init__(self, store: Store, matter: MatterLedger):
        self.store = store
        self.matter = matter

    def archive(self, matter_id: str, *, mini_capsule: Optional[dict] = None) -> dict:
        m = self.matter.get(matter_id)
        if not m:
            raise KeyError(matter_id)
        cap = mini_capsule or {
            "goal": m["title"],
            "current": m.get("next_action") or m.get("status"),
            "open_items": [],
        }
        fields = dict(m.get("fields") or {})
        fields["archive"] = {
            "archived_at": now_ms(),
            "title": m["title"],
            "status": m["status"],
            "mini_capsule": cap,
            "pointer": f"matter:{matter_id}",
        }
        self.matter.update_fields(matter_id, fields, status="ARCHIVED")
        return fields["archive"]

    def recall(self, keyword: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters WHERE status='ARCHIVED'")
        out = []
        kw = (keyword or "").strip()
        for r in rows:
            fields = json.loads(r["fields"])
            arch = fields.get("archive") or {}
            blob = f"{r['title']} {json.dumps(arch, ensure_ascii=False)}"
            if not kw or kw in blob:
                out.append(
                    {
                        "matter_id": r["matter_id"],
                        "title": r["title"],
                        "status": r["status"],
                        "mini_capsule": arch.get("mini_capsule"),
                        "pointer": arch.get("pointer"),
                        "archived_at": arch.get("archived_at"),
                    }
                )
        return out


class KnowledgeLedger:
    def __init__(self, store: Store):
        self.store = store

    def upsert(self, *, topic: str, content: str, source_id: Optional[str] = None) -> str:
        existing = self.store.query_one("SELECT knowledge_id FROM knowledge WHERE topic=?", (topic,))
        if existing:
            self.store.execute(
                "UPDATE knowledge SET content=?, source_id=? WHERE knowledge_id=?",
                (content, source_id, existing["knowledge_id"]),
            )
            self.store.commit()
            return existing["knowledge_id"]
        kid = new_id("know")
        self.store.execute(
            "INSERT INTO knowledge(knowledge_id,topic,content,source_id,created_at) VALUES(?,?,?,?,?)",
            (kid, topic, content, source_id, now_ms()),
        )
        self.store.commit()
        return kid

    def search(self, keyword: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM knowledge")
        return [dict(r) for r in rows if keyword in (r["topic"] + r["content"])]
