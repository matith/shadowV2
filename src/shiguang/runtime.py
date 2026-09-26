# -*- coding: utf-8 -*-
"""P0 runtime application wiring all blackboxes.

Message → normalize → source store → agent turn → ledger ops →
state/commit → summary → projection; reminders via durable runtime →
directive policy → delivery router.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .agent_runtime import LedgerOpsProposer, RuleBasedModel, TurnOrchestrator
from .context_engine import DirectivePolicy, LedgerRouter, WorkingContextCompiler
from .durable_task import DirectivePolicyEvaluator, DurableTaskRuntime, FakeClock, TaskActionBridge
from .identity import ProjectIdentity, identity_from_repo_root, verify_identity
from .interaction import (
    ChannelIdentityMapping,
    DeliveryRouter,
    FakeDeliveryAdapter,
    FakeInboundChannel,
    MessageNormalizer,
)
from .ledgers import EventLedger, MatterLedger, PeopleLedger
from .p1_slices import ArchiveLedger, KnowledgeLedger, MatterTree, P1WriteBridge
from .projection import TableProjection
from .source_evidence import SourceEvidenceService
from .state_commit import StateCommitEngine
from .storage import Store, open_store
from .summary_system import SummarySystem
from .types import ChangeReceipt, MessageEnvelope, now_ms


class ShiGuangApp:
    def __init__(
        self,
        data_path: str | Path,
        *,
        repo_root: str | Path,
        identity: Optional[ProjectIdentity] = None,
        clock: Optional[FakeClock] = None,
        model: Optional[Any] = None,
        delivery: Optional[FakeDeliveryAdapter] = None,
    ):
        self.repo_root = str(repo_root)
        ident = identity or identity_from_repo_root(repo_root)
        verify_identity(ident)
        self.identity = ident

        self.store: Store = open_store(data_path)
        self.clock = clock or FakeClock()
        self.source = SourceEvidenceService(self.store)
        self.commit = StateCommitEngine(self.store, self.source)
        self.matter = self.commit.matter
        self.event = self.commit.event
        self.people = self.commit.people
        self.summary = SummarySystem(self.store, self.matter, self.event)
        self.ledger_router = LedgerRouter()
        self.directive_policy = DirectivePolicy(self.store)
        self.working_context = WorkingContextCompiler(self.store, self.matter, self.people, self.summary)
        self.model = model or RuleBasedModel()
        self.proposer = LedgerOpsProposer()
        self.turns = TurnOrchestrator(self.store, self.model, self.working_context, self.proposer)
        self.inbound = FakeInboundChannel()
        self.normalizer = MessageNormalizer()
        self.channel_identity = ChannelIdentityMapping(self.store)
        self.delivery_adapter = delivery or FakeDeliveryAdapter()
        self.delivery = DeliveryRouter(self.store, self.delivery_adapter, self.source)
        self.policy_eval = DirectivePolicyEvaluator(self.store, self.clock)
        self.durable = DurableTaskRuntime(
            self.store,
            self.clock,
            self.policy_eval,
            commit_ops=self.commit.commit_ops,
        )
        self.projection = TableProjection(self.store, self.matter, self.commit)
        self.p1_bridge = P1WriteBridge(self.commit.commit_ops)
        self._user_ref = "user_default"

    # ---------- lifecycle ----------
    @classmethod
    def open(cls, repo_root: str | Path, data_path: str | Path, **kwargs) -> "ShiGuangApp":
        return cls(data_path, repo_root=repo_root, **kwargs)

    def close(self) -> None:
        self.store.close()

    # ---------- inbound ----------
    def ingest_text(self, text: str, *, channel: str = "fake", user_ref: str = "user") -> dict:
        raw = self.inbound.push(user_ref, text)
        raw["channel"] = channel
        # use controllable clock so replay bucket is deterministic under FakeClock
        raw["ts"] = self.clock.now()
        env = self.normalizer.normalize(raw)

        # input-level idempotency: same message_id is a replay
        prior = self.store.query_one("SELECT * FROM message_inbox WHERE message_id=?", (env.message_id,))
        if prior:
            return {
                "turn_id": prior.get("turn_id"),
                "source_id": None,
                "intent": "replay",
                "extract": {},
                "reply": "重复消息，已忽略。",
                "receipt": ChangeReceipt(
                    receipt_id=prior.get("receipt_id") or "dup",
                    commit_id="dup",
                    op_ids=[],
                    status="DUPLICATE",
                    summary="输入重放，未重复记账",
                    old_to_new=[],
                ),
                "delivery": {"delivered": False, "reason": "REPLAY"},
                "ops": [],
                "message_id": env.message_id,
                "replay": True,
            }

        self.channel_identity.map_user(channel, user_ref)
        source_id = self.source.raw.store_from_envelope(env)
        env.raw_source_id = source_id

        # ledger routing is advisory (soft), recorded on the turn meta
        route = self.ledger_router.route(env.text)

        turn = self.turns.run_turn(env, now_ms=self.clock.now())
        turn.meta["ledger_route"] = route
        ops = self._resolve_ops(turn.ops, turn)

        # inbox row is part of the same durable boundary as the ops batch
        # (close crash window that would double-write Events on same message_id)
        inbox_sql = (
            "INSERT INTO message_inbox(message_id,channel,user_ref,text_hash,turn_id,receipt_id,status,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)"
        )

        def _write_inbox(store, receipt_id: str):
            store.execute(
                inbox_sql,
                (env.message_id, channel, user_ref, source_id, turn.turn_id, receipt_id, "PROCESSED", now_ms()),
            )

        if ops:
            receipt = self.commit.commit_ops(ops, on_success=_write_inbox)
        else:
            with self.store.transaction():
                _write_inbox(self.store, "none")
            receipt = ChangeReceipt(
                receipt_id="none",
                commit_id="none",
                op_ids=[],
                status="COMMITTED",
                summary="无账本变更",
                old_to_new=[],
            )

        # interpretation record (source-linked)
        interp_id = None
        if turn.meta.get("intent"):
            interp_id = f"interp_{turn.turn_id}"
            self.source.provenance.record_interpretation(
                interp_id=interp_id,
                source_id=source_id,
                kind=str(turn.meta.get("intent")),
                fields=turn.meta.get("extract") or {},
                matter_id=receipt.matter_ref or (turn.meta.get("extract") or {}).get("matter_id"),
            )

        # post-commit summary sync for every dirty matter
        self.summary.process_dirty()

        reply_text = turn.reply
        if ops and receipt.status == "COMMITTED":
            if not reply_text:
                reply_text = "已保存。"
        delivery = self.delivery.deliver(
            kind="reply",
            user_ref=user_ref,
            text=reply_text or "已处理。",
            channel=channel,
            matter_ref=receipt.matter_ref,
        )
        return {
            "turn_id": turn.turn_id,
            "source_id": source_id,
            "intent": turn.meta.get("intent"),
            "extract": turn.meta.get("extract"),
            "reply": reply_text,
            "receipt": receipt,
            "delivery": delivery,
            "ops": [o.to_dict() for o in ops],
            "message_id": env.message_id,
            "replay": False,
            "interp_id": interp_id,
        }

    def _resolve_ops(self, ops, turn) -> list:
        from .types import new_id

        extract = turn.meta.get("extract") or {}
        extract_mid = extract.get("matter_id")
        out = []
        for op in ops:
            payload = dict(op.payload)
            if op.kind == "create_matter":
                out.append(op)
                continue
            # bind missing/placeholder matter ids to extract or upcoming create
            mid = payload.get("matter_id") or op.matter_ref
            if mid in (None, "", "__NEW__"):
                if extract_mid:
                    payload["matter_id"] = extract_mid
                    op.payload = payload
                    op.matter_ref = extract_mid
            out.append(op)

        fixed = []
        pending_new_id = None
        for op in out:
            if op.kind == "create_matter":
                pending_new_id = op.payload.get("matter_id") or new_id("matter")
                op.payload = {**op.payload, "matter_id": pending_new_id}
            # after create_matter, bind any ops still missing matter
            if pending_new_id:
                payload = dict(op.payload)
                if op.kind in (
                    "append_event",
                    "create_reminder",
                    "update_matter",
                    "attach_file",
                    "correct_field",
                ):
                    if payload.get("matter_id") in (None, "", "__NEW__"):
                        payload["matter_id"] = pending_new_id
                        op.payload = payload
                    if not op.matter_ref:
                        op.matter_ref = pending_new_id
                    if op.kind == "correct_field" and payload.get("target_id") in (None, "", "__NEW__"):
                        payload["target_id"] = pending_new_id
                        op.payload = payload
            fixed.append(op)
        return fixed

    # ---------- durable ----------
    def run_due_tasks(self) -> list[dict]:
        def deliver(payload: dict) -> dict:
            return self.delivery.deliver(
                kind="notification",
                user_ref=self._user_ref,
                text=payload["text"],
                matter_ref=payload.get("matter_id"),
                reminder_ref=payload.get("reminder_id"),
                collapse_key=payload.get("collapse_key"),
            )

        return self.durable.run_due(deliver_fn=deliver)

    def complete_reminder(self, reminder_id: str) -> dict:
        ops = self.durable.bridge.complete(reminder_id)
        receipt = self.commit.commit_ops(ops)
        if receipt.matter_ref:
            self.summary.sync_with_matter(receipt.matter_ref)
        return {"receipt": receipt}

    def snooze_reminder(self, reminder_id: str, new_due_at: int) -> dict:
        ops = self.durable.bridge.snooze(reminder_id, new_due_at)
        receipt = self.commit.commit_ops(ops)
        return {"receipt": receipt}

    # ---------- queries ----------
    def list_my_matters(self) -> dict:
        return self.projection.render_default_my_matters()

    def matter_timeline(self, matter_id: str) -> dict:
        m = self.matter.get(matter_id)
        if not m:
            raise KeyError(matter_id)
        events = self.event.list_for_matter(matter_id)
        cap = self.summary.capsule.get(matter_id)
        evidence = self.source.provenance.chain_for_matter(matter_id)
        return {
            "matter": m,
            "events": events,
            "capsule": cap,
            "evidence_chain": evidence,
            "stale": self.summary.is_stale(matter_id),
        }

    def rebuild_capsules(self) -> list[str]:
        return self.summary.process_dirty()
