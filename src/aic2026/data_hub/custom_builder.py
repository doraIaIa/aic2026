from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aic2026.core.atomic import atomic_write_json, atomic_write_text
from aic2026.data_hub.custom_models import (
    CustomKeyframeRecord,
    CustomSpace,
    QwenMissingRecord,
    QwenSemanticRecord,
)
from aic2026.data_hub.custom_validator import CustomKeyframeValidator
from aic2026.data_hub.models import SourceRecord
from aic2026.data_hub.video_registry import VideoRegistry


def normalize_custom_image_relpath(image_path: str, video_id: str, file_name: str) -> str:
    """Normalize raw image_path to canonical portable relative path output/keyframes/{video_id}/{file_name}."""
    if not image_path:
        return f"output/keyframes/{video_id}/{file_name}"

    clean = str(image_path).replace("\\", "/")
    # If contains 'output/keyframes/' extract from output/
    if "output/keyframes/" in clean:
        idx = clean.find("output/keyframes/")
        return clean[idx:]
    if "keyframes/" in clean:
        idx = clean.find("keyframes/")
        return f"output/{clean[idx:]}"

    # Default fallback
    return f"output/keyframes/{video_id}/{file_name}"


def build_custom_and_qwen_records(
    raw_custom_items: List[Dict[str, Any]],
    raw_qwen_items: List[Dict[str, Any]],
    video_registry: VideoRegistry,
    custom_space_id: str = "custom_keyframes_v1",
) -> Tuple[List[CustomKeyframeRecord], List[QwenSemanticRecord], List[QwenMissingRecord]]:
    """Build canonical CustomKeyframeRecords, QwenSemanticRecords, and QwenMissingRecords."""
    # 1. Index Qwen items by (video_id, frame_idx)
    qwen_map: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for q in raw_qwen_items:
        v_id = q.get("video_id")
        f_idx = q.get("frame_idx")
        if v_id is not None and f_idx is not None:
            key = (str(v_id), int(f_idx))
            qwen_map[key] = q

    custom_records: List[CustomKeyframeRecord] = []
    qwen_records: List[QwenSemanticRecord] = []
    missing_records: List[QwenMissingRecord] = []

    # Sort custom items deterministically by (video_id, frame_idx)
    def custom_sort_key(item: Dict[str, Any]) -> Tuple[int, int]:
        v_id = str(item.get("video_id", ""))
        v_meta = video_registry.get_video(v_id)
        ord_val = v_meta.ordinal if v_meta else 999999
        f_idx = int(item.get("frame_idx", 0))
        return (ord_val, f_idx)

    sorted_custom = sorted(raw_custom_items, key=custom_sort_key)

    for item in sorted_custom:
        v_id = str(item["video_id"])
        f_idx = int(item["frame_idx"])
        raw_pts = float(item["pts_time"])
        ts_ms = int(round(raw_pts * 1000))
        file_name = str(item.get("file_name", f"{int(item.get('keyframe_id', 1)):06d}.jpg"))

        v_meta = video_registry.get_video(v_id)
        video_ordinal = v_meta.ordinal if v_meta else 0
        ordinal_space_id = v_meta.ordinal_space_id if v_meta else "v1_natural_series_video"

        uid = f"CUSTOM:{v_id}:F{f_idx}"
        img_relpath = normalize_custom_image_relpath(str(item.get("image_path", "")), v_id, file_name)

        join_key = (v_id, f_idx)
        qwen_raw = qwen_map.get(join_key)

        is_qwen_valid = False
        if qwen_raw is not None:
            is_qwen_valid = True
            caption = str(qwen_raw.get("caption", "") or "").strip()
            objects = qwen_raw.get("objects", [])
            scene = qwen_raw.get("scene", [])
            qwen_pts = float(qwen_raw.get("pts_time", raw_pts))
            qwen_ts_ms = int(round(qwen_pts * 1000))
            q_rec = QwenSemanticRecord(
                keyframe_uid=uid,
                video_id=v_id,
                frame_idx=f_idx,
                timestamp_ms=qwen_ts_ms,
                raw_pts_time=qwen_pts,
                objects=[str(x) for x in objects] if isinstance(objects, list) else [],
                attributes=[str(x) for x in qwen_raw.get("attributes", [])] if isinstance(qwen_raw.get("attributes"), list) else [],
                spatial_relations=[str(x) for x in qwen_raw.get("spatial_relations", [])] if isinstance(qwen_raw.get("spatial_relations"), list) else [],
                counts=[str(x) for x in qwen_raw.get("counts", [])] if isinstance(qwen_raw.get("counts"), list) else [],
                scene=[str(x) for x in scene] if isinstance(scene, list) else [],
                visible_actions=[str(x) for x in qwen_raw.get("visible_actions", [])] if isinstance(qwen_raw.get("visible_actions"), list) else [],
                caption=caption,
                semantic_status="OK",
                frame_space="CUSTOM",
                schema_version="v1",
                source_id="qwen_raw_v1",
            )
            qwen_records.append(q_rec)
        else:
            m_rec = QwenMissingRecord(
                keyframe_uid=uid,
                video_id=v_id,
                frame_idx=f_idx,
                timestamp_ms=ts_ms,
                raw_pts_time=raw_pts,
                reason="NOT_IN_QWEN_SHARD",
            )
            missing_records.append(m_rec)

        c_rec = CustomKeyframeRecord(
            keyframe_uid=uid,
            video_id=v_id,
            video_ordinal=video_ordinal,
            ordinal_space_id=ordinal_space_id,
            frame_idx=f_idx,
            timestamp_ms=ts_ms,
            raw_pts_time=raw_pts,
            shot_id=int(item.get("shot_id", 0)),
            cluster_id=int(item.get("cluster_id", 0)),
            embedding_index=int(item.get("embedding_index", 0)),
            source_keyframe_id=int(item.get("keyframe_id", 0)),
            file_name=file_name,
            image_relpath=img_relpath,
            qwen_status="OK" if is_qwen_valid else "MISSING",
            frame_space="CUSTOM",
            schema_version="v1",
            source_id="custom_keyframes_raw_v1",
        )
        custom_records.append(c_rec)

    return custom_records, qwen_records, missing_records


