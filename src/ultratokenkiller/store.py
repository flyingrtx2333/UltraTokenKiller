from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  kind TEXT NOT NULL,
  client TEXT NOT NULL,
  model TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cached_tokens INTEGER,
  saved_tokens INTEGER,
  duration_ms INTEGER,
  success INTEGER NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_created_at ON events(created_at);
CREATE UNIQUE INDEX IF NOT EXISTS events_external_id ON events(kind, json_extract(metadata, '$.external_id'))
  WHERE json_extract(metadata, '$.external_id') IS NOT NULL;
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, *, kind: str, client: str, success: bool, **values: Any) -> int:
        columns = ["created_at", "kind", "client", "success"]
        data: list[Any] = [time.time(), kind, client, int(success)]
        for key in ("model", "input_tokens", "output_tokens", "cached_tokens", "saved_tokens", "duration_ms"):
            if key in values:
                columns.append(key)
                data.append(values[key])
        columns.append("metadata")
        data.append(json.dumps(values.get("metadata", {}), ensure_ascii=False))
        marks = ",".join("?" for _ in data)
        with self.connect() as db:
            cursor = db.execute(f"INSERT OR IGNORE INTO events ({','.join(columns)}) VALUES ({marks})", data)
            return int(cursor.lastrowid or 0)

    def prune(self, days: int) -> int:
        cutoff = time.time() - days * 86400
        with self.connect() as db:
            cursor = db.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
            return cursor.rowcount

    def summary(self, since_hours: int = 24, client: str | None = None, model: str | None = None) -> dict[str, Any]:
        where = ["created_at >= ?"]
        args: list[Any] = [time.time() - since_hours * 3600]
        if client:
            where.append("client = ?")
            args.append(client)
        if model:
            where.append("model = ?")
            args.append(model)
        predicate = " AND ".join(where)
        query = f"""SELECT COUNT(*) requests,
          SUM(input_tokens) input_tokens,
          SUM(output_tokens) output_tokens,
          SUM(cached_tokens) cached_tokens,
          SUM(CASE WHEN kind IN ('input','headroom') THEN 1 ELSE 0 END) model_requests,
          SUM(CASE WHEN kind IN ('tool','rtk') THEN 1 ELSE 0 END) tool_commands,
          SUM(CASE WHEN kind IN ('input','headroom') AND input_tokens IS NOT NULL THEN 1 ELSE 0 END) known_input_usage,
          SUM(CASE WHEN kind='tool' AND json_extract(metadata, '$.filter') IS NOT NULL THEN 1 ELSE 0 END) tool_eligible,
          SUM(CASE WHEN kind='tool' AND json_extract(metadata, '$.optimized')=1 THEN 1 ELSE 0 END) tool_optimized,
          COALESCE(SUM(CASE WHEN kind IN ('rtk','tool') THEN saved_tokens ELSE 0 END),0) rtk_saved_tokens,
          COALESCE(SUM(CASE WHEN kind IN ('headroom','input') THEN saved_tokens ELSE 0 END),0) headroom_saved_tokens,
          COALESCE(AVG(duration_ms),0) average_duration_ms,
          COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),0) failures
          FROM events WHERE {predicate}"""
        with self.connect() as db:
            row = dict(db.execute(query, args).fetchone())
        row["error_rate"] = row["failures"] / row["requests"] if row["requests"] else 0
        row["input_saved_tokens"] = row["headroom_saved_tokens"]
        row["tool_saved_tokens"] = row["rtk_saved_tokens"]
        for key in ("model_requests", "tool_commands", "known_input_usage", "tool_eligible", "tool_optimized"):
            row[key] = row[key] or 0
        return row

    def events(self, limit: int = 100, *, since_hours: int | None = None, kinds: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        conditions = []
        args = []
        if since_hours is not None:
            conditions.append("created_at >= ?")
            args.append(time.time() - since_hours * 3600)
        if kinds:
            conditions.append("kind IN (" + ",".join("?" for _ in kinds) + ")")
            args.extend(kinds)
        predicate = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events" + predicate + " ORDER BY created_at DESC LIMIT ?", (*args, min(limit, 500))
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            item["success"] = bool(item["success"])
            result.append(item)
        return result
