# -*- coding: utf-8 -*-
"""agent-runtime: model-adapter + turn-orchestrator + ledger-ops-proposer.

Model is lubricant; Core owns persistence. P0 uses a deterministic rule model
that can later be swapped via ModelAdapter.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .context_engine import WorkingContextCompiler
from .storage import Store
from .types import LedgerOp, MessageEnvelope, OpKind, new_id, now_ms


@dataclass
class TurnResult:
    turn_id: str
    reply: str
    ops: list[LedgerOp] = field(default_factory=list)
    confirmations: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class ModelAdapter:
    """Replaceable model boundary. P0: RuleBasedModel."""

    def complete(self, *, text: str, context: dict) -> dict:
        raise NotImplementedError


class RuleBasedModel(ModelAdapter):
    """Deterministic Chinese pattern model for P0 nightly fixture + common cases."""

    def complete(self, *, text: str, context: dict) -> dict:
        t = text.strip()
        # Correction
        if any(k in t for k in ("说错了", "纠正", "不是周三", "不是周四", "改一下", "应该是")):
            return self._correction(t, context)
        # Supplement
        if t.startswith("补充") or "补充一下" in t or "另外" in t[:4]:
            return self._supplement(t, context)
        # Status query
        if any(k in t for k in ("怎么样", "什么情况", "进度", "状态")) or t.endswith("？") or t.endswith("?"):
            return self._query(t, context)
        # Reminder / commitment
        if "提醒" in t or "记得" in t or "之前" in t:
            return self._reminder(t, context)
        return {
            "intent": "note",
            "reply": "好的，我记下了。",
            "ops": [],
            "extract": {"text": t},
        }

    def _extract_person(self, t: str) -> Optional[str]:
        # prefer explicit "联系X+title"
        m = re.search(r"联系([一-龥]{1,3}(?:经理|老师|总|工|医生|律师|先生|女士))", t)
        if m:
            return m.group(1)
        # title suffix, name = 1-2 chars immediately before title
        m = re.search(r"(?:^|[^一-龥])([一-龥]{1,2}(?:经理|老师|总|工|医生|律师|先生|女士))", t)
        if m:
            return m.group(1)
        m = re.search(r"([一-龥]{1,2}(?:经理|老师|总|工|医生|律师|先生|女士))", t)
        return m.group(1) if m else None

    def _extract_deadline(self, t: str) -> tuple[Optional[int], Optional[str]]:
        """Return (due_at_ms, label). Uses context['now_ms'] + day offset."""
        now = int(context_now(t, 0))
        return None, None  # overridden below

    def _reminder(self, t: str, context: dict) -> dict:
        now = context.get("now_ms") or now_ms()
        person = self._extract_person(t)
        title_bits = []
        if "合同" in t:
            title_bits.append("合同盖章")
        if "确认" in t:
            title_bits.append("确认")
        if "联系" in t:
            title_bits.append("联系" + (person or "对方"))
        title = "｜".join(title_bits) if title_bits else (t[:20] if len(t) > 20 else t)
        due_at = self._parse_due(t, now)
        people_names = [person] if person else []
        # find existing matter in context
        matter_id = self._match_matter(t, context)
        ops: list[dict] = []
        extract = {
            "person": person,
            "title": title,
            "due_at": due_at,
            "due_label": self._due_label(t),
            "matter_id": matter_id,
            "raw": t,
        }
        reply = "好的，我记下了。"
        if due_at:
            reply = f"好的，{self._due_label(t) or '到点'}提醒你{title}。"
        return {
            "intent": "reminder",
            "reply": reply,
            "ops": ops,
            "extract": extract,
            "people_names": people_names,
            "matter_title": title if not matter_id else None,
        }

    def _parse_due(self, t: str, now: int) -> Optional[int]:
        day = 86400000
        # 明天下午 / 明天
        if "明天下午" in t or "明天 15" in t or "明天15" in t:
            base = now + day
            return (base // day) * day + 15 * 3600000
        if "明天" in t:
            base = now + day
            return (base // day) * day + 15 * 3600000
        # 周三/周四 18:00 as "before that day" → set due to that day 18:00
        m = re.search(r"周([一二三四五六日天])", t)
        if m:
            return self._next_weekday(now, m.group(1))
        if "今天" in t:
            return (now // day) * day + 18 * 3600000
        return None

    def _due_label(self, t: str) -> str:
        if "明天下午" in t:
            return "明天下午"
        if "明天" in t:
            return "明天下午"
        m = re.search(r"周([一二三四五六日天])(之前|以前)?", t)
        if m:
            return f"周{m.group(1)}之前"
        return ""

    def _next_weekday(self, now: int, wd_char: str) -> int:
        mapping = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        target = mapping[wd_char]
        day = 86400000
        base = (now // day) * day
        # weekday from epoch: 1970-01-01 is Thursday
        current_wd = ((base // day) + 4) % 7
        delta = (target - current_wd) % 7
        if delta == 0:
            delta = 7
        return base + delta * day + 18 * 3600000

    def _match_matter(self, t: str, context: dict) -> Optional[str]:
        caps = context.get("capsules") or []
        best = None
        best_score = 0
        for c in caps:
            goal = (c.get("goal") or "") + " " + json.dumps(c, ensure_ascii=False)
            score = 0
            if "合同" in t and "合同" in goal:
                score += 3
            if "李" in t and "李" in goal:
                score += 3
            for name in ("李经理", "合同", "盖章"):
                if name in t and name in goal:
                    score += 2
            if score > best_score:
                best_score = score
                best = c.get("matter_id")
        return best if best_score else None

    def _supplement(self, t: str, context: dict) -> dict:
        now = context.get("now_ms") or now_ms()
        due_at = self._parse_due(t, now)
        matter_id = self._match_matter(t, context) or self._first_matter(context)
        return {
            "intent": "supplement",
            "reply": "好的，我补充进去了。",
            "ops": [],
            "extract": {
                "matter_id": matter_id,
                "due_at": due_at,
                "due_label": self._due_label(t),
                "raw": t,
                "text": t,
            },
        }

    def _correction(self, t: str, context: dict) -> dict:
        now = context.get("now_ms") or now_ms()
        # Prefer the *corrected* value after 不是/改为/是
        new_label = None
        m = re.search(r"不是周([一二三四五六日天]).*?(?:是|到)周([一二三四五六日天])", t)
        if m:
            new_label = "周" + m.group(2)
        else:
            m = re.search(r"改(?:成|为|到)周([一二三四五六日天])", t)
            if m:
                new_label = "周" + m.group(1)
            else:
                # last weekday mentioned as the intended one
                days = re.findall(r"周([一二三四五六日天])", t)
                if days:
                    new_label = "周" + days[-1]
        # due_at from corrected weekday only
        due_at = None
        if new_label:
            due_at = self._next_weekday(now, new_label[-1])
        matter_id = self._match_matter(t, context) or self._first_matter(context)
        return {
            "intent": "correction",
            "reply": f"已更正，后续按{new_label or '新的日期'}来。",
            "ops": [],
            "extract": {
                "matter_id": matter_id,
                "due_at": due_at,
                "due_label": new_label or self._due_label(t),
                "field": "due_at" if due_at else "due_label",
                "raw": t,
            },
        }

    def _query(self, t: str, context: dict) -> dict:
        matter_id = self._match_matter(t, context) or self._first_matter(context)
        return {
            "intent": "query",
            "reply": "",
            "ops": [],
            "extract": {"matter_id": matter_id, "raw": t},
        }

    def _first_matter(self, context: dict) -> Optional[str]:
        caps = context.get("capsules") or []
        return caps[0].get("matter_id") if caps else None


def context_now(_t, default):
    return default


class LedgerOpsProposer:
    """Turn extract → idempotent LedgerOps."""

    def propose(self, result: dict, *, source_id: str, now_ms: int) -> list[LedgerOp]:
        intent = result.get("intent")
        extract = result.get("extract") or {}
        ops: list[LedgerOp] = []
        people = result.get("people_names") or []

        if intent == "reminder":
            mid = extract.get("matter_id")
            if not mid:
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.CREATE_MATTER.value,
                        payload={
                            "title": extract.get("title") or extract.get("raw", "")[:30],
                            "next_action": extract.get("title") or "",
                            "due_at": extract.get("due_at"),
                            "fields": {"people_names": people, "due_label": extract.get("due_label")},
                        },
                        source_ref=source_id,
                        actor="agent",
                    )
                )
            else:
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.UPDATE_MATTER.value,
                        payload={
                            "matter_id": mid,
                            "next_action": extract.get("title") or "",
                            "due_at": extract.get("due_at"),
                            "fields": {"due_label": extract.get("due_label"), "people_names": people},
                        },
                        matter_ref=mid,
                        source_ref=source_id,
                        actor="agent",
                    )
                )
            for name in people:
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.UPSERT_PERSON.value,
                        payload={"name": name},
                        source_ref=source_id,
                        actor="agent",
                    )
                )
            ops.append(
                LedgerOp(
                    op_id=new_id("op"),
                    kind=OpKind.APPEND_EVENT.value,
                    payload={
                        "event_type": "commitment",
                        "summary": extract.get("raw") or "记录承诺",
                        "people": people,
                    },
                    matter_ref=mid,
                    source_ref=source_id,
                    actor="agent",
                )
            )
            if extract.get("due_at"):
                # matter_id for reminder may be unknown until create — leave placeholder fixed later
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.CREATE_REMINDER.value,
                        payload={
                            "matter_id": mid or "__NEW__",
                            "title": extract.get("title") or "提醒",
                            "body": extract.get("raw") or "",
                            "due_at": extract.get("due_at"),
                            "next_action": extract.get("title") or "",
                        },
                        matter_ref=mid,
                        source_ref=source_id,
                        actor="agent",
                    )
                )
        elif intent == "supplement":
            mid = extract.get("matter_id")
            if mid:
                patch = {"last_supplement": extract.get("raw")}
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.UPDATE_MATTER.value,
                        payload={
                            "matter_id": mid,
                            "next_action": extract.get("text") or extract.get("raw") or "",
                            "due_at": extract.get("due_at"),
                            "fields": {"due_label": extract.get("due_label")},
                        },
                        matter_ref=mid,
                        source_ref=source_id,
                        actor="agent",
                    )
                )
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.APPEND_EVENT.value,
                        payload={"event_type": "supplement", "summary": extract.get("raw") or ""},
                        matter_ref=mid,
                        source_ref=source_id,
                        actor="agent",
                    )
                )
                if extract.get("due_at"):
                    ops.append(
                        LedgerOp(
                            op_id=new_id("op"),
                            kind=OpKind.CREATE_REMINDER.value,
                            payload={
                                "matter_id": mid,
                                "title": extract.get("due_label") or "截止确认",
                                "body": extract.get("raw") or "",
                                "due_at": extract.get("due_at"),
                                "next_action": extract.get("due_label") or "确认",
                                "collapse_key": f"{mid}:deadline",
                            },
                            matter_ref=mid,
                            source_ref=source_id,
                            actor="agent",
                        )
                    )
        elif intent == "correction":
            mid = extract.get("matter_id")
            if mid:
                # correct current fields: due_at and due_label together when both known
                if extract.get("due_at"):
                    ops.append(
                        LedgerOp(
                            op_id=new_id("op"),
                            kind=OpKind.CORRECT_FIELD.value,
                            payload={
                                "target_kind": "matter",
                                "target_id": mid,
                                "field": "due_at",
                                "new_value": extract.get("due_at"),
                                "old_value": extract.get("old_value"),
                            },
                            matter_ref=mid,
                            source_ref=source_id,
                            actor="agent",
                        )
                    )
                if extract.get("due_label"):
                    ops.append(
                        LedgerOp(
                            op_id=new_id("op"),
                            kind=OpKind.CORRECT_FIELD.value,
                            payload={
                                "target_kind": "matter",
                                "target_id": mid,
                                "field": "due_label",
                                "new_value": extract.get("due_label"),
                            },
                            matter_ref=mid,
                            source_ref=source_id,
                            actor="agent",
                        )
                    )
                    ops.append(
                        LedgerOp(
                            op_id=new_id("op"),
                            kind=OpKind.UPDATE_MATTER.value,
                            payload={
                                "matter_id": mid,
                                "next_action": f"确认（{extract.get('due_label')}之前）",
                                "fields": {"due_label": extract.get("due_label")},
                            },
                            matter_ref=mid,
                            source_ref=source_id,
                            actor="agent",
                        )
                    )
                ops.append(
                    LedgerOp(
                        op_id=new_id("op"),
                        kind=OpKind.APPEND_EVENT.value,
                        payload={
                            "event_type": "correction",
                            "summary": extract.get("raw") or "纠正",
                        },
                        matter_ref=mid,
                        source_ref=source_id,
                        actor="agent",
                    )
                )
                if extract.get("due_at"):
                    ops.append(
                        LedgerOp(
                            op_id=new_id("op"),
                            kind=OpKind.CREATE_REMINDER.value,
                            payload={
                                "matter_id": mid,
                                "title": extract.get("due_label") or "截止确认",
                                "body": extract.get("raw") or "",
                                "due_at": extract.get("due_at"),
                                "next_action": extract.get("due_label") or "确认",
                                "collapse_key": f"{mid}:deadline",
                            },
                            matter_ref=mid,
                            source_ref=source_id,
                            actor="agent",
                        )
                    )
        elif intent == "query":
            pass
        return ops


class TurnOrchestrator:
    def __init__(self, store: Store, model: ModelAdapter, context: WorkingContextCompiler, proposer: LedgerOpsProposer):
        self.store = store
        self.model = model
        self.context = context
        self.proposer = proposer

    def run_turn(self, env: MessageEnvelope, *, now_ms: int) -> TurnResult:
        turn_id = new_id("turn")
        ctx = self.context.compile(query=env.text)
        ctx["now_ms"] = now_ms
        raw = self.model.complete(text=env.text, context=ctx)
        ops = self.proposer.propose(raw, source_id=env.raw_source_id or "", now_ms=now_ms)
        reply = raw.get("reply") or ""
        if raw.get("intent") == "query":
            mid = (raw.get("extract") or {}).get("matter_id")
            reply = self._answer_query(mid, ctx)
        return TurnResult(
            turn_id=turn_id,
            reply=reply,
            ops=ops,
            meta={"intent": raw.get("intent"), "extract": raw.get("extract"), "context_sources": ctx.get("sources")},
        )

    def _answer_query(self, matter_id: Optional[str], ctx: dict) -> str:
        if not matter_id:
            # last resort: keyword search on title
            return "我这边还没有找到对应事项。"
        for c in ctx.get("capsules") or []:
            if c.get("matter_id") == matter_id:
                current = c.get("current") or ""
                open_items = "；".join(c.get("open_items") or [])
                recent = "；".join((c.get("recent") or [])[-2:])
                parts = [c.get("goal"), current]
                if open_items:
                    parts.append(f"待办：{open_items}")
                if recent:
                    parts.append(f"最近：{recent}")
                return "，".join([p for p in parts if p]) + "。"
        return "找到了事项，但当前摘要尚未同步。"
