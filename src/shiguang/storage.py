# -*- coding: utf-8 -*-
"""SQLite durable store used by P0 blackboxes as local implementation choice.

BBM allows local DB choice inside blackboxes. Writes are transactional.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_sources (
  source_id TEXT PRIMARY KEY,
  hash TEXT NOT NULL,
  content_type TEXT NOT NULL,
  text_content TEXT,
  bytes_path TEXT,
  channel TEXT,
  user_ref TEXT,
  provenance TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS interpretations (
  interp_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  matter_id TEXT,
  kind TEXT NOT NULL,
  fields TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  invalidated_at INTEGER
);
CREATE TABLE IF NOT EXISTS people (
  person_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  org TEXT,
  role TEXT,
  tags TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS matters (
  matter_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  priority TEXT,
  due_at INTEGER,
  owner_person_id TEXT,
  parent_matter_id TEXT,
  next_action TEXT,
  fields TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  matter_id TEXT,
  event_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  people TEXT,
  source_id TEXT,
  created_at INTEGER NOT NULL,
  payload TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
  reminder_id TEXT PRIMARY KEY,
  matter_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  due_at INTEGER NOT NULL,
  status TEXT NOT NULL,
  fire_count INTEGER NOT NULL DEFAULT 0,
  last_fired_at INTEGER,
  collapse_key TEXT,
  next_action TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS op_log (
  op_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  result TEXT NOT NULL,
  commit_id TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS commits (
  commit_id TEXT PRIMARY KEY,
  op_ids TEXT NOT NULL,
  receipt_id TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS change_receipts (
  receipt_id TEXT PRIMARY KEY,
  commit_id TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL,
  old_to_new TEXT,
  matter_ref TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
  correction_id TEXT PRIMARY KEY,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  field TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT NOT NULL,
  source_id TEXT,
  interp_id TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS capsules (
  matter_id TEXT PRIMARY KEY,
  goal TEXT,
  current TEXT,
  recent TEXT,
  open_items TEXT,
  files TEXT,
  evidence TEXT,
  basis_revision INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS dirty_nodes (
  node_id TEXT PRIMARY KEY,
  node_kind TEXT NOT NULL,
  marked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS effect_receipts (
  effect_id TEXT PRIMARY KEY,
  capability TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  target TEXT NOT NULL,
  result TEXT NOT NULL,
  external_ref TEXT,
  timestamp INTEGER NOT NULL,
  evidence_ref TEXT,
  op_id TEXT,
  turn_id TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
  delivery_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  channel TEXT NOT NULL,
  user_ref TEXT NOT NULL,
  text TEXT NOT NULL,
  matter_ref TEXT,
  reminder_ref TEXT,
  collapse_key TEXT,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_identities (
  principal_id TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  channel_user_ref TEXT NOT NULL,
  person_id TEXT,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS directives (
  directive_id TEXT PRIMARY KEY,
  rule TEXT NOT NULL,
  params TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
  knowledge_id TEXT PRIMARY KEY,
  topic TEXT NOT NULL,
  content TEXT NOT NULL,
  source_id TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matters_status ON matters(status);
CREATE INDEX IF NOT EXISTS idx_events_matter ON events(matter_id);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at, status);
CREATE INDEX IF NOT EXISTS idx_interp_matter ON interpretations(matter_id);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return cur

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def transaction(self):
        return _Txn(self)

    def kv_get(self, key: str) -> Any:
        row = self.query_one("SELECT v FROM kv WHERE k=?", (key,))
        if not row:
            return None
        return json.loads(row["v"])

    def kv_set(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO kv(k,v,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), int(time.time() * 1000)),
        )
        self.commit()


class _Txn:
    def __init__(self, store: Store):
        self.store = store

    def __enter__(self):
        self.store._lock.acquire()
        return self.store

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.store._conn.commit()
            else:
                self.store._conn.rollback()
        finally:
            self.store._lock.release()
        return False


def open_store(path: str | Path) -> Store:
    return Store(path)
