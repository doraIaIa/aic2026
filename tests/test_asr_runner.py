from __future__ import annotations

import json
from pathlib import Path

import pytest

import aic2026.asr.whisper_runner as whisper_runner
from aic2026.asr.merge import merge_asr_shards
from aic2026.asr.whisper_runner import AsrDependencyError, run_asr_shard, validate_asr_shard_artifact


class _FakeTranscriber:
    backend_version = "test"

    def transcribe(self, video_path: Path, **kwargs):
        if video_path.stem == "V2":
            raise RuntimeError("synthetic decode failure")
        return ([{
            "start": 0.0,
            "end": 1.5,
            "text": " xin chào Việt Nam ",
            "avg_logprob": -0.1,
            "no_speech_prob": 0.01,
            "compression_ratio": 1.0,
        }], {"duration": 2.0, "language": "vi", "language_probability": 0.99})


def _write_shard(path: Path, video_ids: list[str], *, shard_id: str = "shard_000_of_001") -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "task": "asr_whisper",
        "shard_id": shard_id,
        "shard_index": 0,
        "shard_count": 1,
        "source_manifest_sha256": "a" * 64,
        "item_count": len(video_ids),
        "items": [{
            "schema_version": 1,
            "video_id": video_id,
            "video_path": f"video/{video_id}.mp4",
            "source_query_ids": ["q1"],
            "source_candidate_ranks": {"q1": [1]},
        } for video_id in video_ids],
    }), encoding="utf-8")


def test_run_asr_shard_records_per_video_failure_and_resumes(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "video").mkdir(parents=True)
    (data_root / "video" / "V1.mp4").write_bytes(b"one")
    (data_root / "video" / "V2.mp4").write_bytes(b"two")
    shard = tmp_path / "shard.json"
    _write_shard(shard, ["V1", "V2"])
    output = tmp_path / "artifact"

    with pytest.warns(RuntimeWarning, match="fallback CPU"):
        marker = run_asr_shard(
            shard, data_root, output, device="cpu",
            transcriber_factory=lambda *_: _FakeTranscriber(),
        )

    assert marker["processed_videos"] == 1
    assert marker["failed_videos"] == 1
    assert marker["segment_count"] == 1
    assert marker["status"] == "completed_with_errors"
    assert {path.name for path in output.iterdir()}.issuperset({
        "asr_segments.jsonl", "asr_videos.jsonl", "errors.jsonl",
        "progress.json", "DONE.json", "checksum.sha256",
    })
    assert validate_asr_shard_artifact(output)[0] is True

    second = run_asr_shard(
        shard, data_root, output, device="cpu",
        transcriber_factory=lambda *_: (_ for _ in ()).throw(AssertionError("must not initialize")),
    )
    assert second == marker

    (output / "asr_segments.jsonl").write_text("corrupt\n", encoding="utf-8")
    assert validate_asr_shard_artifact(output)[0] is False


def test_run_asr_shard_resumes_after_backend_initialization_failure(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "video").mkdir(parents=True)
    (data_root / "video" / "V1.mp4").write_bytes(b"one")
    shard = tmp_path / "shard.json"
    _write_shard(shard, ["V1"])
    output = tmp_path / "artifact"

    with pytest.warns(RuntimeWarning), pytest.raises(AsrDependencyError):
        run_asr_shard(
            shard, data_root, output, device="cpu",
            transcriber_factory=lambda *_: (_ for _ in ()).throw(AsrDependencyError("missing")),
        )
    assert (output / "progress.json").is_file()
    assert not (output / "DONE.json").exists()

    with pytest.warns(RuntimeWarning):
        marker = run_asr_shard(
            shard, data_root, output, device="cpu",
            transcriber_factory=lambda *_: _FakeTranscriber(),
        )
    assert marker["processed_videos"] == 1
    assert validate_asr_shard_artifact(output)[0] is True


def test_failed_video_does_not_leave_orphan_segments(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    (data_root / "video").mkdir(parents=True)
    (data_root / "video" / "V1.mp4").write_bytes(b"one")
    shard = tmp_path / "shard.json"
    _write_shard(shard, ["V1"])
    original_append = whisper_runner.append_jsonl
    raised = False

    def flaky_append(path, row):
        nonlocal raised
        original_append(path, row)
        if Path(path).name == "asr_segments.partial.jsonl" and not raised:
            raised = True
            raise OSError("synthetic crash after segment append")

    monkeypatch.setattr(whisper_runner, "append_jsonl", flaky_append)
    with pytest.warns(RuntimeWarning):
        marker = run_asr_shard(
            shard, data_root, tmp_path / "artifact", device="cpu",
            transcriber_factory=lambda *_: _FakeTranscriber(),
        )
    assert marker["failed_videos"] == 1
    assert marker["segment_count"] == 0
    assert (tmp_path / "artifact" / "asr_segments.jsonl").read_text(encoding="utf-8") == ""


def test_merge_validated_asr_shard(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    (data_root / "video").mkdir(parents=True)
    (data_root / "video" / "V1.mp4").write_bytes(b"one")
    shard_file = tmp_path / "shard.json"
    _write_shard(shard_file, ["V1"])
    shard_artifact = tmp_path / "artifacts" / "shard_000_of_001"
    with pytest.warns(RuntimeWarning):
        run_asr_shard(
            shard_file, data_root, shard_artifact, device="cpu",
            transcriber_factory=lambda *_: _FakeTranscriber(),
        )

    marker = merge_asr_shards(tmp_path / "artifacts", tmp_path / "merged")
    assert marker["processed_videos"] == 1
    assert marker["failed_videos"] == 0
    assert marker["segment_count"] == 1
    assert (tmp_path / "merged" / "asr_segments.jsonl").is_file()
