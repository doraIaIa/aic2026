import sqlite3
from pathlib import Path


def test_schema_and_fts_triggers(tmp_path: Path):
    db = tmp_path / "aic.sqlite"
    schema = (Path(__file__).parents[1] / "src" / "aic2026" / "db" / "schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(db) as conn:
        conn.executescript(schema)
        conn.execute("INSERT INTO videos(video_id, relpath) VALUES (?, ?)", ("V1", "Videos/V1.mp4"))
        conn.execute(
            "INSERT INTO transcripts(video_id,start_sec,end_sec,text_raw,text_norm,model_name) VALUES (?,?,?,?,?,?)",
            ("V1", 1.0, 2.0, "Xin chào", "xin chào", "demo"),
        )
        rows = conn.execute("SELECT rowid, text_norm FROM transcripts_fts WHERE transcripts_fts MATCH 'xin'").fetchall()
        assert rows
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
