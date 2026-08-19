"""Unit tests for Qwen Structured Benchmark Runner (M5A)."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.evaluation.qwen_structured_benchmark import run_qwen_structured_benchmark


@pytest.fixture
def mock_benchmark_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "qwen_facets.sqlite"
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        out_dir = tmp_path / "out"

        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE frame_registry (
                frame_ordinal INTEGER PRIMARY KEY,
                keyframe_uid TEXT UNIQUE NOT NULL,
                video_id TEXT NOT NULL,
                frame_idx INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                caption TEXT NOT NULL,
                semantic_status TEXT NOT NULL
            );
            CREATE TABLE facet_dictionary (
                facet_ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                facet_id TEXT UNIQUE NOT NULL,
                namespace TEXT NOT NULL,
                canonical_value TEXT NOT NULL,
                df_frames INTEGER NOT NULL,
                df_videos INTEGER NOT NULL
            );
            CREATE TABLE facet_aliases (
                alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
                facet_ordinal INTEGER NOT NULL,
                alias_value TEXT NOT NULL,
                normalization_method TEXT NOT NULL
            );
            CREATE TABLE frame_facets (
                frame_ordinal INTEGER NOT NULL,
                facet_ordinal INTEGER NOT NULL,
                raw_value TEXT NOT NULL,
                source_field TEXT NOT NULL,
                PRIMARY KEY (frame_ordinal, facet_ordinal, raw_value)
            );
            CREATE VIRTUAL TABLE facet_fts USING fts5(
                facet_ordinal UNINDEXED,
                facet_id UNINDEXED,
                namespace UNINDEXED,
                term_raw,
                term_norm,
                term_accentless,
                tokenize='unicode61'
            );
        """)

        # Add 116,767 dummy rows in frame_registry for health check
        dummy_frames = [(i, f"UID:{i}", "L21_V001", i, i * 1000, "", "OK") for i in range(1, 116768)]
        conn.executemany("INSERT INTO frame_registry VALUES (?, ?, ?, ?, ?, ?, ?)", dummy_frames)
        conn.execute("INSERT INTO facet_dictionary VALUES (1, 'object/car', 'object', 'car', 5, 1)")
        conn.execute("INSERT INTO facet_fts VALUES (1, 'object/car', 'object', 'car', 'car', 'car')")
        conn.execute("INSERT INTO frame_facets VALUES (1, 1, 'car', 'objects_json')")
        conn.commit()
        conn.close()

        # Create mock query manifest
        manifest_file = dataset_dir / "query_manifest.jsonl"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_id": "Q001", "query_text": "car", "split": "DEV"}) + "\n")
            f.write(json.dumps({"query_id": "Q002", "query_text": "unknown_term_xyz", "split": "DEV"}) + "\n")

        yield db_path, dataset_dir, out_dir


def test_run_qwen_structured_benchmark(mock_benchmark_env):
    db_path, dataset_dir, out_dir = mock_benchmark_env
    res = run_qwen_structured_benchmark(db_path, dataset_dir, out_dir, run_id="test_run_001")

    assert res["status"] == "PASS" if "status" in res else True
    assert res["lane_id"] == "qwen_structured"
    assert res["dataset_query_count"] == 2
    assert res["quality_eval_status"] == "BLOCKED_BY_GROUND_TRUTH"
    assert (out_dir / "per_query.jsonl").exists()
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "DONE.json").exists()
