from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest

from aic2026.retrieval.capabilities import CapabilityService
from aic2026.retrieval.clip_faiss import stable_embedding_id
from aic2026.retrieval.providers import AsrProvider, ProviderQuery, VisualProvider, measure_provider_search
from aic2026.retrieval.providers.base import ProviderUnavailableError


def _asr_database(path: Path) -> Path:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE videos(video_id TEXT PRIMARY KEY, relpath TEXT NOT NULL);
            CREATE TABLE asr_segments(
                segment_id TEXT PRIMARY KEY, video_id TEXT NOT NULL,
                start_sec REAL NOT NULL, end_sec REAL NOT NULL, text TEXT NOT NULL,
                language TEXT NOT NULL, model TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE asr_segments_fts USING fts5(
                text, content='asr_segments', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TRIGGER asr_segments_ai AFTER INSERT ON asr_segments BEGIN
                INSERT INTO asr_segments_fts(rowid, text) VALUES (new.rowid, new.text);
            END;
            INSERT INTO videos VALUES ('V1', 'video/V1.mp4'), ('V2', 'video/V2.mp4');
            INSERT INTO asr_segments VALUES
              ('V1:000001', 'V1', 1.0, 3.0, 'Chào mừng quý vị đến thành phố', 'vi', 'medium'),
              ('V2:000001', 'V2', 4.0, 8.0, 'Tin tức thành phố Hồ Chí Minh', 'vi', 'medium');
            """
        )
        connection.commit()
    return path


class FakeIndex:
    d = 2
    ntotal = 2

    def __init__(self, ids: list[int]):
        self.ids = ids
        self.calls = 0

    def search(self, vector, top_k):
        self.calls += 1
        ids = np.asarray([self.ids[:top_k]], dtype=np.int64)
        scores = np.asarray([[0.9, 0.8][:top_k]], dtype=np.float32)
        return scores, ids


def _visual_artifact(tmp_path: Path) -> tuple[Path, list[dict]]:
    root = tmp_path / "clip-faiss-btc-v1"
    root.mkdir(parents=True)
    index_path = root / "clip.index"
    index_path.write_bytes(b"synthetic-faiss")
    rows = [
        {"embedding_id": stable_embedding_id("V1:1"), "keyframe_id": "V1:1", "video_id": "V1", "csv_n": 1, "clip_row": 0, "frame_idx": 0, "pts_time": 0.0, "keyframe_relpath": "data_extracted/keyframes/V1/001.jpg"},
        {"embedding_id": stable_embedding_id("V1:2"), "keyframe_id": "V1:2", "video_id": "V1", "csv_n": 2, "clip_row": 1, "frame_idx": 75, "pts_time": 3.0, "keyframe_relpath": "data_extracted/keyframes/V1/002.jpg"},
    ]
    metadata_path = root / "metadata.jsonl"
    metadata_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    marker = {"schema_version": 1, "task": "clip_faiss_index", "index_file": "clip.index", "metadata_file": "metadata.jsonl", "index_sha256": sha(index_path), "metadata_sha256": sha(metadata_path), "expected_count": 2, "processed_count": 2, "vector_dim": 2, "metric": "cosine_via_normalized_inner_product", "model": "btc-provided-clip-features-32", "model_revision": "unknown-not-present-in-source"}
    (root / "DONE.json").write_text(json.dumps(marker), encoding="utf-8")
    return root, rows


def test_asr_provider_typed_output_no_diacritic_and_phrase(tmp_path: Path):
    provider = AsrProvider(_asr_database(tmp_path / "aic.sqlite"))
    capability = provider.capabilities()
    assert capability.status == "OK"
    assert capability.counts == {"videos": 2, "segments": 2, "fts_rows": 2}
    plain = provider.search(ProviderQuery("thanh pho", top_k=10))
    phrase = provider.search(ProviderQuery('"chào mừng quý vị"', top_k=10))
    assert plain and phrase[0].evidence_id == "V1:000001"
    assert plain[0].score_kind == "bm25_lower_is_better"
    assert plain[0].payload["model"] == "medium"
    assert plain[0].source_video_relpath == "video/V1.mp4"


def test_asr_product_query_treats_raw_fts_as_literals(tmp_path: Path):
    provider = AsrProvider(_asr_database(tmp_path / "aic.sqlite"))
    assert provider.search(ProviderQuery("thành OR phố*")) == []


def test_visual_provider_mapping_stable_ids_top_k_and_cache(tmp_path: Path):
    root, rows = _visual_artifact(tmp_path)
    fake_index = FakeIndex([row["embedding_id"] for row in rows])
    loads = {"index": 0, "encoder": 0}

    def load_index(path):
        loads["index"] += 1
        return fake_index

    def load_encoder():
        loads["encoder"] += 1
        return lambda text: np.asarray([1.0, 0.0], dtype=np.float32)

    provider = VisualProvider(root, index_loader=load_index, encoder_loader=load_encoder)
    first = provider.search(ProviderQuery("xe đạp", top_k=1))
    second = provider.search(ProviderQuery("người đi bộ", top_k=2))
    assert loads == {"index": 1, "encoder": 1}
    assert provider.load_count == 1 and len(first) == 1 and len(second) == 2
    assert first[0].evidence_id == "V1:1"
    assert first[0].payload == {"embedding_id": rows[0]["embedding_id"], "keyframe_id": "V1:1", "csv_n": 1, "clip_row": 0, "frame_idx": 0, "pts_time": 0.0, "keyframe_relpath": "data_extracted/keyframes/V1/001.jpg"}
    assert second[1].payload["frame_idx"] == 75
    assert second[1].payload["keyframe_relpath"].endswith("/002.jpg")
    assert second[0].score_kind == "cosine_ip_higher_is_better"
    with pytest.raises(ValueError, match="1..100"):
        ProviderQuery("x", top_k=101)


def test_visual_encoding_and_faiss_search_are_serialized(tmp_path: Path):
    root, rows = _visual_artifact(tmp_path)
    active = 0
    maximum = 0
    guard = threading.Lock()

    def encode(text):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return np.asarray([1.0, 0.0], dtype=np.float32)

    provider = VisualProvider(root, index_loader=lambda path: FakeIndex([row["embedding_id"] for row in rows]), encoder_loader=lambda: encode)
    threads = [threading.Thread(target=provider.search, args=(ProviderQuery(f"q-{index}"),)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert maximum == 1
    assert provider.load_count == 1


def test_search_measurement_keeps_latency_separate_from_raw_score(tmp_path: Path):
    provider = AsrProvider(_asr_database(tmp_path / "aic.sqlite"))
    result = measure_provider_search(provider, ProviderQuery("thành phố"))
    assert result.provider == "asr" and result.latency_ms >= 0
    assert result.hits[0].score_kind == "bm25_lower_is_better"


def test_visual_checksum_mapping_and_model_failure_are_lane_local(tmp_path: Path):
    root, rows = _visual_artifact(tmp_path)
    (root / "metadata.jsonl").write_text("tampered", encoding="utf-8")
    provider = VisualProvider(root, index_loader=lambda path: FakeIndex([]), encoder_loader=lambda: lambda text: np.ones(2))
    assert provider.capabilities().status == "INTEGRITY_ERROR"

    missing = VisualProvider(tmp_path / "missing", index_loader=lambda path: FakeIndex([]), encoder_loader=lambda: lambda text: np.ones(2))
    assert missing.capabilities().status == "UNAVAILABLE"

    model_root, model_rows = _visual_artifact(tmp_path / "model")
    model_provider = VisualProvider(model_root, index_loader=lambda path: FakeIndex([row["embedding_id"] for row in model_rows]), encoder_loader=lambda: (_ for _ in ()).throw(ProviderUnavailableError("MODEL_MISSING")))
    assert model_provider.capabilities().status == "UNAVAILABLE"


def test_visual_index_checksum_and_locked_mapping_fail_closed(tmp_path: Path):
    checksum_root, checksum_rows = _visual_artifact(tmp_path / "checksum")
    (checksum_root / "clip.index").write_bytes(b"tampered-index")
    checksum_provider = VisualProvider(checksum_root, index_loader=lambda path: FakeIndex([]), encoder_loader=lambda: lambda text: np.ones(2))
    assert checksum_provider.capabilities().status == "INTEGRITY_ERROR"
    assert "INDEX_CHECKSUM" in checksum_provider.capabilities().reason

    mapping_root, mapping_rows = _visual_artifact(tmp_path / "mapping")
    mapping_rows[0]["clip_row"] = 1
    metadata_path = mapping_root / "metadata.jsonl"
    metadata_path.write_text("".join(json.dumps(row) + "\n" for row in mapping_rows), encoding="utf-8")
    marker_path = mapping_root / "DONE.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["metadata_sha256"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    mapping_provider = VisualProvider(mapping_root, index_loader=lambda path: FakeIndex([]), encoder_loader=lambda: lambda text: np.ones(2))
    assert mapping_provider.capabilities().status == "INTEGRITY_ERROR"
    assert "MAPPING_INVALID" in mapping_provider.capabilities().reason


def test_capability_service_keeps_asr_ok_when_visual_fails(tmp_path: Path):
    asr = AsrProvider(_asr_database(tmp_path / "aic.sqlite"))
    visual = VisualProvider(tmp_path / "missing")
    report = CapabilityService({"asr": asr, "visual": visual}, media_root=tmp_path / "no-media").report()
    assert report["providers"]["asr"]["status"] == "OK"
    assert report["providers"]["visual"]["status"] == "UNAVAILABLE"
    assert report["providers"]["ocr"]["status"] == "UNAVAILABLE"
    assert report["providers"]["object"]["status"] == "UNAVAILABLE"
    assert report["media"]["status"] == "MEDIA_UNAVAILABLE"
