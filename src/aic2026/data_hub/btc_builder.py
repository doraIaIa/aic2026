from __future__ import annotations

import csv
import datetime
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from aic2026.data_hub.btc_models import (
    BtcClipRowRecord,
    BtcKeyframeRecord,
    BtcMediaInfoRecord,
    BtcObjectCoverageRecord,
    BtcObjectDetectionRecord,
    BtcSpace,
    BtcValidationResult,
)
from aic2026.data_hub.btc_validator import BtcValidator
from aic2026.data_hub.models import SourceRecord
from aic2026.data_hub.video_registry import VideoRegistry


class BtcCatalogBuilder:
    """Builder that materializes canonical BTC keyframe space, CLIP rowmaps, objects, and media info."""

    def __init__(
        self,
        video_registry: VideoRegistry,
        validator: Optional[BtcValidator] = None,
    ) -> None:
        self.video_registry = video_registry
        self.validator = validator or BtcValidator(video_registry=video_registry)
        self._videos_by_id = {r.video_id: r for r in video_registry.iter_videos()}

    def build_btc_keyframes(self, map_keyframes_dir: Path) -> List[BtcKeyframeRecord]:
        """Build canonical BTC keyframe records from all 873 map CSVs."""
        records: List[BtcKeyframeRecord] = []

        # Iterate over canonical videos in sorted order
        for vid, v_rec in sorted(self._videos_by_id.items(), key=lambda kv: kv[1].ordinal):
            map_p = map_keyframes_dir / f"{vid}.csv"
            if not map_p.exists():
                raise FileNotFoundError(f"Map CSV missing for canonical video: {vid}")

            with open(map_p, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                # Header: ['n', 'pts_time', 'fps', 'frame_idx']
                for row in reader:
                    if not row or len(row) < 4:
                        continue
                    n = int(row[0])
                    pts_time = float(row[1])
                    fps = float(row[2])
                    frame_idx = int(row[3])
                    timestamp_ms = int(round(pts_time * 1000))
                    keyframe_uid = f"BTC:{vid}:KF{n:06d}"
                    image_relpath = f"data_extracted/keyframes/{vid}/{n:03d}.jpg"

                    rec = BtcKeyframeRecord(
                        keyframe_uid=keyframe_uid,
                        video_id=vid,
                        video_ordinal=v_rec.ordinal,
                        ordinal_space_id=v_rec.ordinal_space_id,
                        local_keyframe_no=n,
                        frame_idx=frame_idx,
                        timestamp_ms=timestamp_ms,
                        raw_pts_time=pts_time,
                        fps=fps,
                        image_relpath=image_relpath,
                        frame_space="BTC",
                        btc_space_id="btc_keyframes_v1",
                        map_source_id="btc_map_keyframes_raw_v1",
                        clip_status="HAS_CLIP_ROW",
                        object_status="HAS_OBJECTS",
                    )
                    records.append(rec)

        return records

    def build_raw_clip_rowmaps(
        self,
        clip_features_dir: Path,
        btc_keyframes: List[BtcKeyframeRecord],
    ) -> List[BtcClipRowRecord]:
        """Build 1:1 mapping records for raw BTC CLIP feature rows."""
        # Index keyframes by (video_id, local_keyframe_no)
        kfs_by_vid_n: Dict[Tuple[str, int], BtcKeyframeRecord] = {
            (kf.video_id, kf.local_keyframe_no): kf for kf in btc_keyframes
        }

        rowmaps: List[BtcClipRowRecord] = []
        for vid, v_rec in sorted(self._videos_by_id.items(), key=lambda kv: kv[1].ordinal):
            clip_p = clip_features_dir / f"{vid}.npy"
            if not clip_p.exists():
                raise FileNotFoundError(f"CLIP array missing for canonical video: {vid}")

            arr = np.load(clip_p, mmap_mode="r")
            num_rows = arr.shape[0]
            dim = arr.shape[1] if arr.ndim > 1 else 512
            dtype_str = str(arr.dtype)

            for i in range(num_rows):
                local_keyframe_no = i + 1
                kf = kfs_by_vid_n.get((vid, local_keyframe_no))
                if kf is None:
                    raise KeyError(f"No canonical BTC keyframe found for {vid} row={i} (n={local_keyframe_no})")

                rec = BtcClipRowRecord(
                    clip_source_id="btc_clip_features_32_v1",
                    video_id=vid,
                    video_ordinal=v_rec.ordinal,
                    ordinal_space_id=v_rec.ordinal_space_id,
                    row_in_video=i,
                    keyframe_uid=kf.keyframe_uid,
                    local_keyframe_no=local_keyframe_no,
                    frame_idx=kf.frame_idx,
                    timestamp_ms=kf.timestamp_ms,
                    feature_relpath=f"data_extracted/clip-features-32/{vid}.npy",
                    dimension=dim,
                    dtype=dtype_str,
                    normalized=True,
                )
                rowmaps.append(rec)

        return rowmaps

    def build_object_detections_and_coverage(
        self,
        objects_zip_path: Path,
        btc_keyframes: List[BtcKeyframeRecord],
    ) -> Tuple[List[BtcObjectDetectionRecord], List[BtcObjectCoverageRecord]]:
        """Extract object detections and build keyframe coverage from objects archive."""
        kfs_by_vid_n: Dict[Tuple[str, int], BtcKeyframeRecord] = {
            (kf.video_id, kf.local_keyframe_no): kf for kf in btc_keyframes
        }

        detections: List[BtcObjectDetectionRecord] = []
        coverage: List[BtcObjectCoverageRecord] = []

        with zipfile.ZipFile(objects_zip_path, "r") as zf:
            # Map available json members: 'objects/{video_id}/{n:03d}.json' or '{n}.json'
            member_names = zf.namelist()
            json_members: Dict[Tuple[str, int], str] = {}
            for name in member_names:
                if name.endswith(".json"):
                    parts = name.split("/")
                    if len(parts) >= 3:
                        vid = parts[1]
                        fname = parts[2]
                        try:
                            n_val = int(fname.split(".")[0])
                            json_members[(vid, n_val)] = name
                        except ValueError:
                            pass

            for kf in btc_keyframes:
                member_key = (kf.video_id, kf.local_keyframe_no)
                member_path = json_members.get(member_key)

                if member_path is None:
                    # Unavailable in source archive
                    cov = BtcObjectCoverageRecord(
                        keyframe_uid=kf.keyframe_uid,
                        video_id=kf.video_id,
                        video_ordinal=kf.video_ordinal,
                        local_keyframe_no=kf.local_keyframe_no,
                        frame_idx=kf.frame_idx,
                        timestamp_ms=kf.timestamp_ms,
                        detection_count=0,
                        object_status="UNAVAILABLE",
                        source_file_relpath="",
                    )
                    coverage.append(cov)
                    continue

                raw_bytes = zf.read(member_path)
                data = json.loads(raw_bytes.decode("utf-8"))

                scores = data.get("detection_scores", [])
                class_names = data.get("detection_class_names", [])
                class_entities = data.get("detection_class_entities", [])
                boxes = data.get("detection_boxes", [])
                class_labels = data.get("detection_class_labels", [])

                num_dets = len(scores)
                status = "HAS_OBJECTS" if num_dets > 0 else "EMPTY"

                cov = BtcObjectCoverageRecord(
                    keyframe_uid=kf.keyframe_uid,
                    video_id=kf.video_id,
                    video_ordinal=kf.video_ordinal,
                    local_keyframe_no=kf.local_keyframe_no,
                    frame_idx=kf.frame_idx,
                    timestamp_ms=kf.timestamp_ms,
                    detection_count=num_dets,
                    object_status=status,
                    source_file_relpath=f"data/objects-aic25-b1.zip#{member_path}",
                )
                coverage.append(cov)

                for d_idx in range(num_dets):
                    det_uid = f"BTC_OBJECT:{kf.keyframe_uid}:D{d_idx}"
                    score = float(scores[d_idx])
                    c_name = class_names[d_idx] if d_idx < len(class_names) else ""
                    c_entity = class_entities[d_idx] if d_idx < len(class_entities) else None
                    c_label = class_labels[d_idx] if d_idx < len(class_labels) else None
                    box_raw = boxes[d_idx] if d_idx < len(boxes) else [0.0, 0.0, 0.0, 0.0]
                    bbox = [float(x) for x in box_raw]

                    det = BtcObjectDetectionRecord(
                        detection_uid=det_uid,
                        keyframe_uid=kf.keyframe_uid,
                        video_id=kf.video_id,
                        video_ordinal=kf.video_ordinal,
                        local_keyframe_no=kf.local_keyframe_no,
                        frame_idx=kf.frame_idx,
                        timestamp_ms=kf.timestamp_ms,
                        local_detection_index=d_idx,
                        class_name=c_name,
                        class_entity=c_entity,
                        class_label=c_label,
                        confidence=score,
                        bbox=bbox,
                        frame_space="BTC",
                        source_id="btc_objects_raw_v1",
                    )
                    detections.append(det)

        return detections, coverage

    def build_media_info(self, media_info_zip_path: Path) -> List[BtcMediaInfoRecord]:
        """Extract media-info JSONs from archive for all canonical videos."""
        records: List[BtcMediaInfoRecord] = []

        with zipfile.ZipFile(media_info_zip_path, "r") as zf:
            for vid, v_rec in sorted(self._videos_by_id.items(), key=lambda kv: kv[1].ordinal):
                member_path = f"media-info/{vid}.json"
                try:
                    raw_bytes = zf.read(member_path)
                    data = json.loads(raw_bytes.decode("utf-8"))
                except KeyError:
                    # Video not found in media-info
                    continue

                rec = BtcMediaInfoRecord(
                    video_id=vid,
                    video_ordinal=v_rec.ordinal,
                    ordinal_space_id=v_rec.ordinal_space_id,
                    title=data.get("title", ""),
                    description=data.get("description"),
                    keywords=data.get("keywords") if data.get("keywords") is not None else [],
                    author=data.get("author"),
                    channel_id=data.get("channel_id"),
                    channel_url=data.get("channel_url"),
                    publish_date=data.get("publish_date"),
                    duration_sec=int(data["length"]) if data.get("length") is not None else None,
                    thumbnail_url=data.get("thumbnail_url"),
                    watch_url=data.get("watch_url"),
                    source_id="btc_media_info_raw_v1",
                )
                records.append(rec)

        return records

    def materialize(
        self,
        output_dir: Path,
        map_keyframes_dir: Path,
        clip_features_dir: Path,
        objects_zip_path: Path,
        media_info_zip_path: Path,
        faiss_dir: Optional[Path] = None,
    ) -> BtcValidationResult:
        """Materialize canonical BTC Data Hub artifacts to output_dir."""
        import hashlib
        import math

        output_dir.mkdir(parents=True, exist_ok=True)

        print("1. Building canonical BTC keyframe records from map CSVs...")
        btc_keyframes = self.build_btc_keyframes(map_keyframes_dir)

        print("2. Building raw BTC CLIP row mappings...")
        clip_rowmaps = self.build_raw_clip_rowmaps(clip_features_dir, btc_keyframes)

        print("3. Streaming BTC object detections and coverage from zip...")
        obj_out = output_dir / "btc_objects.jsonl"
        obj_cov_out = output_dir / "btc_object_coverage.jsonl"
        obj_hasher = hashlib.sha256()
        total_detections = 0
        object_coverage: List[BtcObjectCoverageRecord] = []

        with zipfile.ZipFile(objects_zip_path, "r") as zf, \
             open(obj_out, "w", encoding="utf-8") as f_obj, \
             open(obj_cov_out, "w", encoding="utf-8") as f_cov:

            member_names = zf.namelist()
            json_members: Dict[Tuple[str, int], str] = {}
            for name in member_names:
                if name.endswith(".json"):
                    parts = name.split("/")
                    if len(parts) >= 3:
                        vid = parts[1]
                        fname = parts[2]
                        try:
                            n_val = int(fname.split(".")[0])
                            json_members[(vid, n_val)] = name
                        except ValueError:
                            pass

            for kf in btc_keyframes:
                member_key = (kf.video_id, kf.local_keyframe_no)
                member_path = json_members.get(member_key)

                if member_path is None:
                    cov = BtcObjectCoverageRecord(
                        keyframe_uid=kf.keyframe_uid,
                        video_id=kf.video_id,
                        video_ordinal=kf.video_ordinal,
                        local_keyframe_no=kf.local_keyframe_no,
                        frame_idx=kf.frame_idx,
                        timestamp_ms=kf.timestamp_ms,
                        detection_count=0,
                        object_status="UNAVAILABLE",
                        source_file_relpath="",
                    )
                    object_coverage.append(cov)
                    f_cov.write(json.dumps(cov.to_dict(), ensure_ascii=False) + "\n")
                    continue

                raw_bytes = zf.read(member_path)
                data = json.loads(raw_bytes.decode("utf-8"))

                scores = data.get("detection_scores", [])
                class_names = data.get("detection_class_names", [])
                class_entities = data.get("detection_class_entities", [])
                boxes = data.get("detection_boxes", [])
                class_labels = data.get("detection_class_labels", [])

                num_dets = len(scores)
                status = "HAS_OBJECTS" if num_dets > 0 else "EMPTY"

                cov = BtcObjectCoverageRecord(
                    keyframe_uid=kf.keyframe_uid,
                    video_id=kf.video_id,
                    video_ordinal=kf.video_ordinal,
                    local_keyframe_no=kf.local_keyframe_no,
                    frame_idx=kf.frame_idx,
                    timestamp_ms=kf.timestamp_ms,
                    detection_count=num_dets,
                    object_status=status,
                    source_file_relpath=f"data/objects-aic25-b1.zip#{member_path}",
                )
                object_coverage.append(cov)
                f_cov.write(json.dumps(cov.to_dict(), ensure_ascii=False) + "\n")

                for d_idx in range(num_dets):
                    total_detections += 1
                    det_uid = f"BTC_OBJECT:{kf.keyframe_uid}:D{d_idx}"
                    score = float(scores[d_idx])
                    c_name = class_names[d_idx] if d_idx < len(class_names) else ""
                    c_entity = class_entities[d_idx] if d_idx < len(class_entities) else None
                    c_label = class_labels[d_idx] if d_idx < len(class_labels) else None
                    box_raw = boxes[d_idx] if d_idx < len(boxes) else [0.0, 0.0, 0.0, 0.0]
                    bbox = [float(x) for x in box_raw]

                    det_dict = {
                        "detection_uid": det_uid,
                        "keyframe_uid": kf.keyframe_uid,
                        "video_id": kf.video_id,
                        "video_ordinal": kf.video_ordinal,
                        "local_keyframe_no": kf.local_keyframe_no,
                        "frame_idx": kf.frame_idx,
                        "timestamp_ms": kf.timestamp_ms,
                        "local_detection_index": d_idx,
                        "class_name": c_name,
                        "class_entity": c_entity,
                        "class_label": c_label,
                        "confidence": score,
                        "bbox": bbox,
                        "frame_space": "BTC",
                        "source_id": "btc_objects_raw_v1",
                        "schema_version": "v1",
                    }
                    f_obj.write(json.dumps(det_dict, ensure_ascii=False) + "\n")

                    bbox_str = ",".join(f"{x:.6f}" for x in bbox)
                    line_hash = (
                        f"{det_uid}|{kf.keyframe_uid}|{kf.video_id}|{kf.local_keyframe_no}|"
                        f"{kf.frame_idx}|{d_idx}|{c_name}|"
                        f"{c_entity or ''}|{c_label or ''}|{score:.6f}|{bbox_str}\n"
                    )
                    obj_hasher.update(line_hash.encode("utf-8"))

        object_canonical_checksum = obj_hasher.hexdigest()

        print("4. Building media-info records from zip...")
        media_info = self.build_media_info(media_info_zip_path)

        faiss_meta_rows = None
        if faiss_dir and (faiss_dir / "metadata.jsonl").exists():
            print("5. Reading existing FAISS metadata rows...")
            faiss_meta_rows = []
            with open(faiss_dir / "metadata.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        faiss_meta_rows.append(json.loads(line))

        print("6. Validating all BTC entities (fail-closed)...")
        validation = self.validator.validate(
            btc_keyframes=btc_keyframes,
            clip_rowmaps=clip_rowmaps,
            object_coverage=object_coverage,
            media_info=media_info,
            faiss_metadata_rows=faiss_meta_rows,
            precomputed_object_count=total_detections,
            precomputed_object_checksum=object_canonical_checksum,
        )

        if not validation.is_valid:
            raise ValueError(f"BTC Data Hub validation failed with {len(validation.errors)} errors:\n" + "\n".join(validation.errors[:20]))

        print("7. Writing canonical JSONL and JSON metadata artifacts...")
        # Write btc_keyframes.jsonl
        kf_out = output_dir / "btc_keyframes.jsonl"
        with open(kf_out, "w", encoding="utf-8") as f:
            for kf in btc_keyframes:
                f.write(json.dumps(kf.to_dict(), ensure_ascii=False) + "\n")

        # Write btc_clip_raw_rowmap.jsonl
        clip_out = output_dir / "btc_clip_raw_rowmap.jsonl"
        with open(clip_out, "w", encoding="utf-8") as f:
            for rm in clip_rowmaps:
                f.write(json.dumps(rm.to_dict(), ensure_ascii=False) + "\n")

        # Write media_info.jsonl
        media_out = output_dir / "media_info.jsonl"
        with open(media_out, "w", encoding="utf-8") as f:
            for m in media_info:
                f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

        # Write btc_space.json
        btc_space = BtcSpace(
            btc_space_id="btc_keyframes_v1",
            frame_space="BTC",
            schema_version="v1",
            keyframe_count=len(btc_keyframes),
            video_count=validation.btc_video_count,
            identity_rule="BTC:{video_id}:KF{local_keyframe_no:06d}",
            catalog_checksum=validation.btc_catalog_checksum,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        with open(output_dir / "btc_space.json", "w", encoding="utf-8") as f:
            json.dump(btc_space.to_dict(), f, indent=2)

        # Write btc_clip_raw_passport.json
        clip_passport = {
            "source_id": "btc_clip_features_32_v1",
            "source_type": "raw_clip_features",
            "model_family": "OpenAI CLIP ViT-B/32",
            "dimension": 512,
            "dtype": "float16",
            "normalized": True,
            "total_files": validation.raw_clip_file_count,
            "total_rows": validation.raw_clip_row_count,
            "mapped_rows": validation.raw_clip_mapped_rows,
            "unmapped_rows": validation.raw_clip_unmapped_rows,
            "rowmap_checksum": validation.raw_clip_rowmap_checksum,
            "status": "READY",
        }
        with open(output_dir / "btc_clip_raw_passport.json", "w", encoding="utf-8") as f:
            json.dump(clip_passport, f, indent=2)

        # Write btc_clip_existing_index_passport.json
        existing_index_passport = {
            "index_id": "clip-faiss-btc-v1",
            "source_type": "derived_faiss_index",
            "vector_dim": 512,
            "metric": "cosine_via_normalized_inner_product",
            "total_vectors": validation.faiss_vector_rows,
            "mapped_to_btc": validation.faiss_mapped_rows,
            "orphan_rows": validation.faiss_orphan_rows,
            "coverage_gap": len(btc_keyframes) - validation.faiss_mapped_rows,
            "status": "COMPLETE_FOR_ITS_MANIFEST",
            "index_checksum": validation.faiss_checksum,
        }
        with open(output_dir / "btc_clip_existing_index_passport.json", "w", encoding="utf-8") as f:
            json.dump(existing_index_passport, f, indent=2)

        # Write btc_object_space.json
        obj_space = {
            "object_space_id": "btc_objects_v1",
            "schema_version": "v1",
            "source_archive": "data/objects-aic25-b1.zip",
            "covered_videos": validation.object_video_count,
            "covered_keyframes": validation.object_keyframe_count,
            "total_detections": validation.object_detection_count,
            "empty_keyframes": validation.object_empty_keyframe_count,
            "unavailable_keyframes": validation.object_unavailable_keyframe_count,
            "canonical_checksum": validation.object_canonical_checksum,
        }
        with open(output_dir / "btc_object_space.json", "w", encoding="utf-8") as f:
            json.dump(obj_space, f, indent=2)

        # Write source_registry.jsonl
        source_records = [
            SourceRecord(
                source_id="btc_map_keyframes_raw_v1",
                source_type="csv_directory",
                scope="video_to_keyframe_map",
                relative_path_or_logical_ref="data_extracted/map-keyframes",
                schema_version="v1",
                record_count=validation.map_row_count,
                checksum=validation.btc_catalog_checksum,
                producer="AIC_ORGANIZER_BTC",
                status="READY",
                notes=["873 map CSV files across canonical videos"],
            ),
            SourceRecord(
                source_id="btc_keyframes_jpeg_v1",
                source_type="image_directory",
                scope="btc_keyframe_images",
                relative_path_or_logical_ref="data_extracted/keyframes",
                schema_version="v1",
                record_count=validation.jpeg_count,
                checksum="",
                producer="AIC_ORGANIZER_BTC",
                status="READY",
                notes=["873 video folders containing 177,321 JPEGs"],
            ),
            SourceRecord(
                source_id="btc_clip_features_32_v1",
                source_type="npy_directory",
                scope="btc_dense_clip_features",
                relative_path_or_logical_ref="data_extracted/clip-features-32",
                schema_version="v1",
                record_count=validation.raw_clip_row_count,
                checksum=validation.raw_clip_rowmap_checksum,
                producer="OpenAI_CLIP_ViT_B_32",
                status="READY",
                notes=["873 float16 512D arrays, unit normalized"],
            ),
            SourceRecord(
                source_id="btc_objects_raw_v1",
                source_type="zip_archive",
                scope="btc_object_detections",
                relative_path_or_logical_ref="data/objects-aic25-b1.zip",
                schema_version="v1",
                record_count=validation.object_detection_count,
                checksum=validation.object_canonical_checksum,
                producer="AIC_ORGANIZER_OBJECTS",
                status="READY",
                notes=["177,321 keyframes covered, OpenImages format"],
            ),
            SourceRecord(
                source_id="btc_media_info_raw_v1",
                source_type="zip_archive",
                scope="video_metadata_prior",
                relative_path_or_logical_ref="data/media-info-aic25-b1.zip",
                schema_version="v1",
                record_count=validation.media_info_count,
                checksum=validation.media_info_checksum,
                producer="AIC_ORGANIZER_MEDIA",
                status="READY",
                notes=["873 YouTube video metadata JSONs"],
            ),
        ]
        with open(output_dir / "source_registry.jsonl", "w", encoding="utf-8") as f:
            for s in source_records:
                f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")

        # Write build_manifest_m1d.json
        manifest = {
            "task": "M1D_BTC_MAPPING",
            "schema_version": "v1",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "btc_space_id": "btc_keyframes_v1",
            "video_count": validation.btc_video_count,
            "btc_keyframe_count": validation.btc_keyframe_count,
            "btc_catalog_checksum": validation.btc_catalog_checksum,
            "raw_clip_file_count": validation.raw_clip_file_count,
            "raw_clip_row_count": validation.raw_clip_row_count,
            "raw_clip_dimension": 512,
            "raw_clip_dtype": "float16",
            "raw_clip_mapped_rows": validation.raw_clip_mapped_rows,
            "raw_clip_unmapped_rows": validation.raw_clip_unmapped_rows,
            "raw_clip_rowmap_checksum": validation.raw_clip_rowmap_checksum,
            "object_source": "data/objects-aic25-b1.zip",
            "object_video_count": validation.object_video_count,
            "object_keyframe_count": validation.object_keyframe_count,
            "object_detection_count": validation.object_detection_count,
            "object_empty_keyframe_count": validation.object_empty_keyframe_count,
            "object_unavailable_keyframe_count": validation.object_unavailable_keyframe_count,
            "object_canonical_checksum": validation.object_canonical_checksum,
            "media_info_count": validation.media_info_count,
            "media_info_checksum": validation.media_info_checksum,
            "existing_faiss_rows": validation.faiss_vector_rows,
            "existing_faiss_mapped_rows": validation.faiss_mapped_rows,
            "existing_faiss_coverage_gap": len(btc_keyframes) - validation.faiss_mapped_rows,
            "existing_faiss_status": "COMPLETE_FOR_ITS_MANIFEST",
            "existing_faiss_checksum": validation.faiss_checksum,
            "raw_mutations": 0,
            "inference_reruns": 0,
            "validation_status": "PASS" if validation.is_valid else "FAIL",
        }
        with open(output_dir / "build_manifest_m1d.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return validation
