"""Unit tests for SigLIP index integrity and artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

INDEX_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\siglip_custom_v1")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.mark.skipif(not (INDEX_DIR / "DONE.json").exists(), reason="Production SigLIP index not built")
class TestProductionSigLIPIndex:
    """Test production SigLIP index artifacts and invariants."""

    def test_done_marker(self):
        done_path = INDEX_DIR / "DONE.json"
        assert done_path.is_file()
        done = json.loads(done_path.read_text(encoding="utf-8"))
        assert done["task"] == "siglip_faiss_index"
        assert done["schema_version"] == 1
        assert done["row_count"] == 116767
        assert done["dimension"] == 768
        assert done["metric"] == "INNER_PRODUCT"
        assert done["status"] == "READY"

    def test_passport(self):
        passport_path = INDEX_DIR / "siglip_custom_passport.json"
        assert passport_path.is_file()
        passport = json.loads(passport_path.read_text(encoding="utf-8"))
        assert passport["model_id"] == "google/siglip2-base-patch16-224"
        assert passport["dimension"] == 768
        assert passport["row_count"] == 116767
        assert passport["frame_space"] == "CUSTOM"
        assert passport["nan_rows"] == 0
        assert passport["inf_rows"] == 0
        assert passport["duplicate_keyframe_uids"] == 0
        assert passport["videos_covered"] == 873
        assert passport["vector_norms"]["min"] == 1.0
        assert passport["vector_norms"]["max"] == 1.0

    def test_checksums(self):
        done = json.loads((INDEX_DIR / "DONE.json").read_text(encoding="utf-8"))
        index_path = INDEX_DIR / done["index_file"]
        rowmap_path = INDEX_DIR / done["rowmap_file"]

        assert _sha256(index_path) == done["index_sha256"]
        assert _sha256(rowmap_path) == done["rowmap_sha256"]

    def test_rowmap_invariants(self):
        rowmap_path = INDEX_DIR / "siglip_custom_rowmap.jsonl"
        assert rowmap_path.is_file()

        seen_uids: set[str] = set()
        count = 0
        with open(rowmap_path, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                uid = entry["keyframe_uid"]
                assert uid.startswith("CUSTOM:"), f"Non-CUSTOM uid: {uid}"
                assert uid not in seen_uids, f"Duplicate uid: {uid}"
                seen_uids.add(uid)
                assert entry["faiss_row"] == count
                assert entry["frame_idx"] >= 0
                assert entry["timestamp_ms"] >= 0
                count += 1

        assert count == 116767
