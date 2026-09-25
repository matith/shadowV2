# -*- coding: utf-8 -*-
"""projection-layer: table-projection (Local Inspector)."""
from __future__ import annotations

import json
from typing import Any, Optional

from .ledgers import MatterLedger
from .state_commit import StateCommitEngine
from .storage import Store
from .types import LedgerOp, OpKind, new_id


# Chinese display name ↔ English field id map (versioned with product)
FIELD_LABELS = {
    "matter_id": "事项ID",
    "title": "标题",
    "status": "状态",
    "due_at": "截止",
    "next_action": "下一步",
    "owner_person_id": "负责人",
    "parent_matter_id": "父事项",
    "revision": "版本",
    "updated_at": "更新时间",
}


class TableProjection:
    def __init__(self, store: Store, matter: MatterLedger, commit: StateCommitEngine):
        self.store = store
        self.matter = matter
        self.commit = commit

    def render_default_my_matters(self) -> dict:
        rows = []
        for m in self.matter.list_open():
            rows.append(
                {
                    "matter_id": m["matter_id"],
                    "title": m["title"],
                    "status": m["status"],
                    "due_at": m.get("due_at"),
                    "next_action": m.get("next_action"),
                    "revision": m.get("revision"),
                    "updated_at": m.get("updated_at"),
                }
            )
        return {
            "view": "我的事项",
            "columns": [
                {"id": "title", "label": FIELD_LABELS["title"]},
                {"id": "status", "label": FIELD_LABELS["status"]},
                {"id": "due_at", "label": FIELD_LABELS["due_at"]},
                {"id": "next_action", "label": FIELD_LABELS["next_action"]},
                {"id": "revision", "label": FIELD_LABELS["revision"]},
            ],
            "rows": rows,
        }

    def apply_cell_edit(self, matter_id: str, field_id: str, value: Any) -> dict:
        """External edit → LedgerOp → State/Commit (with receipt)."""
        op = LedgerOp(
            op_id=new_id("op"),
            kind=OpKind.UPDATE_MATTER.value,
            payload={"matter_id": matter_id, "fields": {field_id: value}},
            matter_ref=matter_id,
            actor="projection",
        )
        receipt = self.commit.commit_ops([op])
        return {"receipt": receipt, "field_id": field_id, "value": value}

    def expand_children(self, matter_id: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters WHERE parent_matter_id=?", (matter_id,))
        out = []
        for r in rows:
            item = dict(r)
            item["fields"] = json.loads(r["fields"])
            out.append(item)
        return out

    def open_evidence(self, matter_id: str) -> list[dict]:
        events = self.store.query("SELECT * FROM events WHERE matter_id=?", (matter_id,))
        out = []
        for e in events:
            if e.get("source_id"):
                out.append({"event_id": e["event_id"], "source_id": e["source_id"], "summary": e["summary"]})
        return out

    def export_readonly(self) -> dict:
        rows = self.store.query("SELECT * FROM matters ORDER BY updated_at DESC")
        out = []
        for r in rows:
            item = dict(r)
            item["fields"] = json.loads(r["fields"])
            out.append(item)
        return {"readonly": True, "matters": out}
