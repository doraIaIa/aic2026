from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from aic2026.search.api import create_server


def _database(path: Path) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE videos(video_id TEXT PRIMARY KEY, relpath TEXT NOT NULL);
            CREATE TABLE asr_segments(
                segment_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                text TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'vi',
                model TEXT NOT NULL DEFAULT 'medium'
            );
            CREATE VIRTUAL TABLE asr_segments_fts USING fts5(
                text,
                content='asr_segments',
                content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER asr_segments_ai AFTER INSERT ON asr_segments BEGIN
                INSERT INTO asr_segments_fts(rowid, text) VALUES (new.rowid, new.text);
            END;
            INSERT INTO videos(video_id, relpath) VALUES
                ('V1', 'video/V1.mp4'),
                ('V2', 'video/V2.mp4');
            INSERT INTO asr_segments(segment_id, video_id, start_sec, end_sec, text) VALUES
                ('V1:000001', 'V1', 1.0, 3.0, 'Chào mừng quý vị đến với 60 giây'),
                ('V2:000001', 'V2', 4.0, 8.0, 'Tin tức thành phố Hồ Chí Minh');
            """
        )
        connection.commit()
    return path


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_asr_search_api_health_search_filter_and_validation(tmp_path: Path) -> None:
    server = create_server(_database(tmp_path / "aic.sqlite"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = _get_json(f"{base_url}/api/health")
        assert status == 200
        assert health["status"] == "OK"

        status, capabilities = _get_json(f"{base_url}/api/v1/capabilities")
        assert status == 200
        assert capabilities["contract_version"] == "retrieval.v1"
        assert capabilities["providers"]["asr"]["status"] == "OK"
        assert capabilities["providers"]["visual"]["status"] == "UNAVAILABLE"
        assert capabilities["providers"]["ocr"]["status"] == "UNAVAILABLE"
        assert capabilities["providers"]["object"]["status"] == "UNAVAILABLE"
        assert capabilities["media"]["status"] == "MEDIA_UNAVAILABLE"

        status, payload = _get_json(f"{base_url}/api/asr/search?q=thanh%20pho&limit=5")
        assert status == 200
        assert payload["count"] == 1
        assert payload["results"][0]["segment_id"] == "V2:000001"
        assert payload["results"][0]["source_video_path"] == "video/V2.mp4"

        status, payload = _get_json(
            f"{base_url}/api/asr/search?q=ch%C3%A0o&video_id=V2"
        )
        assert status == 200
        assert payload["count"] == 0

        status, payload = _get_json(f"{base_url}/api/asr/search?q=&limit=5")
        assert status == 400
        assert payload["status"] == "ERROR"

        status, payload = _get_json(f"{base_url}/api/asr/search?q=test&limit=101")
        assert status == 400
        assert "between 1 and 100" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
