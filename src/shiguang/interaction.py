# -*- coding: utf-8 -*-
"""interaction-layer: inbound gateway, normalizer, delivery router, channel identity."""
from __future__ import annotations

import json
from typing import Any, Optional

from .source_evidence import SourceEvidenceService
from .storage import Store
from .types import DeliveryPayload, EffectReceipt, MessageEnvelope, new_id, now_ms


class FakeInboundChannel:
    def __init__(self, channel: str = "fake"):
        self.channel = channel
        self.received: list[dict] = []

    def push(self, user_ref: str, text: str, attachments: Optional[list] = None) -> dict:
        msg = {
            "channel": self.channel,
            "user_ref": user_ref,
            "text": text,
            "attachments": attachments or [],
            "ts": now_ms(),
        }
        self.received.append(msg)
        return msg


class MessageNormalizer:
    def normalize(self, raw: dict) -> MessageEnvelope:
        text = raw.get("text") or ""
        return MessageEnvelope(
            message_id=new_id("msg"),
            channel=raw.get("channel") or "fake",
            user_ref=raw.get("user_ref") or "user",
            ts_ms=int(raw.get("ts") or now_ms()),
            text=text,
            attachments=raw.get("attachments") or [],
            provenance={"channel": raw.get("channel"), "user_ref": raw.get("user_ref")},
        )


class ChannelIdentityMapping:
    def __init__(self, store: Store):
        self.store = store

    def map_user(self, channel: str, channel_user_ref: str, person_id: Optional[str] = None) -> str:
        existing = self.store.query_one(
            "SELECT principal_id FROM channel_identities WHERE channel=? AND channel_user_ref=?",
            (channel, channel_user_ref),
        )
        if existing:
            return existing["principal_id"]
        pid = new_id("principal")
        self.store.execute(
            "INSERT INTO channel_identities(principal_id,channel,channel_user_ref,person_id,status,created_at) VALUES(?,?,?,?,?,?)",
            (pid, channel, channel_user_ref, person_id, "BOUND", now_ms()),
        )
        self.store.commit()
        return pid

    def rebind(self, principal_id: str, person_id: str) -> None:
        self.store.execute(
            "UPDATE channel_identities SET person_id=?, status='BOUND' WHERE principal_id=?",
            (person_id, principal_id),
        )
        self.store.commit()

    def unbind(self, principal_id: str) -> None:
        self.store.execute(
            "UPDATE channel_identities SET status='UNBOUND' WHERE principal_id=?",
            (principal_id,),
        )
        self.store.commit()


class FakeDeliveryAdapter:
    def __init__(self):
        self.sent: list[dict] = []
        self.fail_next = False

    def send(self, payload: DeliveryPayload) -> dict:
        if self.fail_next:
            self.fail_next = False
            return {"ok": False, "error": "channel_limited"}
        rec = {
            "delivery_id": payload.delivery_id,
            "kind": payload.kind,
            "channel": payload.channel,
            "user_ref": payload.user_ref,
            "text": payload.text,
            "matter_ref": payload.matter_ref,
            "reminder_ref": payload.reminder_ref,
            "collapse_key": payload.collapse_key,
        }
        self.sent.append(rec)
        return {"ok": True, "external_ref": payload.delivery_id}


class DeliveryRouter:
    """Select channel, collapse/dedup, write delivery + effect receipt."""

    def __init__(self, store: Store, adapter: FakeDeliveryAdapter, source: SourceEvidenceService):
        self.store = store
        self.adapter = adapter
        self.source = source

    def deliver(self, *, kind: str, user_ref: str, text: str, channel: str = "fake", matter_ref: str = None, reminder_ref: str = None, collapse_key: str = None) -> dict:
        # collapse: if same collapse_key already sent and status ok, skip
        if collapse_key:
            prior = self.store.query_one(
                "SELECT delivery_id FROM deliveries WHERE collapse_key=? AND status='SENT' AND reminder_ref=?",
                (collapse_key, reminder_ref),
            )
            if prior:
                return {"delivered": False, "reason": "COLLAPSED", "delivery_id": prior["delivery_id"]}

        payload = DeliveryPayload(
            delivery_id=new_id("del"),
            kind=kind,
            channel=channel,
            user_ref=user_ref,
            text=text,
            matter_ref=matter_ref,
            reminder_ref=reminder_ref,
            collapse_key=collapse_key,
        )
        result = self.adapter.send(payload)
        status = "SENT" if result.get("ok") else "FAILED"
        self.store.execute(
            "INSERT INTO deliveries(delivery_id,kind,channel,user_ref,text,matter_ref,reminder_ref,collapse_key,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                payload.delivery_id,
                kind,
                channel,
                user_ref,
                text,
                matter_ref,
                reminder_ref,
                collapse_key,
                status,
                payload.created_at,
            ),
        )
        self.store.commit()
        effect = EffectReceipt(
            effect_id=new_id("eff"),
            capability=f"deliver_{kind}",
            request_digest=text[:64],
            target=f"{channel}:{user_ref}",
            result="success" if result.get("ok") else "failed",
            external_ref=result.get("external_ref"),
            timestamp=now_ms(),
            evidence_ref=None,
        )
        self.source.effects.attach(effect)
        return {
            "delivered": result.get("ok") is True,
            "delivery_id": payload.delivery_id,
            "status": status,
            "external_ref": result.get("external_ref"),
            "effect_id": effect.effect_id,
        }

    def resend_failed(self) -> list[dict]:
        rows = self.store.query("SELECT * FROM deliveries WHERE status='FAILED'")
        out = []
        for r in rows:
            res = self.deliver(
                kind=r["kind"],
                user_ref=r["user_ref"],
                text=r["text"],
                channel=r["channel"],
                matter_ref=r["matter_ref"],
                reminder_ref=r["reminder_ref"],
                collapse_key=r["collapse_key"],
            )
            out.append(res)
        return out
