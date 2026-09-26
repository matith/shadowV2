# -*- coding: utf-8 -*-
"""state-commit-engine: sole write gate for Canonical business state.

Invariants:
- State/Commit Engine owns the transaction boundary (ALL COMMIT or ALL ROLLBACK)
- lower layers mutate only; they never durable-commit mid-batch
- op_id idempotent
- success only after durable commit
- correction uses field whitelist; never f-string column names
- correction invalidates old interpretations
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

# Contract: correctable fields per target_kind. Illegal field → deterministic reject.
CORRECTABLE_FIELDS = {
    "matter": {"due_at", "due_label", "next_action", "status", "title", "priority"},
    "reminder": {"status", "due_at", "title", "body", "next_action"},
}

# Fixed column map — no dynamic SQL identifiers from user/model input.
REMINDER_COLUMNS = {
    "status": "status",
    "due_at": "due_at",
    "title": "title",
    "body": "body",
    "next_action": "next_action",
}

MATTER_TOP_LEVEL = {"due_at", "status", "next_action", "title", "priority"}


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
        OpKind.UPSERT_KNOWLEDGE.value: ["topic", "content"],
        OpKind.SET_MATTER_PARENT.value: ["matter_id"],
        OpKind.ARCHIVE_MATTER.value: ["matter_id"],
        OpKind.MARK_REMINDER_FIRED.value: ["reminder_id"],
        OpKind.MARK_REMINDER_MISSED.value: ["reminder_id"],
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
        if op.kind == OpKind.CORRECT_FIELD.value:
            self._validate_correction(op)

    def _validate_correction(self, op: LedgerOp) -> None:
        p = op.payload
        target_kind = p.get("target_kind")
        field = p.get("field")
        allowed = CORRECTABLE_FIELDS.get(target_kind)
        if allowed is None:
            raise ValidationReject(f"unknown target_kind: {target_kind}", op.op_id)
        if field not in allowed:
            raise ValidationReject(
                f"field not correctable for {target_kind}: {field}", op.op_id
            )


class ChangeReceiptWriter:
    def __init__(self, store: Store):
        self.store = store

    def emit(self, receipt: ChangeReceipt) -> str:
        # receipt is durable proof of a finished commit/reject — allow outside txn
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
        self.store.require_transaction("CorrectionApplier.apply")
        p = op.payload
        target_kind = p["target_kind"]
        target_id = p["target_id"]
        field = p["field"]
        new_value = p["new_value"]
        old_value = p.get("old_value")
        interp_id = p.get("interp_id")

        if field not in CORRECTABLE_FIELDS.get(target_kind, set()):
            raise ValidationReject(f"field not correctable for {target_kind}: {field}", op.op_id)

        if old_value is None:
            if target_kind == "matter":
                m = self.matter.get(target_id)
                if m:
                    if field in (m.get("fields") or {}):
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

        invalidated = []
        if interp_id:
            self.source.mark_interpretation_invalid(interp_id)
            invalidated.append(interp_id)
        # Contract: correction must invalidate prior interpretations for this target
        invalidated.extend(self._invalidate_active_interps(target_kind, target_id))

        changes = [{"field": field, "old": old_value, "new": new_value, "correction_id": correction_id}]
        if target_kind == "matter":
            self.matter.update_fields(target_id, {field: new_value})
            # Matter due correction must move linked active reminders in the same txn,
            # otherwise the old due still fires after the user says "不是周三，是周四".
            if field == "due_at":
                changes.extend(self._reschedule_linked_reminders(target_id, old_value, new_value))
        elif target_kind == "reminder":
            col = REMINDER_COLUMNS[field]
            self.store.execute(
                f"UPDATE reminders SET {col}=?, updated_at=? WHERE reminder_id=?",
                (new_value, now_ms(), target_id),
            )
            if field == "due_at":
                # keep status scannable if it had already slipped into MISSED
                row = self.store.query_one(
                    "SELECT status FROM reminders WHERE reminder_id=?", (target_id,)
                )
                if row and row["status"] == ReminderStatus.MISSED.value:
                    self.store.execute(
                        "UPDATE reminders SET status=?, updated_at=? WHERE reminder_id=?",
                        (ReminderStatus.SCHEDULED.value, now_ms(), target_id),
                    )
        return {
            "correction_id": correction_id,
            "old": old_value,
            "new": new_value,
            "changes": changes,
            "invalidated_interps": invalidated,
        }

    def _reschedule_linked_reminders(self, matter_id: str, old_due: Any, new_due: Any) -> list[dict]:
        """Reschedule active reminders whose due is the corrected time.

        Link rule: same matter + due_at == old semantic time. Only SCHEDULED /
        SNOOZED / MISSED rows move — FIRED/COMPLETED/CANCELLED stay as history.
        """
        try:
            old_due_i = int(old_due) if old_due is not None else None
            new_due_i = int(new_due) if new_due is not None else None
        except (TypeError, ValueError):
            return []
        if old_due_i is None or new_due_i is None or old_due_i == new_due_i:
            return []
        active = (
            ReminderStatus.SCHEDULED.value,
            ReminderStatus.SNOOZED.value,
            ReminderStatus.MISSED.value,
        )
        placeholders = ",".join("?" * len(active))
        rows = self.store.query(
            f"SELECT reminder_id, due_at, title FROM reminders "
            f"WHERE matter_id=? AND due_at=? AND status IN ({placeholders})",
            (matter_id, old_due_i, *active),
        )
        out: list[dict] = []
        for r in rows:
            self.store.execute(
                "UPDATE reminders SET due_at=?, updated_at=? WHERE reminder_id=?",
                (new_due_i, now_ms(), r["reminder_id"]),
            )
            out.append(
                {
                    "field": "reminder.due_at",
                    "old": r["due_at"],
                    "new": new_due_i,
                    "reminder_id": r["reminder_id"],
                    "reason": "correction_reschedule",
                }
            )
        return out

    def _invalidate_active_interps(self, target_kind: str, target_id: str) -> list[str]:
        rows = self.store.query(
            "SELECT interp_id FROM interpretations WHERE status='ACTIVE' AND matter_id=?",
            (target_id,),
        )
        out = []
        for r in rows:
            self.source.mark_interpretation_invalid(r["interp_id"])
            out.append(r["interp_id"])
        # also invalidate by source-linked interps when target is reminder
        if target_kind == "reminder":
            rows2 = self.store.query(
                "SELECT interp_id FROM interpretations WHERE status='ACTIVE' AND kind='reminder'"
            )
            # only those that claim this reminder in fields
            for r in rows2:
                row = self.store.query_one("SELECT fields FROM interpretations WHERE interp_id=?", (r["interp_id"],))
                if row and target_id in (row.get("fields") or ""):
                    self.source.mark_interpretation_invalid(r["interp_id"])
                    out.append(r["interp_id"])
        return out


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
        self.store.require_transaction("PatchCommitter.apply_op")
        p = op.payload
        kind = op.kind
        changes: list[dict] = []
        matter_id = op.matter_ref or p.get("matter_id")

        if kind == OpKind.CREATE_MATTER.value:
            # identity: prefer reuse when similar open matter exists and not forced
            if not p.get("force_new"):
                sims = self.matter.find_similar(title=p["title"], person_name=(p.get("fields") or {}).get("person_name"))
                if sims:
                    mid = sims[0]["matter_id"]
                    result = self.matter.update_fields(
                        mid,
                        p.get("fields") or {},
                        next_action=p.get("next_action") or sims[0].get("next_action"),
                        due_at=p.get("due_at") if p.get("due_at") is not None else ...,
                    )
                    changes.append({"field": "matter_id", "old": None, "new": mid, "reused": True})
                    changes.extend(result["changes"])
                    return {"changes": changes, "matter_id": mid, "reused": True}
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
        elif kind == OpKind.SET_MATTER_PARENT.value:
            result = self.matter.set_parent(p["matter_id"], p.get("parent_matter_id"))
            changes.extend(result["changes"])
            matter_id = p["matter_id"]
        elif kind == OpKind.ARCHIVE_MATTER.value:
            m = self.matter.get(p["matter_id"])
            if not m:
                raise ValidationReject("matter not found", op.op_id)
            mini = p.get("mini_capsule") or {
                "goal": m["title"],
                "current": m.get("next_action") or m.get("status"),
                "open_items": [],
            }
            fields = dict(m.get("fields") or {})
            fields["archive"] = {
                "archived_at": now_ms(),
                "title": m["title"],
                "status": m["status"],
                "mini_capsule": mini,
                "pointer": f"matter:{p['matter_id']}",
            }
            result = self.matter.update_fields(p["matter_id"], fields, status="ARCHIVED")
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
        elif kind == OpKind.UPSERT_KNOWLEDGE.value:
            kid = self._upsert_knowledge(p, op.source_ref)
            changes.append({"field": "knowledge_id", "old": None, "new": kid})
        elif kind == OpKind.CREATE_REMINDER.value:
            rid, created = self._create_or_reuse_reminder(p)
            changes.append({"field": "reminder_id", "old": None, "new": rid, "created": created})
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
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.COMPLETED.value})
            matter_id = row["matter_id"]
        elif kind == OpKind.SNOOZE_REMINDER.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            self.store.execute(
                "UPDATE reminders SET status=?, due_at=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.SNOOZED.value, p["due_at"], now_ms(), rid),
            )
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
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.CANCELLED.value})
            matter_id = row["matter_id"]
        elif kind == OpKind.MARK_REMINDER_FIRED.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            if row["status"] == ReminderStatus.FIRED.value and row.get("last_fired_at"):
                return {"changes": [], "matter_id": row["matter_id"], "already_fired": True, "reminder_id": rid}
            self.store.execute(
                "UPDATE reminders SET status=?, fire_count=fire_count+1, last_fired_at=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.FIRED.value, now_ms(), now_ms(), rid),
            )
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.FIRED.value})
            matter_id = row["matter_id"]
        elif kind == OpKind.MARK_REMINDER_MISSED.value:
            rid = p["reminder_id"]
            row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (rid,))
            if not row:
                raise ValidationReject("reminder not found", op.op_id)
            self.store.execute(
                "UPDATE reminders SET status=?, updated_at=? WHERE reminder_id=?",
                (ReminderStatus.MISSED.value, now_ms(), rid),
            )
            changes.append({"field": "status", "old": row["status"], "new": ReminderStatus.MISSED.value})
            matter_id = row["matter_id"]
        elif kind == OpKind.ATTACH_FILE.value:
            fid = new_id("file")
            # File Ledger holds semantics + links only; bytes/hash stay in Source & Evidence
            self.store.execute(
                "INSERT INTO files(file_id,matter_id,filename,file_type,product_ref,source_id,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    fid,
                    p["matter_id"],
                    p["filename"],
                    p.get("file_type") or "",
                    p.get("product_ref"),
                    op.source_ref,
                    now_ms(),
                ),
            )
            fields = {}
            m = self.matter.get(p["matter_id"])
            if m:
                fields = m.get("fields", {})
            files = list(fields.get("files") or [])
            files.append(
                {
                    "file_id": fid,
                    "filename": p["filename"],
                    "source_id": op.source_ref,
                    "product_ref": p.get("product_ref"),
                }
            )
            self.matter.update_fields(p["matter_id"], {"files": files})
            changes.append({"field": "file_id", "old": None, "new": fid, "source_id": op.source_ref})
            matter_id = p["matter_id"]
        else:
            raise ValidationReject(f"unhandled op kind {kind}", op.op_id)

        return {"changes": changes, "matter_id": matter_id}

    def _create_or_reuse_reminder(self, p: dict) -> tuple[str, bool]:
        """Reminder identity = (matter_id, title, due_at) among *active* rows.

        Delivery collapse_key is NOT create-identity: completed/cancelled
        reminders must not swallow a new commitment with the same title.
        An explicit collapse_key on an *active* row is a semantic link —
        correction/replace reschedules that row instead of double-booking.
        """
        active = ("SCHEDULED", "SNOOZED", "MISSED", "FIRED")
        placeholders = ",".join("?" * len(active))
        existing = self.store.query_one(
            f"SELECT reminder_id FROM reminders WHERE matter_id=? AND title=? AND due_at=? AND status IN ({placeholders})",
            (p["matter_id"], p["title"], p["due_at"], *active),
        )
        if existing:
            return existing["reminder_id"], False
        collapse = p.get("collapse_key") or f"{p['matter_id']}:{p['title']}:{p['due_at']}"
        # semantic replace: same collapse_key active row moves to the new due
        linked = self.store.query_one(
            f"SELECT reminder_id, due_at, status FROM reminders "
            f"WHERE matter_id=? AND collapse_key=? AND status IN ({placeholders})",
            (p["matter_id"], collapse, *active),
        )
        if linked:
            self.store.execute(
                "UPDATE reminders SET title=?, body=?, due_at=?, next_action=?, status=?, updated_at=? WHERE reminder_id=?",
                (
                    p["title"],
                    p.get("body", ""),
                    p["due_at"],
                    p.get("next_action", ""),
                    ReminderStatus.SCHEDULED.value,
                    now_ms(),
                    linked["reminder_id"],
                ),
            )
            return linked["reminder_id"], False
        rid = new_id("rem")
        now = now_ms()
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
        return rid, True

    def _upsert_knowledge(self, p: dict, source_id: Optional[str]) -> str:
        self.store.require_transaction("KnowledgeLedger.upsert")
        existing = self.store.query_one("SELECT knowledge_id FROM knowledge WHERE topic=?", (p["topic"],))
        if existing:
            self.store.execute(
                "UPDATE knowledge SET content=?, source_id=? WHERE knowledge_id=?",
                (p["content"], source_id, existing["knowledge_id"]),
            )
            return existing["knowledge_id"]
        kid = new_id("know")
        self.store.execute(
            "INSERT INTO knowledge(knowledge_id,topic,content,source_id,created_at) VALUES(?,?,?,?,?)",
            (kid, p["topic"], p["content"], source_id, now_ms()),
        )
        return kid


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

    def commit_ops(
        self,
        ops: list[LedgerOp],
        *,
        require_confirm: bool = False,
        on_success=None,
    ) -> ChangeReceipt:
        """Apply ops atomically. on_success(store, receipt_id) is same-txn companion write."""
        if require_confirm and any(o.risk == "high" for o in ops):
            raise CommitError("HIGH_RISK_CONFIRM_REQUIRED")

        applied: list[str] = []
        all_changes: list[dict] = []
        matter_ids: set[str] = set()
        duplicates: list[str] = []
        pending: list[LedgerOp] = []

        for op in ops:
            try:
                self.validator.validate(op)
            except ValidationReject as e:
                receipt = ChangeReceipt(
                    receipt_id=new_id("rcpt"),
                    commit_id="none",
                    op_ids=[op.op_id],
                    status="REJECTED",
                    summary=f"校验失败：{e.reason}",
                    old_to_new=[],
                )
                self.receipts.emit(receipt)
                raise
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
        receipt_id = new_id("rcpt")
        try:
            with self.store.transaction():
                for op in pending:
                    if op.kind == OpKind.CORRECT_FIELD.value:
                        result = self.corrections.apply(op)
                    else:
                        result = self.patcher.apply_op(op)
                    changes = result.get("changes", [])
                    all_changes.extend(changes)
                    mid = result.get("matter_id") or op.matter_ref or op.payload.get("matter_id")
                    if mid:
                        matter_ids.add(mid)
                    # parent link changes dirty both sides so tree rollup can refresh
                    for ch in changes:
                        if ch.get("field") == "parent_matter_id":
                            if ch.get("old"):
                                matter_ids.add(ch["old"])
                            if ch.get("new"):
                                matter_ids.add(ch["new"])
                    if op.kind == OpKind.CREATE_MATTER.value and op.payload.get("parent_matter_id"):
                        matter_ids.add(op.payload["parent_matter_id"])
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
                    (commit_id, json.dumps(applied), receipt_id, now_ms()),
                )
                if on_success is not None:
                    on_success(self.store, receipt_id)
        except Exception as e:
            # full rollback owned by transaction; emit durable REJECTED receipt
            receipt = ChangeReceipt(
                receipt_id=new_id("rcpt"),
                commit_id=commit_id,
                op_ids=[o.op_id for o in pending],
                status="REJECTED",
                summary=f"提交失败，已全部回滚：{e}",
                old_to_new=[],
                matter_ref=next(iter(matter_ids), None),
            )
            self.receipts.emit(receipt)
            raise CommitError(str(e)) from e

        # dirty tracking for ALL matters in this batch (post durable commit)
        for mid in matter_ids:
            self.store.execute(
                "INSERT OR REPLACE INTO dirty_nodes(node_id,node_kind,marked_at) VALUES(?,?,?)",
                (mid, "matter", now_ms()),
            )
        self.store.commit()

        summary = self._summarize(all_changes, duplicates)
        receipt = ChangeReceipt(
            receipt_id=receipt_id,
            commit_id=commit_id,
            op_ids=applied + duplicates,
            status="COMMITTED",
            summary=summary,
            old_to_new=all_changes,
            matter_ref=next(iter(matter_ids), None),
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
