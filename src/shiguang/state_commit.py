# -*- coding: utf-8 -*-
"""state-commit-engine: sole write gate for ledgers.

Invariants:
- op_id idempotent
- success only after durable commit
- correction records old→new and invalidates interpretation
- high-risk ops require confirmation
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .ledgers import EventLedger, MatterLedger, PeopleLedger
from .source_evidence import SourceEvidenceService
from .storage import Store
from .types import (
    ChangeReceipt,
    CommitError,
    LedgerOp,
    OpKind,
    ReminderStatus,
    ValidationReject,
    new_id,
    now_ms,
)


class OpValidator:
    REQUIRED = {
        OpKind.CREATE_MATTER.value: ["title"],
        OpKind.UPDATE_MATTER.value: ["matter_id"],
        OpKind.APPEND_EVENT.value: ["summary"],
        OpKind.UPSERT_PERSON.value: ["name"],
        OpKind.CREATE_REMINDER.value: ["matter_id", "due_at", "title"],
        OpKind.COMPLETE_REMINDER.value: ["reminder_id"],
        OpKind.SNOOZE_REMINDER.value: ["reminder_id", "due_at"],
        OpKind.CANCEL_REMINDER.value: ["reminder_id"],
        OpKind.CORRECT_FIELD.value: ["target_kind", "target_id", "field", "new_value"],
        OpKind.ATTACH_FILE.value: ["matter_id", "filename"],
    }

    def validate(self, op: LedgerOp) -> None:
        if not op.op_id:
            raise ValidationReject("op_id required", op.op_id)
        req = self.REQUIRED.get(op.kind)
        if req is None:
            raise ValidationReject(f"unknown op kind: {op.kind}", op.op_id)
        for key in req:
            if key not in op.payload or op.payload[key] in (None, ""):
                raise ValidationReject(f"{op.kind} missing {key}", op.op_id)
        due = op.payload.get("due_at")
        if op.kind in (OpKind.CREATE_REMINDER.value, OpKind.SNOOZE_REMINDER.value):
            if not isinstance(due, int) or due <= 0:
                raise ValidationReject("due_at must be positive int ms", op.op_id)


class ChangeReceiptWriter:
    def __init__(self, store: Store):
        self.store = store

    def emit(self, receipt: ChangeReceipt) -> str:
        self.store.execute(
            "INSERT INTO change_receipts(receipt_id,commit_id,status,summary,old_to_new,matter_ref,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                receipt.receipt_id,
                receipt.commit_id,
                receipt.status,
                receipt.summary,
                json.dumps(receipt.old_to_new, ensure_ascii=False),
                receipt.matter_ref,
                receipt.created_at,
            ),
        )
        self.store.commit()
        return receipt.receipt_id


class CorrectionApplier:
    """Invalidates old interpretation; updates current state; never mutates Source."""

    def __init__(self, store: Store, matter: MatterLedger, source: SourceEvidenceService):
        self.store = store
        self.matter = matter
        self.source = source

    def apply(self, op: LedgerOp) -> dict:
        p = op.payload
        target_kind = p["target_kind"]
        target_id = p["target_id"]
        field = p["field"]
        new_value = p["new_value"]
        old_value = p.get("old_value")
        interp_id = p.get("interp_id")

        if old_value is None:
            if target_kind == "matter":
                m = self.matter.get(target_id)
                if m:
                    if field in m.get("fields", {}):
                        old_value = m["fields"].get(field)
                    else:
                        old_value = m.get(field)
            elif target_kind == "reminder":
                row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (target_id,))
                old_value = row.get(field) if row else None

        correction_id = new_id("corr")
        self.store.execute(
            "INSERT INTO corrections(correction_id,target_kind,target_id,field,old_value,new_value,source_id,interp_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                correction_id,
                target_kind,
                target_id,
                field,
                None if old_value is None else str(old_value),
                str(new_value),
                op.source_ref,
                interp_id,
                now_ms(),
            ),
        )
        if interp_id:
            self.source.mark_interpretation_invalid(interp_id)

        changes = [{"field": field, "old": old_value, "new": new_value, "correction_id": correction_id}]
        if target_kind == "matter":
            self.matter.update_fields(target_id, {field: new_value})
        elif target_kind == "reminder":
            self.store.execute(
                f"UPDATE reminders SET {field}=?, updated_at=? WHERE reminder_id=?",
                (new_value, now_ms(), target_id),
            )
            self.store.commit()
        return {"correction_id": correction_id, "old": old_value, "new": new_value, "changes": changes}


class PatchCommitter:
    def __init__(
        self,
        store: Store,
        matter: MatterLedger,
        event: EventLedger,
        people: PeopleLedger,
    ):
        self.store = store
        self.matter = matter
        self.event = event
        self.people = people

    def apply_op(self, op: LedgerOp) -> dict:
        p = op.payload
        kind = op.kind
        changes: list[dict] = []
        matter_id = op.matter_ref or p.get("matter_id")

        if kind == OpKind.CREATE_MATTER.value:
            mid = self.matter.create(
                title=p["title"],
                status=p.get("status", "OPEN"),
                next_action=p.get("next_action", ""),
                due_at=p.get("due_at"),
                owner_person_id=p.get("owner_person_id"),
                parent_matter_id=p.get("parent_matter_id"),
                fields=p.get("fields", {}),
                matter_id=p.get("matter_id"),
            )
            changes.append({"field": "matter_id", "old": None, "new": mid})
            matter_id = mid
        elif kind == OpKind.UPDATE_MATTER.value:
            result = self.matter.update_fields(
                p["matter_id"],
                p.get("fields", {}),
                next_action=p.get("next_action"),
                due_at=p["due_at"] if "due_at" in p else ...,
                status=p.get("status"),
            )
            changes.extend(result["changes"])
            matter_id = p["matter_id"]
        elif kind == OpKind.APPEND_EVENT.value:
            eid = self.event.append(
                event_type=p.get("event_type", "note"),
                summary=p["summary"],
                matter_id=matter_id,
                people=p.get("people", []),
                source_id=op.source_ref,
                payload=p.get("payload", {}),
            )
            changes.append({"field": "event_id", "old": None, "new": eid})
        elif kind == OpKind.UPSERT_PERSON.value:
            pid = self.people.upsert(
                name=p["name"],
                org=p.get("org", ""),
                role=p.get("role", ""),
                tags=p.get("tags", []),
            )
            changes.append({"field": "person_id", "old": None, "new": pid})
        elif kind == OpKind.CREATE_REMINDER.value:
            rid = self._create_reminder(p)
            changes.append({"field": "reminder_id", "old": None, "new": rid})
            matter_id = p["matter_id"]
        elif kind == OpKind.COMPLETE_REMINDER.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            self.store.execute(
                "UPDATE reminders SET status=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.COMPLETED.value, now_ms(), rid),
            )
            self.store.commit()
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.COMPLETED.value})
            matter_id = row["matter_id"]
            # durable complete must not write matter directly — only reminder state here.
        elif kind == OpKind.SNOOZE_REMINDER.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            self.store.execute(
                "UPDATE reminders SET status=?, due_at=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.SNOOZED.value, p["due_at"], now_ms(), rid),
            )
            self.store.commit()
            changes.append({"field": "due_at", "old": row["due_at"], "new": p["due_at"]})
            matter_id = row["matter_id"]
        elif kind == OpKind.CANCEL_REMINDER.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            self.store.execute(
                "UPDATE reminders SET status=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.CANCELLED.value, now_ms(), rid),
            )
            self.store.commit()
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.CANCELLED.value})
            matter_id = row["matter_id"]
        elif kind == OpKind.ATTACH_FILE.value:
            fid = new_id("file")
            fields = {}
            m = self.matter.get(p["matter_id"])
            if m:
                fields = m.get("fields", {})
            files = list(fields.get("files") or [])
            files.append({"file_id": fid, "filename": p["filename"], "source_id": op.source_ref})
            self.matter.update_fields(p["matter_id"], {"files": files})
            changes.append({"field": "file_id", "old": None, "new": fid})
            matter_id = p["matter_id"]
        else:
            raise ValidationReject(f"unhandled op kind {kind}", op.op_id)

        return {"changes": changes, "matter_id": matter_id}

    def _create_reminder(self, p: dict) -> str:
        rid = new_id("rem")
        now = now_ms()
        collapse = p.get("collapse_key") or f"{p['matter_id']}:{p['title']}"
        self.store.execute(
            "INSERT INTO reminders(reminder_id,matter_id,title,body,due_at,status,fire_count,last_fired_at,collapse_key,next_action,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,0,NULL,?,?,?,?)",
            (
                rid,
                p["matter_id"],
                p["title"],
                p.get("body", ""),
                p["due_at"],
                ReminderStatus.SCHEDULED.value,
                collapse,
                p.get("next_action", ""),
                now,
                now,
            ),
        )
        self.store.commit()
        return rid


class StateCommitEngine:
    def __init__(self, store: Store, source: SourceEvidenceService):
        self.store = store
        self.source = source
        self.matter = MatterLedger(store)
        self.event = EventLedger(store)
        self.people = PeopleLedger(store)
        self.validator = OpValidator()
        self.receipts = ChangeReceiptWriter(store)
        self.corrections = CorrectionApplier(store, self.matter, source)
        self.patcher = PatchCommitter(store, self.matter, self.event, self.people)

    def is_duplicate(self, op_id: str) -> Optional[dict]:
        return self.store.query_one("SELECT * FROM op_log WHERE op_id=?", (op_id,))

    def commit_ops(self, ops: list[LedgerOp], *, require_confirm: bool = False) -> ChangeReceipt:
        if require_confirm and any(o.risk == "high" for o in ops):
            raise CommitError("HIGH_RISK_CONFIRM_REQUIRED")

        applied: list[str] = []
        all_changes: list[dict] = []
        matter_ref = None
        duplicates: list[str] = []
        pending: list[LedgerOp] = []

        for op in ops:
            self.validator.validate(op)
            if self.is_duplicate(op.op_id):
                duplicates.append(op.op_id)
                continue
            pending.append(op)

        if not pending and duplicates:
            receipt = ChangeReceipt(
                receipt_id=new_id("rcpt"),
                commit_id="dup",
                op_ids=duplicates,
                status="DUPLICATE",
                summary="重复提交，已忽略",
                old_to_new=[],
            )
            self.receipts.emit(receipt)
            return receipt

        commit_id = new_id("commit")
        try:
            with self.store.transaction():
                for op in pending:
                    if op.kind == OpKind.CORRECT_FIELD.value:
                        result = self.corrections.apply(op)
                    else:
                        result = self.patcher.apply_op(op)
                    changes = result.get("changes", [])
                    all_changes.extend(changes)
                    matter_ref = result.get("matter_id") or matter_ref or op.matter_ref
                    self.store.execute(
                        "INSERT INTO op_log(op_id,kind,payload,result,commit_id,created_at) VALUES(?,?,?,?,?,?)",
                        (
                            op.op_id,
                            op.kind,
                            json.dumps(op.payload, ensure_ascii=False),
                            "COMMITTED",
                            commit_id,
                            now_ms(),
                        ),
                    )
                    applied.append(op.op_id)
                self.store.execute(
                    "INSERT INTO commits(commit_id,op_ids,receipt_id,created_at) VALUES(?,?,?,?)",
                    (commit_id, json.dumps(applied), None, now_ms()),
                )
        except Exception as e:
            # transaction rolled back; mark nothing as committed
            raise CommitError(str(e)) from e

        # dirty tracking for summary system
        if matter_ref:
            self.store.execute(
                "INSERT OR REPLACE INTO dirty_nodes(node_id,node_kind,marked_at) VALUES(?,?,?)",
                (matter_ref, "matter", now_ms()),
            )
            self.store.commit()

        summary = self._summarize(all_changes, duplicates)
        receipt = ChangeReceipt(
            receipt_id=new_id("rcpt"),
            commit_id=commit_id,
            op_ids=applied + duplicates,
            status="COMMITTED",
            summary=summary,
            old_to_new=all_changes,
            matter_ref=matter_ref,
        )
        self.receipts.emit(receipt)
        self.store.execute("UPDATE commits SET receipt_id=? WHERE commit_id=?", (receipt.receipt_id, commit_id))
        self.store.commit()
        return receipt

    def _summarize(self, changes: list[dict], duplicates: list[str]) -> str:
        if not changes and duplicates:
            return "重复提交，已忽略"
        parts = []
        for c in changes[:8]:
            parts.append(f"{c.get('field')}: {c.get('old')} → {c.get('new')}")
        if len(changes) > 8:
            parts.append(f"... 共 {len(changes)} 处变更")
        return "已保存：" + "；".join(parts) if parts else "已保存"
