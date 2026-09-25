# -*- coding: utf-8 -*-
"""source-evidence: raw-source-store + provenance + effect-receipt-store."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Optional

from .storage import Store
from .types import EffectReceipt, MessageEnvelope, now_ms


class RawSourceStore:
    """Immutable raw content. Correction never mutates rows here."""

    def __init__(self, store: Store):
        self.store = store

    def store_text(
        self,
        text: str,
        *,
        channel: str,
        user_ref: str,
        provenance: Optional[dict] = None,
    ) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        source_id = f"src_{digest[:16]}"
        existing = self.store.query_one("SELECT source_id FROM raw_sources WHERE source_id=?", (source_id,))
        if existing:
            return source_id
        prov = provenance or {}
        prov = {**prov, "channel": channel, "user_ref": user_ref, "hash": digest}
        self.store.execute(
            "INSERT INTO raw_sources(source_id,hash,content_type,text_content,bytes_path,channel,user_ref,provenance,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (source_id, digest, "text/plain", text, None, channel, user_ref, json.dumps(prov, ensure_ascii=False), now_ms()),
        )
        self.store.commit()
        return source_id

    def store_bytes(
        self,
        data: bytes,
        *,
        content_type: str,
        filename: str,
        channel: str,
        user_ref: str,
        provenance: Optional[dict] = None,
    ) -> str:
        digest = hashlib.sha256(data).hexdigest()
        source_id = f"src_{digest[:16]}"
        existing = self.store.query_one("SELECT source_id FROM raw_sources WHERE source_id=?", (source_id,))
        if existing:
            return source_id
        blob_path = f"blobs/{source_id}"
        # content kept inline as hex for P0 simplicity when small; path recorded for larger
        prov = {
            **(provenance or {}),
            "channel": channel,
            "user_ref": user_ref,
            "hash": digest,
            "filename": filename,
        }
        self.store.execute(
            "INSERT INTO raw_sources(source_id,hash,content_type,text_content,bytes_path,channel,user_ref,provenance,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                source_id,
                digest,
                content_type,
                None,
                blob_path,
                channel,
                user_ref,
                json.dumps(prov, ensure_ascii=False),
                now_ms(),
            ),
        )
        # store bytes in kv as base64-less raw utf-8 replace for P0 fixtures; real blobs later
        self.store.kv_set(f"blob:{source_id}", {"filename": filename, "b64": data.hex()})
        self.store.commit()
        return source_id

    def get(self, source_id: str) -> Optional[dict]:
        return self.store.query_one("SELECT * FROM raw_sources WHERE source_id=?", (source_id,))

    def resolve_evidence(self, source_id: str) -> Optional[dict]:
        row = self.get(source_id)
        if not row:
            return None
        return {
            "source_id": row["source_id"],
            "hash": row["hash"],
            "content_type": row["content_type"],
            "text": row["text_content"],
            "provenance": json.loads(row["provenance"]),
            "created_at": row["created_at"],
        }

    def store_from_envelope(self, env: MessageEnvelope) -> str:
        return self.store_text(
            env.text,
            channel=env.channel,
            user_ref=env.user_ref,
            provenance=env.provenance or {},
        )


class ProvenanceChain:
    def __init__(self, store: Store):
        self.store = store

    def record_interpretation(
        self,
        *,
        interp_id: str,
        source_id: str,
        kind: str,
        fields: dict,
        matter_id: Optional[str] = None,
    ) -> str:
        self.store.execute(
            "INSERT INTO interpretations(interp_id,source_id,matter_id,kind,fields,status,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                interp_id,
                source_id,
                matter_id,
                kind,
                json.dumps(fields, ensure_ascii=False),
                "ACTIVE",
                now_ms(),
            ),
        )
        self.store.commit()
        return interp_id

    def mark_invalid(self, interp_id: str) -> None:
        self.store.execute(
            "UPDATE interpretations SET status='INVALIDATED', invalidated_at=? WHERE interp_id=?",
            (now_ms(), interp_id),
        )
        self.store.commit()

    def chain_for_matter(self, matter_id: str) -> list[dict]:
        interps = self.store.query(
            "SELECT * FROM interpretations WHERE matter_id=? ORDER BY created_at", (matter_id,)
        )
        out = []
        for i in interps:
            src = self.store.query_one("SELECT source_id,hash,provenance FROM raw_sources WHERE source_id=?", (i["source_id"],))
            out.append(
                {
                    "interp_id": i["interp_id"],
                    "status": i["status"],
                    "kind": i["kind"],
                    "fields": json.loads(i["fields"]),
                    "source": src,
                }
            )
        return out


class EffectReceiptStore:
    def __init__(self, store: Store):
        self.store = store

    def attach(self, receipt: EffectReceipt) -> str:
        self.store.execute(
            "INSERT OR REPLACE INTO effect_receipts(effect_id,capability,request_digest,target,result,external_ref,timestamp,evidence_ref,op_id,turn_id)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                receipt.effect_id,
                receipt.capability,
                receipt.request_digest,
                receipt.target,
                receipt.result,
                receipt.external_ref,
                receipt.timestamp,
                receipt.evidence_ref,
                receipt.op_id,
                receipt.turn_id,
            ),
        )
        self.store.commit()
        return receipt.effect_id

    def get(self, effect_id: str) -> Optional[dict]:
        return self.store.query_one("SELECT * FROM effect_receipts WHERE effect_id=?", (effect_id,))


class SourceEvidenceService:
    def __init__(self, store: Store):
        self.raw = RawSourceStore(store)
        self.provenance = ProvenanceChain(store)
        self.effects = EffectReceiptStore(store)
        self.store = store

    def mark_interpretation_invalid(self, interp_id: str) -> None:
        self.provenance.mark_invalid(interp_id)
