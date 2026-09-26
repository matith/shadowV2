# -*- coding: utf-8 -*-
"""personal-ledger-core sub-blackboxes: matter / event / people.

Write discipline (dec-source-write):
- These methods only mutate. They never call Store.commit().
- Canonical business mutations must run inside State/Commit Engine transaction.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .storage import Store
from .types import MatterStatus, now_ms


class MatterLedger:
    def __init__(self, store: Store):
        self.store = store

    def create(
        self,
        *,
        title: str,
        status: str = MatterStatus.OPEN.value,
        next_action: str = "",
        due_at: Optional[int] = None,
        owner_person_id: Optional[str] = None,
        parent_matter_id: Optional[str] = None,
        fields: Optional[dict] = None,
        matter_id: Optional[str] = None,
    ) -> str:
        from .types import new_id

        self.store.require_transaction("MatterLedger.create")
        mid = matter_id or new_id("matter")
        now = now_ms()
        self.store.execute(
            "INSERT INTO matters(matter_id,title,status,priority,due_at,owner_person_id,parent_matter_id,next_action,fields,revision,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                mid,
                title,
                status,
                (fields or {}).get("priority"),
                due_at,
                owner_person_id,
                parent_matter_id,
                next_action,
                json.dumps(fields or {}, ensure_ascii=False),
                1,
                now,
                now,
            ),
        )
        return mid

    def get(self, matter_id: str) -> Optional[dict]:
        row = self.store.query_one("SELECT * FROM matters WHERE matter_id=?", (matter_id,))
        if not row:
            return None
        row = dict(row)
        row["fields"] = json.loads(row["fields"])
        return row

    def update_fields(
        self,
        matter_id: str,
        patch: dict,
        *,
        next_action: Optional[str] = None,
        due_at: Any = ...,
        status: Optional[str] = None,
    ) -> dict:
        """Update current state fields. Returns old_to_new pairs."""
        self.store.require_transaction("MatterLedger.update_fields")
        old = self.get(matter_id)
        if not old:
            raise KeyError(matter_id)
        changes = []
        fields = dict(old.get("fields") or {})
        patch = dict(patch or {})
        if "due_at" in patch and due_at is ...:
            due_at = patch.pop("due_at")
        if "status" in patch and status is None:
            status = patch.pop("status")
        if "next_action" in patch and next_action is None:
            next_action = patch.pop("next_action")
        for k, v in patch.items():
            prev = fields.get(k)
            if prev != v:
                changes.append({"field": k, "old": prev, "new": v})
            if v is None:
                fields.pop(k, None)
            else:
                fields[k] = v
        status_val = old["status"]
        if status is not None and status != old["status"]:
            changes.append({"field": "status", "old": old["status"], "new": status})
            status_val = status
        next_action_val = old["next_action"]
        if next_action is not None and next_action != old["next_action"]:
            changes.append({"field": "next_action", "old": old["next_action"], "new": next_action})
            next_action_val = next_action
        due_val = old["due_at"]
        if due_at is not ... and due_at != old["due_at"]:
            changes.append({"field": "due_at", "old": old["due_at"], "new": due_at})
            due_val = due_at
            fields["due_at"] = due_at
        self.store.execute(
            "UPDATE matters SET status=?, next_action=?, due_at=?, fields=?, revision=revision+1, updated_at=? WHERE matter_id=?",
            (status_val, next_action_val, due_val, json.dumps(fields, ensure_ascii=False), now_ms(), matter_id),
        )
        return {"matter_id": matter_id, "changes": changes, "revision": (old.get("revision") or 1) + 1}

    def set_parent(self, matter_id: str, parent_matter_id: Optional[str]) -> dict:
        self.store.require_transaction("MatterLedger.set_parent")
        old = self.get(matter_id)
        if not old:
            raise KeyError(matter_id)
        prev = old.get("parent_matter_id")
        self.store.execute(
            "UPDATE matters SET parent_matter_id=?, revision=revision+1, updated_at=? WHERE matter_id=?",
            (parent_matter_id, now_ms(), matter_id),
        )
        return {
            "matter_id": matter_id,
            "changes": [{"field": "parent_matter_id", "old": prev, "new": parent_matter_id}],
        }

    def find_similar(self, *, title: str, person_name: Optional[str] = None, due_at: Optional[int] = None) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters WHERE status != 'ARCHIVED'")
        hits = []
        title_l = title.strip().lower()
        for r in rows:
            score = 0
            rt = (r["title"] or "").lower()
            if title_l and (title_l in rt or rt in title_l):
                score += 3
            t_tokens = set(title.replace("，", " ").replace("。", " ").split())
            r_tokens = set((r["title"] or "").replace("，", " ").replace("。", " ").split())
            score += len(t_tokens & r_tokens)
            if person_name:
                fields = json.loads(r["fields"])
                people = " ".join(fields.get("people_names") or []) + " " + (r.get("next_action") or "")
                if person_name in people:
                    score += 2
            if score >= 2:
                item = dict(r)
                item["fields"] = json.loads(r["fields"])
                item["score"] = score
                hits.append(item)
        hits.sort(key=lambda x: -x["score"])
        return hits[:5]

    def list_open(self) -> list[dict]:
        rows = self.store.query(
            "SELECT * FROM matters WHERE status IN ('OPEN','IN_PROGRESS','WAITING') ORDER BY updated_at DESC"
        )
        out = []
        for r in rows:
            item = dict(r)
            item["fields"] = json.loads(r["fields"])
            out.append(item)
        return out

    def find_by_keyword(self, keyword: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM matters")
        out = []
        kw = keyword.strip()
        for r in rows:
            blob = f"{r['title']} {r.get('next_action') or ''} {r['fields']}"
            if kw and kw in blob:
                item = dict(r)
                item["fields"] = json.loads(r["fields"])
                out.append(item)
        return out


class EventLedger:
    def __init__(self, store: Store):
        self.store = store

    def append(
        self,
        *,
        event_type: str,
        summary: str,
        matter_id: Optional[str] = None,
        people: Optional[list] = None,
        source_id: Optional[str] = None,
        payload: Optional[dict] = None,
        event_id: Optional[str] = None,
    ) -> str:
        from .types import new_id

        self.store.require_transaction("EventLedger.append")
        eid = event_id or new_id("evt")
        self.store.execute(
            "INSERT INTO events(event_id,matter_id,event_type,summary,people,source_id,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",
            (
                eid,
                matter_id,
                event_type,
                summary,
                json.dumps(people or [], ensure_ascii=False),
                source_id,
                now_ms(),
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        return eid

    def list_for_matter(self, matter_id: str) -> list[dict]:
        rows = self.store.query("SELECT * FROM events WHERE matter_id=? ORDER BY created_at", (matter_id,))
        out = []
        for r in rows:
            item = dict(r)
            item["people"] = json.loads(r["people"])
            item["payload"] = json.loads(r["payload"])
            out.append(item)
        return out


class PeopleLedger:
    def __init__(self, store: Store):
        self.store = store

    def upsert(
        self, *, name: str, person_id: Optional[str] = None, org: str = "", role: str = "", tags: Optional[list] = None
    ) -> str:
        from .types import new_id

        self.store.require_transaction("PeopleLedger.upsert")
        existing = self.store.query_one("SELECT person_id FROM people WHERE name=?", (name,))
        pid = person_id or (existing["person_id"] if existing else new_id("person"))
        now = now_ms()
        if existing:
            self.store.execute(
                "UPDATE people SET org=?, role=?, tags=?, updated_at=? WHERE person_id=?",
                (org, role, json.dumps(tags or [], ensure_ascii=False), now, pid),
            )
        else:
            self.store.execute(
                "INSERT INTO people(person_id,name,org,role,tags,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (pid, name, org, role, json.dumps(tags or [], ensure_ascii=False), now, now),
            )
        return pid

    def get(self, person_id: str) -> Optional[dict]:
        return self.store.query_one("SELECT * FROM people WHERE person_id=?", (person_id,))

    def find_by_name(self, name: str) -> Optional[dict]:
        return self.store.query_one("SELECT * FROM people WHERE name=?", (name,))
