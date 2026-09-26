# -*- coding: utf-8 -*-
"""P1 slice facades — all Canonical writes go through State/Commit Ops.

Matter tree / archive / knowledge must not bypass the unique write path.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .ledgers import MatterLedger
from .storage import Store
from .types import LedgerOp, OpKind, new_id, now_ms


class P1WriteBridge:
    """Produces LedgerOps and commits them via StateCommitEngine."""

    def __init__(self, commit_ops: Callable[[list[LedgerOp]], Any]):
        self._commit_ops = commit_ops

    def commit(self, ops: list[LedgerOp]):
        return self._commit_ops(ops)


class MatterTree:
    def __init__(self, store: Store, matter: MatterLedger, bridge: Optional[P1WriteBridge] = None):
        self.store = store
        self.matter = matter
        self.bridge = bridge

    def set_parent(self, child_id: str, parent_id: Optional[str]) -> dict:
        if not self.bridge:
            raise RuntimeError("MatterTree.set_parent requires State/Commit bridge")
        op = LedgerOp(
            op_id=new_id("op"),
            kind=OpKind.SET_MATTER_PARENT.value,
            payload={"matter_id": child_id, "parent_matter_id": parent_id},
            matter_ref=child_id,
            actor="p1_tree",
        )
        receipt = self.bridge.commit([op])
        return {"receipt": receipt, "matter_id": child_id, "parent_matter_id": parent_id}

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
    def __init__(self, store: Store, matter: MatterLedger, bridge: Optional[P1WriteBridge] = None):
        self.store = store
        self.matter = matter
        self.bridge = bridge

    def archive(self, matter_id: str, *, mini_capsule: Optional[dict] = None) -> dict:
        if not self.bridge:
            raise RuntimeError("ArchiveLedger.archive requires State/Commit bridge")
        op = LedgerOp(
            op_id=new_id("op"),
            kind=OpKind.ARCHIVE_MATTER.value,
            payload={"matter_id": matter_id, "mini_capsule": mini_capsule},
            matter_ref=matter_id,
            actor="p1_archive",
        )
        receipt = self.bridge.commit([op])
        m = self.matter.get(matter_id)
        arch = (m.get("fields") or {}).get("archive") if m else None
        return {"receipt": receipt, "archive": arch}

    def mini_capsule(self, matter_id: str) -> Optional[dict]:
        """Archive Capsule only — safe for daily context (no full history)."""
        m = self.matter.get(matter_id)
        if not m or m.get("status") != "ARCHIVED":
            return None
        arch = (m.get("fields") or {}).get("archive") or {}
        return arch.get("mini_capsule")

    def recall(self, keyword: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters WHERE status='ARCHIVED'")
        out = []
        kw = (keyword or "").strip()
        for r in rows:
            fields = json.loads(r["fields"])
            arch = fields.get("archive") or {}
            mini = arch.get("mini_capsule") or {}
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

    def drill_down(self, matter_id: str) -> dict:
        """Full Matter + Events + Source from archive pointer. Archive ≠ delete."""
        m = self.matter.get(matter_id)
        if not m:
            raise KeyError(matter_id)
        events = [
            dict(r)
            for r in self.store.query(
                "SELECT * FROM events WHERE matter_id=? ORDER BY created_at", (matter_id,)
            )
        ]
        for e in events:
            e["people"] = json.loads(e.get("people") or "[]")
            e["payload"] = json.loads(e.get("payload") or "{}")
        source_ids = sorted({e.get("source_id") for e in events if e.get("source_id")})
        sources = []
        for sid in source_ids:
            row = self.store.query_one("SELECT * FROM raw_sources WHERE source_id=?", (sid,))
            if row:
                src = dict(row)
                # do not dump full text into the drill-down card; pointer + meta only
                src.pop("text_content", None)
                sources.append(src)
        fields = m.get("fields") or {}
        arch = fields.get("archive") or {}
        return {
            "matter": {k: v for k, v in m.items() if k != "fields"},
            "fields": fields,
            "mini_capsule": arch.get("mini_capsule"),
            "pointer": arch.get("pointer") or f"matter:{matter_id}",
            "events": events,
            "sources": sources,
            "reminders": [
                dict(r)
                for r in self.store.query(
                    "SELECT reminder_id,title,due_at,status FROM reminders WHERE matter_id=?",
                    (matter_id,),
                )
            ],
        }


class KnowledgeLedger:
    """Stable knowledge. Content is the fact; Source stays in Source & Evidence by ref."""

    def __init__(self, store: Store, bridge: Optional[P1WriteBridge] = None):
        self.store = store
        self.bridge = bridge

    def upsert(self, *, topic: str, content: str, source_id: Optional[str] = None) -> dict:
        if not self.bridge:
            raise RuntimeError("KnowledgeLedger.upsert requires State/Commit bridge")
        op = LedgerOp(
            op_id=new_id("op"),
            kind=OpKind.UPSERT_KNOWLEDGE.value,
            payload={"topic": topic, "content": content},
            source_ref=source_id,
            actor="p1_knowledge",
        )
        receipt = self.bridge.commit([op])
        row = self.store.query_one("SELECT knowledge_id FROM knowledge WHERE topic=?", (topic,))
        return {"receipt": receipt, "knowledge_id": row["knowledge_id"] if row else None}

    def get(self, *, topic: Optional[str] = None, knowledge_id: Optional[str] = None) -> Optional[dict]:
        if knowledge_id:
            row = self.store.query_one("SELECT * FROM knowledge WHERE knowledge_id=?", (knowledge_id,))
        elif topic:
            row = self.store.query_one("SELECT * FROM knowledge WHERE topic=?", (topic,))
        else:
            return None
        return dict(row) if row else None

    def list(self) -> list[dict]:
        return [dict(r) for r in self.store.query("SELECT * FROM knowledge ORDER BY created_at")]

    def search(self, keyword: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM knowledge")
        return [dict(r) for r in rows if keyword in (r["topic"] + r["content"])]

    def source_pointer(self, knowledge_id: str) -> Optional[str]:
        """Return source_id if linked — never a copy of source text."""
        row = self.get(knowledge_id=knowledge_id)
        return row.get("source_id") if row else None


class FileLedger:
    """File semantics + links (matter / product). Bytes & hash live in Source & Evidence."""

    def __init__(self, store: Store, bridge: Optional[P1WriteBridge] = None):
        self.store = store
        self.bridge = bridge

    def attach(
        self,
        *,
        matter_id: str,
        filename: str,
        source_id: Optional[str] = None,
        file_type: str = "",
        product_ref: Optional[str] = None,
    ) -> dict:
        if not self.bridge:
            raise RuntimeError("FileLedger.attach requires State/Commit bridge")
        op = LedgerOp(
            op_id=new_id("op"),
            kind=OpKind.ATTACH_FILE.value,
            payload={
                "matter_id": matter_id,
                "filename": filename,
                "file_type": file_type,
                "product_ref": product_ref,
            },
            source_ref=source_id,
            actor="p1_file",
        )
        receipt = self.bridge.commit([op])
        row = self.store.query_one(
            "SELECT file_id FROM files WHERE matter_id=? AND filename=? ORDER BY created_at DESC LIMIT 1",
            (matter_id, filename),
        )
        return {
            "receipt": receipt,
            "file_id": row["file_id"] if row else None,
            "source_id": source_id,
        }

    def list_for_matter(self, matter_id: str) -> list[dict]:
        rows = self.store.query(
            "SELECT * FROM files WHERE matter_id=? ORDER BY created_at", (matter_id,)
        )
        return [dict(r) for r in rows]

    def list_for_product(self, product_ref: str) -> list[dict]:
        rows = self.store.query(
            "SELECT * FROM files WHERE product_ref=? ORDER BY created_at", (product_ref,)
        )
        return [dict(r) for r in rows]

    def get(self, file_id: str) -> Optional[dict]:
        row = self.store.query_one("SELECT * FROM files WHERE file_id=?", (file_id,))
        return dict(row) if row else None

    def source_pointer(self, file_id: str) -> Optional[str]:
        """Return source_id if linked — never bytes, never a source text copy."""
        row = self.get(file_id)
        return row.get("source_id") if row else None