def materialize_custom_qwen_catalog(
    custom_records: List[CustomKeyframeRecord],
    qwen_records: List[QwenSemanticRecord],
    missing_records: List[QwenMissingRecord],
    output_dir: Path | str,
    video_registry: VideoRegistry,
    custom_space_id: str = "custom_keyframes_v1",
    source_records: Optional[List[SourceRecord]] = None,
    validate: bool = True,
) -> Dict[str, Path]:
    """Materialize custom_keyframes.jsonl, qwen_semantics_normalized.jsonl, qwen_missing_keyframes.jsonl, custom_space.json, build_manifest.json."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    validator = CustomKeyframeValidator(
        expected_keyframe_count=len(custom_records),
        expected_video_count=len(set(r.video_id for r in custom_records)),
        video_registry=video_registry,
    )
    custom_checksum = validator.compute_custom_catalog_checksum(custom_records)
    qwen_checksum = validator.compute_qwen_canonical_checksum(qwen_records)

    custom_space = CustomSpace(
        custom_space_id=custom_space_id,
        frame_space="CUSTOM",
        schema_version="v1",
        keyframe_count=len(custom_records),
        video_count=len(set(r.video_id for r in custom_records)),
        identity_rule="CUSTOM:{video_id}:F{frame_idx}",
        source_checksum=custom_checksum,
        catalog_checksum=custom_checksum,
        created_at=datetime.now(timezone.utc).isoformat(),
        status="READY",
    )

    if validate:
        res = validator.validate(custom_records, qwen_records, missing_records, custom_space)
        if not res.is_valid:
            raise ValueError(f"Custom/Qwen catalog validation failed: {res.errors}")

    # 1. custom_keyframes.jsonl
    custom_file = out / "custom_keyframes.jsonl"
    atomic_write_text(custom_file, "\n".join(json.dumps(r.to_dict(), ensure_ascii=False) for r in custom_records) + "\n")

    # 2. qwen_semantics_normalized.jsonl
    qwen_file = out / "qwen_semantics_normalized.jsonl"
    atomic_write_text(qwen_file, "\n".join(json.dumps(q.to_dict(), ensure_ascii=False) for q in qwen_records) + "\n")

    # 3. qwen_missing_keyframes.jsonl
    missing_file = out / "qwen_missing_keyframes.jsonl"
    atomic_write_text(missing_file, "\n".join(json.dumps(m.to_dict(), ensure_ascii=False) for m in missing_records) + "\n")

    # 4. custom_space.json
    space_file = out / "custom_space.json"
    atomic_write_json(space_file, custom_space.to_dict())

    # 5. source_registry.jsonl (extended with custom and qwen sources)
    sources = source_records or [
        SourceRecord(
            source_id="canonical_video_universe_v1",
            source_type="SOURCE_VIDEO_CATALOG",
            scope="CANONICAL_VIDEO_UNIVERSE",
            relative_path_or_logical_ref="videos.jsonl",
            schema_version="v1",
            record_count=video_registry.video_count(),
            checksum=video_registry.catalog_checksum,
            producer="aic2026.data_hub.builder",
            status="READY",
            notes=["Canonical 873-video universe"],
        ),
        SourceRecord(
            source_id="custom_keyframes_raw_v1",
            source_type="CUSTOM_KEYFRAME_CATALOG",
            scope="CUSTOM_KEYFRAME_UNIVERSE",
            relative_path_or_logical_ref="custom_keyframes.jsonl",
            schema_version="v1",
            record_count=len(custom_records),
            checksum=custom_checksum,
            producer="aic2026.data_hub.custom_builder",
            status="READY",
            notes=["Canonical 116,767 custom keyframes with natural video ordinals"],
        ),
        SourceRecord(
            source_id="qwen_raw_v1",
            source_type="QWEN_SEMANTICS_NORMALIZED",
            scope="CUSTOM_KEYFRAME_OBSERVATIONS",
            relative_path_or_logical_ref="qwen_semantics_normalized.jsonl",
            schema_version="v1",
            record_count=len(qwen_records),
            checksum=qwen_checksum,
            producer="qwen_vl_max_raw",
            status="READY",
            notes=[f"Qwen visual semantic observations; missing count={len(missing_records)}"],
        ),
    ]
    source_file = out / "source_registry.jsonl"
    atomic_write_text(source_file, "\n".join(json.dumps(s.to_dict(), ensure_ascii=False) for s in sources) + "\n")

    # 6. build_manifest.json
    manifest_file = out / "build_manifest.json"
    manifest_data = {
        "task": "M1B_CUSTOM_QWEN_MAPPING",
        "video_space_id": video_registry.video_space_id,
        "video_catalog_checksum": video_registry.catalog_checksum,
        "custom_space_id": custom_space_id,
        "custom_keyframe_count": len(custom_records),
        "qwen_valid_count": len(qwen_records),
        "qwen_missing_count": len(missing_records),
        "custom_catalog_checksum": custom_checksum,
        "qwen_canonical_checksum": qwen_checksum,
        "status": "SUCCESS",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(manifest_file, manifest_data)

    return {
        "custom_keyframes": custom_file,
        "qwen_semantics": qwen_file,
        "qwen_missing": missing_file,
        "custom_space": space_file,
        "source_registry": source_file,
        "build_manifest": manifest_file,
    }
