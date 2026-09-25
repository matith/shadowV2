# -*- coding: utf-8 -*-
"""Shared P0 domain types. Mirrors BBM contracts; no third-party reverse-define."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional
import time
import uuid


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class OpKind(str, Enum):
    CREATE_MATTER = "create_matter"
    UPDATE_MATTER = "update_matter"
    APPEND_EVENT = "append_event"
    UPSERT_PERSON = "upsert_person"
    CREATE_REMINDER = "create_reminder"
    COMPLETE_REMINDER = "complete_reminder"
    SNOOZE_REMINDER = "snooze_reminder"
    CANCEL_REMINDER = "cancel_reminder"
    CORRECT_FIELD = "correct_field"
    ATTACH_FILE = "attach_file"
    UPSERT_KNOWLEDGE = "upsert_knowledge"
    UPSERT_DIRECTIVE = "upsert_directive"
    ARCHIVE_MATTER = "archive_matter"


class ReminderStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    FIRED = "FIRED"
    COMPLETED = "COMPLETED"
    SNOOZED = "SNOOZED"
    CANCELLED = "CANCELLED"
    MISSED = "MISSED"


class MatterStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"
    ARCHIVED = "ARCHIVED"


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"


@dataclass
class MessageEnvelope:
    message_id: str
    channel: str
    user_ref: str
    ts_ms: int
    text: str
    attachments: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    raw_source_id: Optional[str] = None


@dataclass
class LedgerOp:
    """Idempotent operation proposed by agent / task bridge / projection edit."""

    op_id: str
    kind: str
    payload: dict
    source_ref: Optional[str] = None  # raw_source_id
    actor: str = "agent"
    risk: str = "low"  # low | high
    matter_ref: Optional[str] = None
    created_at: int = field(default_factory=now_ms)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChangeReceipt:
    receipt_id: str
    commit_id: str
    op_ids: list[str]
    status: str  # COMMITTED | REJECTED | DUPLICATE
    summary: str
    old_to_new: list[dict] = field(default_factory=list)
    created_at: int = field(default_factory=now_ms)
    matter_ref: Optional[str] = None


@dataclass
class PolicyDecision:
    action: str
    directive_ids: list[str]
    reason: str


@dataclass
class EffectReceipt:
    effect_id: str
    capability: str
    request_digest: str
    target: str
    result: str  # success | failed | cancelled
    external_ref: Optional[str]
    timestamp: int
    evidence_ref: Optional[str] = None
    op_id: Optional[str] = None
    turn_id: Optional[str] = None


@dataclass
class DeliveryPayload:
    delivery_id: str
    kind: str  # reply | notification
    channel: str
    user_ref: str
    text: str
    matter_ref: Optional[str] = None
    reminder_ref: Optional[str] = None
    collapse_key: Optional[str] = None
    created_at: int = field(default_factory=now_ms)


class IdentityError(RuntimeError):
    """Project identity gate hard stop."""


class CommitError(RuntimeError):
    pass


class ValidationReject(Exception):
    def __init__(self, reason: str, op_id: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.op_id = op_id
