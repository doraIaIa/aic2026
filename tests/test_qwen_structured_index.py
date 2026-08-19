"""Unit tests for Qwen Structured Index and Normalization (M5A)."""
import sqlite3
import tempfile
from pathlib import Path

import pytest
from aic2026.retrieval.qwen_structured_index import (
    CANONICAL_CUSTOM_FRAME_COUNT,
    CANONICAL_QWEN_ROW_COUNT,
    VALID_NAMESPACES,
    build_qwen_structured_index,
    normalize_facet_phrase,
    to_accentless,
)


def test_normalization_deterministic():
    assert normalize_facet_phrase("  Motorcycle  ") == "motorcycle"
    assert normalize_facet_phrase("GREEN SHIRT") == "green shirt"
    assert normalize_facet_phrase('"riding a bicycle"') == "riding a bicycle"
    assert normalize_facet_phrase("multiple  cars,  on  street") == "multiple cars, on street"
    assert normalize_facet_phrase("") == ""
    assert normalize_facet_phrase("   ") == ""


def test_accentless_derivation():
    assert to_accentless("xe máy") == "xe may"
    assert to_accentless("đường phố") == "duong pho"
    assert to_accentless("Áo đỏ") == "Ao do"
    assert to_accentless("motorcycle") == "motorcycle"


def test_valid_namespaces():
    expected = {"object", "attribute", "relation", "count", "scene", "action"}
    assert VALID_NAMESPACES == expected


def test_build_qwen_structured_index_mock_fixture():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        mock_mapping = tmp_path / "mapping.sqlite"
        out_dir = tmp_path / "index_out"

        conn = sqlite3.connect(mock_mapping)
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
        """)

        # Insert a sample of rows
        rows = [
            (
                f"CUSTOM:L21_V001:F{i}", "L21_V001", i, i * 1000, float(i),
                '["motorcycle", "car"]' if i % 2 == 0 else '["person"]',
                '["red color"]' if i % 2 == 0 else '["blue shirt"]',
                '["car is next to motorcycle"]' if i % 2 == 0 else '[]',
                '["one motorcycle", "one car"]' if i % 2 == 0 else '["one person"]',
                '["city street"]' if i % 2 == 0 else '["indoor hallway"]',
                '["riding"]' if i % 2 == 0 else '["walking"]',
                f"Caption for frame {i}", "OK",
            )
            for i in range(10)
        ]
        conn.executemany("INSERT INTO qwen_frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", rows)
        conn.commit()

        # Build index with custom row count patch
        from aic2026.retrieval import qwen_structured_index
        orig_count = qwen_structured_index.CANONICAL_QWEN_ROW_COUNT
        try:
            qwen_structured_index.CANONICAL_QWEN_ROW_COUNT = 10
            passport = build_qwen_structured_index(mock_mapping, out_dir)
            assert passport["status"] == "OK"
            assert passport["frame_registry_rows"] == 10
            assert passport["total_unique_facets"] > 0
            assert (out_dir / "qwen_facets.sqlite").exists()
            assert (out_dir / "vocabulary_audit.json").exists()
            assert (out_dir / "DONE.json").exists()
        finally:
            qwen_structured_index.CANONICAL_QWEN_ROW_COUNT = orig_count
        conn.close()
