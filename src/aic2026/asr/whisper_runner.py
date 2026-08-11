from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from aic2026.asr.manifest import AsrContractError
from aic2026.asr.shard import load_asr_shard
from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.core.hashing import sha256_bytes, sha256_file
from aic2026.core.paths import normalize_relpath
from aic2026.jobs.artifact import append_jsonl, read_valid_jsonl_prefix, rewrite_jsonl


class AsrDependencyError(RuntimeError):
    """The optional faster-whisper runtime is unavailable."""


class Transcriber(Protocol):
    backend_version: str

    def transcribe(self, video_path: Path, **kwargs: Any) -> tuple[list[Any], Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout)
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN", True


def detect_device(requested: str = "auto") -> str:
    if requested not in {"auto", "cpu", "cuda"}:
        raise AsrContractError("device phải là auto, cpu hoặc cuda")
    if requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class FasterWhisperTranscriber:
    def __init__(self, model_size: str, *, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AsrDependencyError(
                "Thiếu optional dependency faster-whisper; cài project với extra [asr]"
            ) from exc
        self.backend_version = importlib.metadata.version("faster-whisper")
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, video_path: Path, **kwargs: Any) -> tuple[list[Any], Any]:
        segments, info = self._model.transcribe(str(video_path), **kwargs)
        return list(segments), info


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _strict_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AsrContractError(f"JSONL final lỗi tại {path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise AsrContractError(f"JSONL final row không phải object tại {path}:{line_number}")
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_text(
        path,
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
    )


def write_checksum_file(root: Path, filenames: list[str]) -> tuple[dict[str, str], str]:
    checksums = {name: sha256_file(root / name) for name in sorted(filenames)}
    payload = "".join(f"{digest}  {name}\n" for name, digest in checksums.items())
    checksum_path = root / "checksum.sha256"
    atomic_write_text(checksum_path, payload)
    return checksums, sha256_file(checksum_path)


def validate_asr_shard_artifact(
    artifact_dir: str | Path,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    root = Path(artifact_dir)
    errors: list[str] = []
    try:
        marker = json.loads((root / "DONE.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"DONE.json không đọc được: {exc}"], None
    if marker.get("schema_version") != 1 or marker.get("task") != "asr_whisper":
        errors.append("DONE.json sai schema/task")
    required = ["asr_segments.jsonl", "asr_videos.jsonl", "errors.jsonl", "progress.json"]
    output_checksums = marker.get("output_checksums")
    if not isinstance(output_checksums, dict):
        errors.append("DONE.json thiếu output_checksums")
        output_checksums = {}
    for name in required:
        path = root / name
        if not path.is_file():
            errors.append(f"Thiếu {name}")
        elif sha256_file(path) != output_checksums.get(name):
            errors.append(f"Checksum không khớp: {name}")
    checksum_path = root / "checksum.sha256"
    if not checksum_path.is_file():
        errors.append("Thiếu checksum.sha256")
    elif sha256_file(checksum_path) != marker.get("checksum_sha256"):
        errors.append("checksum.sha256 không khớp marker")
    expected = marker.get("expected_videos")
    processed = marker.get("processed_videos")
    failed = marker.get("failed_videos")
    if not all(type(value) is int for value in (expected, processed, failed)):
        errors.append("Count video không hợp lệ")
    elif processed + failed != expected:
        errors.append("processed_videos + failed_videos != expected_videos")
    try:
        videos = _strict_jsonl(root / "asr_videos.jsonl")
        failures = _strict_jsonl(root / "errors.jsonl")
        segments = _strict_jsonl(root / "asr_segments.jsonl")
        if type(processed) is int and len(videos) != processed:
            errors.append("Số asr_videos rows không khớp")
        if type(failed) is int and len(failures) != failed:
            errors.append("Số errors rows không khớp")
        if type(marker.get("segment_count")) is int and len(segments) != marker["segment_count"]:
            errors.append("Số segment rows không khớp")
    except (OSError, AsrContractError) as exc:
        errors.append(str(exc))
    return not errors, errors, marker


def _archive_for_force(target: Path) -> None:
    if not target.exists():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.with_name(f"{target.name}.replaced-{timestamp}")
    if backup.exists():
        raise AsrContractError(f"Force backup đã tồn tại: {backup.name}")
    os.replace(target, backup)


def run_asr_shard(
    shard_path: str | Path,
    data_root: str | Path,
    output_dir: str | Path,
    *,
    model_size: str = "medium",
    model_revision: str = "medium",
    language: str = "vi",
    task: str = "transcribe",
    beam_size: int = 5,
    vad_filter: bool = True,
    word_timestamps: bool = False,
    device: str = "auto",
    compute_type: str | None = None,
    force: bool = False,
    transcriber_factory: Callable[[str, str, str], Transcriber] | None = None,
) -> dict[str, Any]:
    shard_source = Path(shard_path)
    shard = load_asr_shard(shard_source)
    target = Path(output_dir)
    if (target / "DONE.json").exists():
        valid, errors, marker = validate_asr_shard_artifact(target)
        if valid and not force:
            if marker and marker.get("input_shard_sha256") == sha256_file(shard_source):
                return marker
            raise AsrContractError("ASR artifact hoàn tất thuộc shard khác; dùng output version mới")
        if not force:
            raise AsrContractError(f"ASR artifact tồn tại nhưng không hợp lệ: {errors}")
        _archive_for_force(target)
    elif force and target.exists():
        _archive_for_force(target)
    target.mkdir(parents=True, exist_ok=True)

    actual_device = detect_device(device)
    actual_compute = compute_type or ("float16" if actual_device == "cuda" else "int8")
    if actual_device == "cpu":
        warnings.warn("ASR đang fallback CPU; Whisper medium có thể chạy rất chậm", RuntimeWarning)
    config = {
        "model_size": model_size,
        "model_revision": model_revision,
        "language": language,
        "task": task,
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "word_timestamps": word_timestamps,
        "device": actual_device,
        "compute_type": actual_compute,
    }
    config_hash = sha256_bytes(json.dumps(config, sort_keys=True).encode("utf-8"))
    shard_hash = sha256_file(shard_source)
    progress_path = target / "progress.json"
    progress_contract = {
        "schema_version": 1,
        "task": "asr_whisper",
        "shard_id": shard["shard_id"],
        "input_shard_sha256": shard_hash,
        "input_manifest_sha256": shard["source_manifest_sha256"],
        "config_hash": config_hash,
    }
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AsrContractError(f"progress.json không đọc được: {exc}") from exc
        if any(progress.get(key) != value for key, value in progress_contract.items()):
            raise AsrContractError("Partial ASR artifact thuộc shard/config khác")
    else:
        progress = {**progress_contract, "completed_video_ids": [], "failed_video_ids": [], "updated_at": _utc_now()}
        atomic_write_json(progress_path, progress)

    segment_partial = target / "asr_segments.partial.jsonl"
    video_partial = target / "asr_videos.partial.jsonl"
    error_partial = target / "errors.partial.jsonl"
    video_rows = read_valid_jsonl_prefix(video_partial)
    error_rows = read_valid_jsonl_prefix(error_partial)
    completed_ids = {row.get("video_id") for row in video_rows}
    failed_ids = {row.get("video_id") for row in error_rows}
    if None in completed_ids or None in failed_ids or completed_ids & failed_ids:
        raise AsrContractError("Partial ASR có video_id thiếu/trùng giữa success và error")
    item_ids = {item["video_id"] for item in shard["items"]}
    if not (completed_ids | failed_ids).issubset(item_ids):
        raise AsrContractError("Partial ASR chứa video ngoài shard")
    # Trim a crash-truncated final line and discard orphan segments written
    # before a video-level success record was durably appended.
    segment_rows = [
        row for row in read_valid_jsonl_prefix(segment_partial)
        if row.get("video_id") in completed_ids
    ]
    rewrite_jsonl(segment_partial, segment_rows)
    rewrite_jsonl(video_partial, video_rows)
    rewrite_jsonl(error_partial, error_rows)

    factory = transcriber_factory or (
        lambda size, dev, compute: FasterWhisperTranscriber(size, device=dev, compute_type=compute)
    )
    transcriber = factory(model_size, actual_device, actual_compute)
    backend_version = getattr(transcriber, "backend_version", "unknown")
    started_at = progress.get("started_at") or _utc_now()
    root = Path(data_root)
    for item in shard["items"]:
        video_id = item["video_id"]
        if video_id in completed_ids or video_id in failed_ids:
            continue
        relpath = normalize_relpath(item["video_path"])
        video_path = root / Path(relpath)
        started = time.perf_counter()
        try:
            if not video_path.is_file():
                raise FileNotFoundError(f"Không tìm thấy source video: {relpath}")
            segments, info = transcriber.transcribe(
                video_path,
                language=language,
                task=task,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )
            pending_segments: list[dict[str, Any]] = []
            for index, segment in enumerate(segments):
                start_sec = float(_value(segment, "start", -1))
                end_sec = float(_value(segment, "end", -1))
                text = str(_value(segment, "text", "")).strip()
                if start_sec < 0 or end_sec < start_sec or not text:
                    raise AsrContractError(f"Backend trả segment malformed cho {video_id}")
                pending_segments.append({
                    "video_id": video_id,
                    "segment_id": f"{video_id}:{index:06d}",
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "text": text,
                    "avg_logprob": _value(segment, "avg_logprob"),
                    "no_speech_prob": _value(segment, "no_speech_prob"),
                    "compression_ratio": _value(segment, "compression_ratio"),
                    "model": model_size,
                    "language": language,
                    "source_video_path": relpath,
                })
            for segment_row in pending_segments:
                append_jsonl(segment_partial, segment_row)
            append_jsonl(video_partial, {
                "video_id": video_id,
                "source_video_path": relpath,
                "status": "OK",
                "segment_count": len(pending_segments),
                "duration_sec": _value(info, "duration"),
                "detected_language": _value(info, "language", language),
                "language_probability": _value(info, "language_probability"),
                "elapsed_sec": time.perf_counter() - started,
            })
            completed_ids.add(video_id)
        except Exception as exc:
            append_jsonl(error_partial, {
                "video_id": video_id,
                "source_video_path": relpath,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_sec": time.perf_counter() - started,
            })
            failed_ids.add(video_id)
        progress = {
            **progress_contract,
            "started_at": started_at,
            "completed_video_ids": sorted(completed_ids),
            "failed_video_ids": sorted(failed_ids),
            "updated_at": _utc_now(),
        }
        atomic_write_json(progress_path, progress)

    segment_rows = [
        row for row in read_valid_jsonl_prefix(segment_partial)
        if row.get("video_id") in completed_ids
    ]
    rewrite_jsonl(segment_partial, segment_rows)
    video_rows = read_valid_jsonl_prefix(video_partial)
    error_rows = read_valid_jsonl_prefix(error_partial)
    _write_jsonl(target / "asr_segments.jsonl", segment_rows)
    _write_jsonl(target / "asr_videos.jsonl", video_rows)
    _write_jsonl(target / "errors.jsonl", error_rows)
    progress = {
        **progress_contract,
        "started_at": started_at,
        "completed_video_ids": sorted(completed_ids),
        "failed_video_ids": sorted(failed_ids),
        "updated_at": _utc_now(),
        "status": "completed" if not error_rows else "completed_with_errors",
    }
    atomic_write_json(progress_path, progress)
    checksums, checksum_hash = write_checksum_file(
        target, ["asr_segments.jsonl", "asr_videos.jsonl", "errors.jsonl", "progress.json"]
    )
    git_commit, git_dirty = _git_state()
    marker = {
        "schema_version": 1,
        "task": "asr_whisper",
        "shard_id": shard["shard_id"],
        "started_at": started_at,
        "finished_at": _utc_now(),
        "input_manifest_sha256": shard["source_manifest_sha256"],
        "input_shard_sha256": shard_hash,
        "config_hash": config_hash,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "model": model_size,
        "model_revision": model_revision,
        "backend": "faster-whisper",
        "backend_version": backend_version,
        "language": language,
        "device": actual_device,
        "compute_type": actual_compute,
        "expected_videos": len(shard["items"]),
        "processed_videos": len(video_rows),
        "failed_videos": len(error_rows),
        "segment_count": len(segment_rows),
        "output_checksums": checksums,
        "checksum_file": "checksum.sha256",
        "checksum_sha256": checksum_hash,
        "status": "completed" if not error_rows else "completed_with_errors",
    }
    atomic_write_json(target / "DONE.json", marker)
    valid, errors, _ = validate_asr_shard_artifact(target)
    if not valid:
        raise AsrContractError(f"ASR artifact finalize không hợp lệ: {errors}")
    return marker
