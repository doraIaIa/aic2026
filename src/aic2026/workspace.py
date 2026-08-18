from __future__ import annotations

import csv
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkspaceError(ValueError):
    pass


_STATUSES = {"draft", "confirmed", "submitted"}
_TYPES = {"KIS", "QA", "TRAKE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceStore:
    """Notebook local persistence; frame_id luôn là competition-facing identity."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def migrate(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_entries(
                  id TEXT PRIMARY KEY, btc_stt TEXT, original_query TEXT NOT NULL, search_query TEXT NOT NULL,
                  query_type TEXT NOT NULL, video_id TEXT NOT NULL, timestamp_sec REAL NOT NULL, frame_id INTEGER NOT NULL,
                  answer_text TEXT, match_lanes_json TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL,
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_events(
                  history_id TEXT NOT NULL REFERENCES workspace_entries(id) ON DELETE CASCADE,
                  event_order INTEGER NOT NULL, video_id TEXT NOT NULL, timestamp_sec REAL NOT NULL, frame_id INTEGER NOT NULL,
                  PRIMARY KEY(history_id,event_order)
                );
                CREATE INDEX IF NOT EXISTS workspace_entries_type_status ON workspace_entries(query_type,status,updated_at DESC);
            """)

    @staticmethod
    def _validate(raw: dict[str, Any], *, entry_id: str | None = None) -> dict[str, Any]:
        required = {"btc_stt", "original_query", "search_query", "query_type", "video_id", "timestamp_sec", "frame_id", "answer_text", "match_lanes", "note", "status", "events"}
        unknown = set(raw) - required
        if unknown:
            raise WorkspaceError(f"Workspace field không hỗ trợ: {', '.join(sorted(unknown))}")
        missing = required - set(raw)
        if missing:
            raise WorkspaceError(f"Workspace thiếu field: {', '.join(sorted(missing))}")
        if raw["query_type"] not in _TYPES or raw["status"] not in _STATUSES:
            raise WorkspaceError("query_type hoặc status không hợp lệ")
        for key in ("original_query", "search_query", "video_id", "note"):
            if not isinstance(raw[key], str) or (key != "note" and not raw[key].strip()):
                raise WorkspaceError(f"{key} không hợp lệ")
        if type(raw["frame_id"]) is not int or raw["frame_id"] < 0 or not isinstance(raw["timestamp_sec"], (int, float)) or raw["timestamp_sec"] < 0:
            raise WorkspaceError("timestamp_sec/frame_id không hợp lệ")
        lanes = raw["match_lanes"]
        if not isinstance(lanes, list) or any(lane not in {"visual", "asr", "ocr", "object"} for lane in lanes):
            raise WorkspaceError("match_lanes không hợp lệ")
        events = raw["events"]
        if raw["query_type"] == "TRAKE":
            if not isinstance(events, list) or not events:
                raise WorkspaceError("TRAKE cần danh sách events không rỗng")
            orders = []
            for event in events:
                if not isinstance(event, dict) or set(event) != {"event_order", "video_id", "timestamp_sec", "frame_id"}:
                    raise WorkspaceError("TRAKE event không hợp lệ")
                if event["video_id"] != raw["video_id"] or type(event["event_order"]) is not int or type(event["frame_id"]) is not int:
                    raise WorkspaceError("TRAKE phải cùng video và dùng frame_id hợp lệ")
                orders.append(event["event_order"])
            if sorted(orders) != list(range(1, len(events) + 1)):
                raise WorkspaceError("TRAKE event_order phải liên tiếp từ 1")
        elif events not in ([], None):
            raise WorkspaceError("KIS/QA không nhận TRAKE events")
        return {**raw, "id": entry_id or str(uuid.uuid4()), "events": events or []}

    def save(self, raw: dict[str, Any], *, entry_id: str | None = None) -> dict[str, Any]:
        self.migrate()
        item = self._validate(raw, entry_id=entry_id)
        now = _now()
        with sqlite3.connect(self.database) as connection:
            if entry_id and connection.execute("SELECT 1 FROM workspace_entries WHERE id=?", (entry_id,)).fetchone() is None:
                raise WorkspaceError("Workspace entry không tồn tại")
            created = connection.execute("SELECT created_at FROM workspace_entries WHERE id=?", (item["id"],)).fetchone()
            connection.execute("""INSERT INTO workspace_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET btc_stt=excluded.btc_stt,original_query=excluded.original_query,search_query=excluded.search_query,query_type=excluded.query_type,video_id=excluded.video_id,timestamp_sec=excluded.timestamp_sec,frame_id=excluded.frame_id,answer_text=excluded.answer_text,match_lanes_json=excluded.match_lanes_json,note=excluded.note,status=excluded.status,updated_at=excluded.updated_at""",
                (item["id"], item["btc_stt"] or None, item["original_query"], item["search_query"], item["query_type"], item["video_id"], float(item["timestamp_sec"]), item["frame_id"], item["answer_text"] or None, json.dumps(item["match_lanes"]), item["note"], item["status"], created[0] if created else now, now))
            connection.execute("DELETE FROM workspace_events WHERE history_id=?", (item["id"],))
            connection.executemany("INSERT INTO workspace_events VALUES(?,?,?,?,?)", [(item["id"], event["event_order"], event["video_id"], event["timestamp_sec"], event["frame_id"]) for event in item["events"]])
        return self.get(item["id"])

    def get(self, entry_id: str) -> dict[str, Any]:
        self.migrate()
        with sqlite3.connect(self.database) as connection:
            row = connection.execute("SELECT * FROM workspace_entries WHERE id=?", (entry_id,)).fetchone()
            if row is None:
                raise WorkspaceError("Workspace entry không tồn tại")
            events = connection.execute("SELECT event_order,video_id,timestamp_sec,frame_id FROM workspace_events WHERE history_id=? ORDER BY event_order", (entry_id,)).fetchall()
        keys = ["id", "btc_stt", "original_query", "search_query", "query_type", "video_id", "timestamp_sec", "frame_id", "answer_text", "match_lanes_json", "note", "status", "created_at", "updated_at"]
        value = dict(zip(keys, row, strict=True)); value["match_lanes"] = json.loads(value.pop("match_lanes_json")); value["events"] = [dict(zip(("event_order", "video_id", "timestamp_sec", "frame_id"), event, strict=True)) for event in events]
        return value

    def list(self, query: str = "") -> list[dict[str, Any]]:
        self.migrate()
        with sqlite3.connect(self.database) as connection:
            ids = [row[0] for row in connection.execute("SELECT id FROM workspace_entries WHERE original_query LIKE ? OR btc_stt LIKE ? ORDER BY updated_at DESC", (f"%{query}%", f"%{query}%"))]
        return [self.get(item_id) for item_id in ids]

    def delete(self, entry_id: str) -> None:
        self.migrate()
        with sqlite3.connect(self.database) as connection:
            connection.execute("DELETE FROM workspace_events WHERE history_id=?", (entry_id,))
            if connection.execute("DELETE FROM workspace_entries WHERE id=?", (entry_id,)).rowcount != 1:
                raise WorkspaceError("Workspace entry không tồn tại")

    def export(self, fmt: str) -> str:
        items = self.list()
        if fmt == "json":
            return json.dumps(items, ensure_ascii=False, indent=2)
        if fmt != "csv":
            raise WorkspaceError("export format chỉ hỗ trợ json/csv")
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=["id", "btc_stt", "query_type", "video_id", "frame_id", "answer_text", "status", "events"]); writer.writeheader()
        for item in items:
            writer.writerow({key: json.dumps(item[key], ensure_ascii=False) if key == "events" else item.get(key) for key in writer.fieldnames})
        return stream.getvalue()
