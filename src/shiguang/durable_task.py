# -*- coding: utf-8 -*-
"""durable-task-runtime: reminder-scheduler + delayed runner + task-action-bridge.

complete/snooze/fire go through TaskActionProposal → State/Commit.
Directive policy is evaluated BEFORE fire mutation.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .storage import Store
from .types import LedgerOp, MessageEnvelope, OpKind, PolicyDecision, ReminderStatus, new_id, now_ms


class FakeClock:
    """Controllable clock for tests and delayed runner."""

    def __init__(self, start_ms: Optional[int] = None):
        self._now = start_ms if start_ms is not None else now_ms()

    def now(self) -> int:
        return self._now

    def set(self, ts: int) -> None:
        self._now = ts

    def advance_ms(self, delta: int) -> int:
        self._now += delta
        return self._now

    def advance_hours(self, hours: float) -> int:
        return self.advance_ms(int(hours * 3600 * 1000))


class ReminderScheduler:
    def __init__(self, store: Store, clock: FakeClock):
        self.store = store
        self.clock = clock

    def due_reminders(self) -> list[dict]:
        now = self.clock.now()
        return self.store.query(
            "SELECT * FROM reminders WHERE status IN ('SCHEDULED','SNOOZED','MISSED') AND due_at <= ? ORDER BY due_at",
            (now,),
        )

    def mark_fired_ops(self, reminder_id: str) -> list[LedgerOp]:
        """Fire is a canonical reminder mutation → produces ops for State/Commit."""
        return [
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.MARK_REMINDER_FIRED.value,
                payload={"reminder_id": reminder_id},
                actor="durable",
            )
        ]

    def mark_missed_ops(self, reminder_id: str) -> list[LedgerOp]:
        return [
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.MARK_REMINDER_MISSED.value,
                payload={"reminder_id": reminder_id},
                actor="durable",
            )
        ]

    def mark_missed_catchup(self) -> list[dict]:
        now = self.clock.now()
        rows = self.store.query(
            "SELECT * FROM reminders WHERE status IN ('SCHEDULED','SNOOZED') AND due_at < ?",
            (now - 24 * 3600 * 1000,),
        )
        return [dict(r) for r in rows]


class DirectivePolicyEvaluator:
    """Minimal P0 policy: deny/defer night work notifications only.

    Precedence: DENY > DEFER > ALLOW.
    """

    NIGHT_START = 22
    NIGHT_END = 8

    def __init__(self, store: Store, clock: FakeClock):
        self.store = store
        self.clock = clock

    def evaluate_delivery(self, *, kind: str, target: str, text: str = "") -> PolicyDecision:
        hour = (self.clock.now() // 3600000) % 24
        # parentheses required: only notifications are subject to night quiet hours
        if kind == "notification" and (hour >= self.NIGHT_START or hour < self.NIGHT_END):
            if any(w in text for w in ("工作", "合同", "客户", "项目", "盖章", "确认")):
                return PolicyDecision(
                    action="defer",
                    directive_ids=["night-quiet-work"],
                    reason="夜间工作提醒按 Directive 延后",
                )
        return PolicyDecision(action="allow", directive_ids=[], reason="")


class TaskActionBridge:
    """User complete/snooze → LedgerOps → State/Commit → Matter update."""

    def __init__(self, store: Store):
        self.store = store

    def complete(self, reminder_id: str) -> list[LedgerOp]:
        row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (reminder_id,))
        if not row:
            raise KeyError(reminder_id)
        ops = [
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.COMPLETE_REMINDER.value,
                payload={"reminder_id": reminder_id},
                matter_ref=row["matter_id"],
                actor="user_task_action",
            ),
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.UPDATE_MATTER.value,
                payload={
                    "matter_id": row["matter_id"],
                    "status": "DONE",
                    "fields": {"completed_reminder": reminder_id},
                },
                matter_ref=row["matter_id"],
                actor="user_task_action",
            ),
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.APPEND_EVENT.value,
                payload={
                    "event_type": "reminder_completed",
                    "summary": f"完成提醒：{row['title']}",
                    "payload": {"reminder_id": reminder_id},
                },
                matter_ref=row["matter_id"],
                actor="user_task_action",
            ),
        ]
        return ops

    def snooze(self, reminder_id: str, new_due_at: int) -> list[LedgerOp]:
        row = self.store.query_one("SELECT * FROM reminders WHERE reminder_id=?", (reminder_id,))
        if not row:
            raise KeyError(reminder_id)
        return [
            LedgerOp(
                op_id=new_id("op"),
                kind=OpKind.SNOOZE_REMINDER.value,
                payload={"reminder_id": reminder_id, "due_at": new_due_at},
                matter_ref=row["matter_id"],
                actor="user_task_action",
            )
        ]


class DurableTaskRuntime:
    def __init__(
        self,
        store: Store,
        clock: FakeClock,
        policy: DirectivePolicyEvaluator,
        commit_ops=None,
    ):
        self.store = store
        self.clock = clock
        self.policy = policy
        self.scheduler = ReminderScheduler(store, clock)
        self.bridge = TaskActionBridge(store)
        # injectable StateCommitEngine.commit_ops for canonical mutations
        self._commit_ops = commit_ops

    def run_due(self, deliver_fn: Optional[Callable[[dict], dict]] = None) -> list[dict]:
        results = []
        for rem in self.scheduler.due_reminders():
            payload = {
                "kind": "notification",
                "reminder_id": rem["reminder_id"],
                "matter_id": rem["matter_id"],
                "title": rem["title"],
                "body": rem["body"],
                "next_action": rem.get("next_action"),
                "collapse_key": rem.get("collapse_key"),
                "text": f"提醒：{rem['title']}｜{rem.get('next_action') or rem['body']}",
            }
            # policy BEFORE any fire mutation
            decision = self.policy.evaluate_delivery(
                kind="notification", target=rem.get("collapse_key") or "", text=payload["text"]
            )
            if decision.action != "allow":
                next_morning = ((self.clock.now() // 86400000) + 1) * 86400000 + 9 * 3600000
                if self._commit_ops:
                    self._commit_ops(
                        [
                            LedgerOp(
                                op_id=new_id("op"),
                                kind=OpKind.SNOOZE_REMINDER.value,
                                payload={"reminder_id": rem["reminder_id"], "due_at": int(next_morning)},
                                matter_ref=rem["matter_id"],
                                actor="durable_defer",
                            )
                        ]
                    )
                results.append(
                    {"reminder_id": rem["reminder_id"], "status": "DEFERRED", "reason": decision.reason}
                )
                continue

            # already fired once? skip (idempotent)
            if rem["status"] == ReminderStatus.FIRED.value and rem.get("last_fired_at"):
                results.append({"reminder_id": rem["reminder_id"], "status": "ALREADY_FIRED"})
                continue

            if self._commit_ops:
                self._commit_ops(self.scheduler.mark_fired_ops(rem["reminder_id"]))
            delivery = deliver_fn(payload) if deliver_fn else {"delivered": True, "payload": payload}
            results.append(
                {
                    "reminder_id": rem["reminder_id"],
                    "status": "FIRED",
                    "delivery": delivery,
                    "payload": payload,
                }
            )
        return results
