# -*- coding: utf-8 -*-
"""context-engine: working-context-compiler + ledger-router + directives."""
from __future__ import annotations

import json
from typing import Any, Optional

from .ledgers import MatterLedger, PeopleLedger
from .storage import Store
from .summary_system import SummarySystem


class DirectivePolicy:
    def __init__(self, store: Store):
        self.store = store

    def active_directives(self) -> list[dict]:
        return self.store.query("SELECT * FROM directives WHERE active=1")

    def should_skip_long_term_save(self, text: str) -> bool:
        for d in self.active_directives():
            if d["rule"] == "no_long_term_for_chitchat":
                params = json.loads(d["params"] or "{}")
                words = params.get("keywords") or ["闲聊", "哈哈", "随便说说"]
                if any(w in text for w in words):
                    return True
        return False


class LedgerRouter:
    """Suggest which ledgers an input touches. Soft route, not hard lock."""

    def route(self, text: str) -> list[str]:
        ledgers = []
        if any(k in text for k in ("提醒", "之前", "明天", "后天", "周五", "周三", "周四", "截止")):
            ledgers.extend(["matter", "event"])
        if any(k in text for k in ("经理", "老师", "总", "同事", "客户", "先生", "女士")):
            ledgers.append("people")
        if any(k in text for k in ("合同", "协议", "盖章", "报价", "发票", "文件", "PDF", "截图")):
            ledgers.append("file")
        if any(k in text for k in ("不要记", "别记", "删除", "忘掉")):
            ledgers.append("directive")
        if "matter" not in ledgers:
            ledgers.append("matter")
        if "event" not in ledgers:
            ledgers.append("event")
        return ledgers


class WorkingContextCompiler:
    def __init__(self, store: Store, matter: MatterLedger, people: PeopleLedger, summary: SummarySystem):
        self.store = store
        self.matter = matter
        self.people = people
        self.summary = summary

    def compile(self, *, query: str, budget_items: int = 8) -> dict:
        """Assemble working context under budget. Sources explainable."""
        sources = []
        capsules = []
        # include open + recently touched (query may refer to done/archived matters)
        open_matters = self.matter.list_open()
        all_matters = self.store.query("SELECT * FROM matters ORDER BY updated_at DESC")
        seen = set()
        candidates = []
        for m in open_matters + [dict(r) for r in all_matters]:
            mid = m["matter_id"]
            if mid in seen:
                continue
            seen.add(mid)
            if "fields" not in m:
                m = dict(m)
                m["fields"] = json.loads(m["fields"])
            candidates.append(m)
        q_tokens = set(query.replace("，", " ").replace("。", " ").split())

        def score(m: dict) -> int:
            blob = f"{m['title']} {m.get('next_action') or ''} {json.dumps(m.get('fields') or {}, ensure_ascii=False)}"
            s = 0
            for t in q_tokens:
                if t and t in blob:
                    s += 1
            for ch in ("李", "王", "张", "刘", "陈", "经理", "老师", "合同"):
                if ch in query and ch in blob:
                    s += 2
            return s

        ranked = sorted(candidates, key=lambda m: -score(m))
        # always keep top scored even if 0, so query can resolve
        for m in ranked[:budget_items]:
            if score(m) == 0 and m["status"] in ("DONE", "ARCHIVED") and len(candidates) > budget_items:
                continue
            cap = self.summary.capsule.get(m["matter_id"])
            if not cap or self.summary.is_stale(m["matter_id"]):
                try:
                    self.summary.sync_with_matter(m["matter_id"])
                    cap = self.summary.capsule.get(m["matter_id"])
                except Exception:
                    cap = cap or {
                        "matter_id": m["matter_id"],
                        "goal": m["title"],
                        "current": m.get("next_action") or "",
                        "open_items": [],
                        "evidence": [],
                    }
            capsules.append(cap)
            sources.append({"type": "capsule", "matter_id": m["matter_id"], "title": m["title"]})

        people_rows = self.store.query("SELECT * FROM people")
        people_cards = []
        for p in people_rows:
            if p["name"] and (p["name"] in query or any(p["name"][-2:] == q[-2:] for q in q_tokens if len(q) >= 2)):
                people_cards.append({"person_id": p["person_id"], "name": p["name"], "role": p.get("role")})
                sources.append({"type": "person", "person_id": p["person_id"]})

        directives = self.store.query("SELECT * FROM directives WHERE active=1")
        return {
            "query": query,
            "capsules": capsules,
            "people": people_cards,
            "directives": [{"directive_id": d["directive_id"], "rule": d["rule"]} for d in directives],
            "sources": sources,
            "budget_items": budget_items,
            "evidence_insufficient": False,
        }
