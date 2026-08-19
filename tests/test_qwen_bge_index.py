"""Unit tests for Qwen BGE semantic document serialization and index logic (M5B)."""
import json
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest
from aic2026.retrieval.qwen_bge_index import (
    DOCUMENT_POLICY_ID,
    QwenBgeIndex,
    serialize_qwen_semantic_core_v1,
)


def test_serialize_qwen_semantic_core_v1():
    # Full row
    mock_row = {
        "caption": "A person riding a motorcycle on street.",
        "objects_json": '["motorcycle", "person"]',
        "attributes_json": '["red motorcycle", "black jacket"]',
        "scene_json": '["city street"]',
        "visible_actions_json": '["riding", "turning"]',
        "spatial_relations_json": '["person is on motorcycle"]',
        "counts_json": '["one person", "one motorcycle"]',
    }
    doc = serialize_qwen_semantic_core_v1(mock_row)

    assert "caption: A person riding a motorcycle on street." in doc
    assert "objects: motorcycle; person" in doc
    assert "attributes: red motorcycle; black jacket" in doc
    assert "scene: city street" in doc
    assert "visible actions: riding; turning" in doc
    # Relations and counts must be excluded in V1
    assert "person is on motorcycle" not in doc
    assert "one person" not in doc


def test_serialize_qwen_semantic_core_v1_empty_and_partial():
    # Empty row
    mock_empty = {
        "caption": "",
        "objects_json": "[]",
        "attributes_json": "[]",
        "scene_json": "[]",
        "visible_actions_json": "[]",
        "spatial_relations_json": "[]",
        "counts_json": "[]",
    }
    assert serialize_qwen_semantic_core_v1(mock_empty) == ""

    # Caption only
    mock_cap_only = {
        "caption": "Solo caption only.",
        "objects_json": "[]",
        "attributes_json": "[]",
        "scene_json": "[]",
        "visible_actions_json": "[]",
    }
    assert serialize_qwen_semantic_core_v1(mock_cap_only) == "caption: Solo caption only."


def test_qwen_bge_index_runtime_wrapper():
    import faiss

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        faiss_file = tmp_path / "qwen_bge.faiss"
        rowmap_file = tmp_path / "qwen_bge_rowmap.jsonl"
        passport_file = tmp_path / "qwen_bge_passport.json"

        # Create mock FAISS IndexFlatIP with 5 vectors
        dim = 1024
        index = faiss.IndexFlatIP(dim)
        vecs = np.random.randn(5, dim).astype(np.float32)
        # Normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs = vecs / norms
        index.add(vecs)
        faiss.write_index(index, str(faiss_file))

        # Write rowmap
        rowmap_entries = [
            {
                "dense_row": i,
                "keyframe_uid": f"CUSTOM:L21_V001:F{i*100}",
                "video_id": "L21_V001" if i < 3 else "L21_V002",
                "frame_idx": i * 100,
                "timestamp_ms": i * 4000,
                "document_policy_id": DOCUMENT_POLICY_ID,
                "document_sha256": f"dummy_sha_{i}",
                "caption": f"Sample caption {i}",
            }
            for i in range(5)
        ]
        with open(rowmap_file, "w", encoding="utf-8") as f:
            for r in rowmap_entries:
                f.write(json.dumps(r) + "\n")

        with open(passport_file, "w", encoding="utf-8") as f:
            json.dump({"status": "PASS", "index_rows": 5}, f)

        # Test index wrapper
        qwen_idx = QwenBgeIndex(tmp_path)
        assert qwen_idx.total_rows == 5

        # Query with vector 0 -> should return row 0 as rank 1 with score ~1.0
        q_vec = vecs[0:1]
        results = qwen_idx.search(q_vec, top_k=3)
        assert len(results) == 3
        assert results[0][0]["dense_row"] == 0
        assert pytest.approx(results[0][1], rel=1e-4) == 1.0

        # Test candidate video scoping
        scoped_results = qwen_idx.search(q_vec, top_k=5, candidate_video_ids=["L21_V002"])
        assert len(scoped_results) == 2
        assert all(r[0]["video_id"] == "L21_V002" for r in scoped_results)
