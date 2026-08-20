"""Unit tests for Qwen BM25 Benchmark Runner (M5B1)."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.evaluation.qwen_bm25_benchmark import run_qwen_bm25_benchmark


@pytest.fixture
def mock_benchmark_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "mapping.sqlite"
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        out_dir = tmp_path / "out"

        # 1. Mock SQLite mapping with qwen_caption_fts
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE qwen_frames (
                keyframe_uid TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                raw_pts_time REAL NOT NULL,
                objects_json TEXT NOT NULL DEFAULT '[]',
                attributes_json TEXT NOT NULL DEFAULT '[]',
                spatial_relations_json TEXT NOT NULL DEFAULT '[]',
                counts_json TEXT NOT NULL DEFAULT '[]',
                scene_json TEXT NOT NULL DEFAULT '[]',
                visible_actions_json TEXT NOT NULL DEFAULT '[]',
                caption TEXT NOT NULL DEFAULT '',
                semantic_status TEXT NOT NULL DEFAULT 'OK',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE qwen_caption_fts USING fts5(
                keyframe_uid UNINDEXED,
                video_id UNINDEXED,
                caption_raw,
                caption_norm,
                caption_accentless,
                tokenize = 'unicode61'
            );
        """)

        # Insert canonical count dummy rows (or override for test)
        for i in range(116767):
            conn.execute(
                "INSERT INTO qwen_frames (keyframe_uid, video_id, frame_idx, timestamp_ms, raw_pts_time, caption) VALUES (?, ?, ?, ?, ?, ?)",
                (f"CUSTOM:L21_V001:F{i}", "L21_V001", i, i * 100, i * 0.1, "người đi xe máy trên đường" if i == 0 else "cảnh thiên nhiên"),
            )
            conn.execute(
                "INSERT INTO qwen_caption_fts (keyframe_uid, video_id, caption_raw, caption_norm, caption_accentless) VALUES (?, ?, ?, ?, ?)",
                (f"CUSTOM:L21_V001:F{i}", "L21_V001", "người đi xe máy trên đường" if i == 0 else "cảnh thiên nhiên", "nguoi di xe may tren duong" if i == 0 else "canh thien nhien", "nguoi di xe may tren duong" if i == 0 else "canh thien nhien"),
            )
        conn.commit()
        conn.close()

        # 2. Mock dataset manifest
        manifest_file = dataset_dir / "query_manifest.jsonl"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": "Q01", "query_text": "xe máy", "split": "DEV"}) + "\n")
            f.write(json.dumps({"query_id": "Q02", "query_text": "thiên nhiên", "split": "DEV"}) + "\n")

        yield db_path, dataset_dir, out_dir


def test_qwen_bm25_benchmark_runner(mock_benchmark_env):
    db_path, dataset_dir, out_dir = mock_benchmark_env
    summary = run_qwen_bm25_benchmark(db_path, dataset_dir, out_dir, split="DEV", top_k=5)

    assert summary["lane_id"] == "qwen_bm25"
    assert summary["query_count"] == 2
    assert summary["scored_query_count"] == 0
    assert summary["unscored_query_count"] == 2
    assert summary["quality_evaluation_status"] == "BLOCKED_BY_GROUND_TRUTH"

    summary_file = out_dir / "benchmark_summary.json"
    results_file = out_dir / "per_query_results.json"
    assert summary_file.exists()
    assert results_file.exists()

    with open(results_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    assert len(results) == 2
    assert results[0]["query_id"] == "Q01"
    assert results[0]["hit_count"] > 0
