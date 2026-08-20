from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from pathlib import Path

from aic2026.search.api import AsrSearchApi, _sanitize_public_payload


def _make_taxonomy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE videos(video_id TEXT PRIMARY KEY)")
    conn.execute(
        """
        CREATE TABLE taxonomy_nodes(
            branch_id TEXT PRIMARY KEY,
            branch_type TEXT NOT NULL,
            label_vi TEXT NOT NULL,
            label_en TEXT NOT NULL,
            aliases_json TEXT NOT NULL,
            parent_ids_json TEXT NOT NULL,
            requires_region_index INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE video_memberships(
            membership_id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            membership_type TEXT NOT NULL,
            status TEXT NOT NULL,
            confidence REAL,
            score_type TEXT,
            evidence TEXT
        )
        """
    )
    for vid in ["L21_V001", "L21_V002", "L25_V001"]:
        conn.execute("INSERT INTO videos(video_id) VALUES (?)", (vid,))
    nodes = [
        ("program/news", "PROGRAM", "Bản tin / Thời sự", "News", ["60 giây"], [], 1),
        ("program/education/exam-prep", "PROGRAM", "Giáo dục / Ôn thi THPT", "Education", ["ôn thi"], [], 0),
        (
            "subject/education/literature",
            "SUBJECT",
            "Môn Ngữ văn",
            "Literature",
            ["ngữ văn"],
            ["program/education/exam-prep"],
            0,
        ),
    ]
    for branch_id, branch_type, label_vi, label_en, aliases, parents, requires_region in nodes:
        conn.execute(
            """
            INSERT INTO taxonomy_nodes(
                branch_id, branch_type, label_vi, label_en,
                aliases_json, parent_ids_json, requires_region_index, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                branch_id,
                branch_type,
                label_vi,
                label_en,
                json.dumps(aliases, ensure_ascii=False),
                json.dumps(parents, ensure_ascii=False),
                requires_region,
            ),
        )
    memberships = [
        ("m1", "L21_V001", "program/news", "PRIMARY_PROGRAM"),
        ("m2", "L21_V002", "program/news", "PRIMARY_PROGRAM"),
        ("m3", "L25_V001", "program/education/exam-prep", "PRIMARY_PROGRAM"),
        ("m4", "L25_V001", "subject/education/literature", "SUBJECT"),
    ]
    for membership_id, video_id, branch_id, membership_type in memberships:
        conn.execute(
            """
            INSERT INTO video_memberships(
                membership_id, video_id, branch_id, membership_type,
                status, confidence, score_type, evidence
            )
            VALUES (?, ?, ?, ?, 'VERIFIED', 1.0, 'test', 'test')
            """,
            (membership_id, video_id, branch_id, membership_type),
        )
    conn.commit()
    conn.close()


def test_taxonomy_endpoint_returns_canonical_scopes(tmp_path: Path):
    db_path = tmp_path / "mapping.sqlite"
    _make_taxonomy_db(db_path)

    api = AsrSearchApi(db_path)
    status, payload = api.taxonomy()

    assert status == HTTPStatus.OK
    assert payload["status"] == "OK"
    assert payload["global_count"] == 3
    assert len(payload["programs"]) == 2
    assert len(payload["topics"]) == 1

    news = next(item for item in payload["programs"] if item["branch_id"] == "program/news")
    assert news["count"] == 2
    assert news["video_ids"] == ["L21_V001", "L21_V002"]

    literature = payload["topics"][0]
    assert literature["parent_ids"] == ["program/education/exam-prep"]
    assert literature["video_ids"] == ["L25_V001"]


def test_public_payload_sanitizer_removes_absolute_paths():
    payload = {
        "provenance": {"db_path": r"F:\AIC_WORK\artifacts\runtime\mapping.sqlite"},
        "hits": [{"safe": "L25_V001", "nested": [r"\\server\share\private.mp4"]}],
    }

    sanitized = _sanitize_public_payload(payload)

    assert sanitized["provenance"]["db_path"] == "[redacted-local-path]"
    assert sanitized["hits"][0]["nested"][0] == "[redacted-local-path]"
    assert sanitized["hits"][0]["safe"] == "L25_V001"
