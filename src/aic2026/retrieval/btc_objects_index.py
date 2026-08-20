"""BTC Objects Index Builder and Compact Postings Materialization (M5D).

Builds a deterministic, compact SQLite object postings index over the
177,321 canonical BTC keyframes and 17,732,100 OpenImages object detections.

Key invariants:
- frame_space = BTC
- canonical frames = 177,321
- canonical videos = 873
- raw detections = 17,732,100 (100 per frame)
- score_type = btc_object_support (HIGHER_IS_BETTER)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sqlite3
import time
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

CANONICAL_BTC_FRAME_COUNT = 177321
CANONICAL_DETECTION_COUNT = 17732100
CANONICAL_VIDEO_COUNT = 873
NORMALIZER_VERSION = "deterministic_text_v1"

DEFAULT_MAPPING_DB = Path(r"F:\AIC_WORK\artifacts\retrieval_data_v1\runtime\mapping.sqlite")
DEFAULT_ZIP_PATH = Path(r"F:\AIC_WORK\tmp\objects-aic25-b1.zip")
FALLBACK_ZIP_PATH = Path(r"F:\AIC_2026\data\objects-aic25-b1.zip")
DEFAULT_OUTPUT_DIR = Path(r"F:\AIC_WORK\artifacts\retrieval_v2\btc_objects_v1")


def normalize_class_label(label: str) -> str:
    """Deterministic, conservative normalization for detector class labels.
    
    1. Unicode NFKC / NFC
    2. Strip leading/trailing whitespace
    3. Lowercase
    4. Collapse whitespace
    """
    if not label or not isinstance(label, str):
        return ""
    s = unicodedata.normalize("NFKC", label).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return unicodedata.normalize("NFC", s).strip()


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file in 64KB blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class BtcClassInfo:
    class_id: int
    class_name: str  # OpenImages MID e.g. /m/01g317
    class_entity: str  # Entity display name e.g. Person
    class_label: str  # Integer string class label e.g. 84
    class_norm: str  # Normalized lookup key e.g. person
    frame_count: int = 0
    detection_count: int = 0
    max_score: float = 0.0
    min_score: float = 1.0


def resolve_object_zip_path(custom_path: str | Path | None = None) -> Path:
    """Locate the authoritative BTC objects zip archive."""
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p
    if DEFAULT_ZIP_PATH.exists():
        return DEFAULT_ZIP_PATH
    if FALLBACK_ZIP_PATH.exists():
        return FALLBACK_ZIP_PATH
    raise FileNotFoundError(
        f"BTC objects zip archive not found at {DEFAULT_ZIP_PATH} or {FALLBACK_ZIP_PATH}"
    )


def load_canonical_btc_keyframe_map(
    mapping_db: str | Path = DEFAULT_MAPPING_DB,
) -> dict[tuple[str, int], tuple[str, int, int]]:
    """Loads mapping from (video_id, local_keyframe_no) -> (keyframe_uid, frame_idx, timestamp_ms)."""
    p = Path(mapping_db)
    if not p.exists():
        raise FileNotFoundError(f"Mapping database not found at {p}")
    
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    mapping: dict[tuple[str, int], tuple[str, int, int]] = {}
    rows = c.execute(
        "SELECT keyframe_uid, video_id, local_keyframe_no, frame_idx, timestamp_ms FROM btc_keyframes"
    ).fetchall()
    conn.close()
    
    for r in rows:
        mapping[(r["video_id"], int(r["local_keyframe_no"]))] = (
            r["keyframe_uid"],
            int(r["frame_idx"]),
            int(r["timestamp_ms"]),
        )
    return mapping


def build_btc_objects_index(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    zip_path: str | Path | None = None,
    mapping_db: str | Path = DEFAULT_MAPPING_DB,
    *,
    build_id: str | None = None,
) -> dict[str, Any]:
    """Build the compact SQLite index and manifest for BTC object retrieval.
    
    Builds into a temporary directory first and commits atomically to output_dir.
    """
    t_start = time.perf_counter()
    out_path = Path(output_dir)
    actual_zip = resolve_object_zip_path(zip_path)
    build_tag = build_id or f"btc_obj_b{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    
    temp_dir = out_path.parent / f"_tmp_{build_tag}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    db_file = temp_dir / "btc_objects_postings.sqlite"
    classes_json_file = temp_dir / "classes.json"
    manifest_file = temp_dir / "manifest.json"
    passport_file = temp_dir / "btc_objects_passport.json"
    done_file = temp_dir / "DONE.json"
    
    logger.info("Starting BTC objects index build (build_id: %s)", build_tag)
    logger.info("Source archive: %s", actual_zip)
    
    # 1. Load canonical BTC keyframe map
    kf_map = load_canonical_btc_keyframe_map(mapping_db)
    if len(kf_map) != CANONICAL_BTC_FRAME_COUNT:
        logger.warning(
            "Canonical BTC frame count mismatch: expected %d, got %d",
            CANONICAL_BTC_FRAME_COUNT,
            len(kf_map),
        )
        
    # 2. Open SQLite in temp location and set performance pragmas
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA journal_mode = OFF;")
    conn.execute("PRAGMA page_size = 65536;")
    conn.execute("PRAGMA cache_size = 100000;")
    
    conn.execute("""
        CREATE TABLE class_dictionary (
            class_id INTEGER PRIMARY KEY,
            class_name TEXT NOT NULL,
            class_entity TEXT NOT NULL,
            class_label TEXT NOT NULL,
            class_norm TEXT NOT NULL UNIQUE,
            frame_count INTEGER NOT NULL,
            detection_count INTEGER NOT NULL,
            max_score REAL NOT NULL,
            min_score REAL NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE object_postings (
            posting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            keyframe_uid TEXT NOT NULL,
            video_id TEXT NOT NULL,
            local_keyframe_no INTEGER NOT NULL,
            frame_idx INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            max_score REAL NOT NULL,
            detection_count INTEGER NOT NULL,
            top_bbox_json TEXT NOT NULL,
            top_detections_json TEXT NOT NULL
        )
    """)
    
    # 3. Stream zip files and aggregate detections per frame
    class_registry: dict[str, BtcClassInfo] = {}  # MID -> BtcClassInfo
    norm_to_mid: dict[str, str] = {}
    
    total_frames_read = 0
    total_detections_read = 0
    total_postings_inserted = 0
    
    postings_batch: list[tuple[Any, ...]] = []
    BATCH_SIZE = 50000
    
    with zipfile.ZipFile(actual_zip, "r") as zf:
        namelist = [n for n in zf.namelist() if n.endswith(".json")]
        namelist.sort()
        
        for name in namelist:
            # Format: objects/{video_id}/{kf_num}.json
            parts = name.split("/")
            if len(parts) < 3:
                continue
            video_id = parts[1]
            kf_no_str = parts[2].replace(".json", "")
            try:
                kf_no = int(kf_no_str)
            except ValueError:
                continue
                
            kf_info = kf_map.get((video_id, kf_no))
            if not kf_info:
                logger.warning("Unmapped object file: %s (video: %s, kf: %d)", name, video_id, kf_no)
                continue
                
            kf_uid, frame_idx, timestamp_ms = kf_info
            
            raw_bytes = zf.read(name)
            data = json.loads(raw_bytes)
            
            scores = data.get("detection_scores", [])
            mids = data.get("detection_class_names", [])
            entities = data.get("detection_class_entities", [])
            labels = data.get("detection_class_labels", [])
            boxes = data.get("detection_boxes", [])
            
            total_frames_read += 1
            total_detections_read += len(scores)
            
            # Aggregate by MID inside frame
            by_class: dict[str, dict[str, Any]] = {}
            for mid, ent, sc_val, lbl_val, box in zip(mids, entities, scores, labels, boxes):
                sc = float(sc_val)
                # Parse bbox
                if isinstance(box, list):
                    bbox_floats = [float(x) for x in box]
                else:
                    bbox_floats = [0.0, 0.0, 1.0, 1.0]
                    
                # Update global class dictionary
                if mid not in class_registry:
                    norm_label = normalize_class_label(ent)
                    if norm_label in norm_to_mid and norm_to_mid[norm_label] != mid:
                        raise ValueError(
                            f"Normalization collision detected: class '{ent}' ({mid}) conflicts with {norm_to_mid[norm_label]}"
                        )
                    norm_to_mid[norm_label] = mid
                    cls_id = len(class_registry) + 1
                    class_registry[mid] = BtcClassInfo(
                        class_id=cls_id,
                        class_name=mid,
                        class_entity=ent,
                        class_label=str(lbl_val),
                        class_norm=norm_label,
                        frame_count=0,
                        detection_count=0,
                        max_score=sc,
                        min_score=sc,
                    )
                
                cls_info = class_registry[mid]
                cls_info.detection_count += 1
                cls_info.max_score = max(cls_info.max_score, sc)
                cls_info.min_score = min(cls_info.min_score, sc)
                
                if mid not in by_class:
                    by_class[mid] = {
                        "class_id": cls_info.class_id,
                        "max_score": sc,
                        "count": 1,
                        "top_bbox": bbox_floats,
                        "detections": [{"score": sc, "bbox": bbox_floats, "label": str(lbl_val)}],
                    }
                else:
                    cur = by_class[mid]
                    cur["count"] += 1
                    cur["detections"].append({"score": sc, "bbox": bbox_floats, "label": str(lbl_val)})
                    if sc > cur["max_score"]:
                        cur["max_score"] = sc
                        cur["top_bbox"] = bbox_floats
                        
            # Record per-frame aggregated postings
            for mid, agg in by_class.items():
                class_registry[mid].frame_count += 1
                # Sort detections by score desc, keep top 5
                agg["detections"].sort(key=lambda d: d["score"], reverse=True)
                top_dets = agg["detections"][:5]
                
                postings_batch.append((
                    agg["class_id"],
                    kf_uid,
                    video_id,
                    kf_no,
                    frame_idx,
                    timestamp_ms,
                    round(agg["max_score"], 6),
                    agg["count"],
                    json.dumps(agg["top_bbox"]),
                    json.dumps(top_dets),
                ))
                
            if len(postings_batch) >= BATCH_SIZE:
                conn.executemany(
                    """INSERT INTO object_postings (
                        class_id, keyframe_uid, video_id, local_keyframe_no,
                        frame_idx, timestamp_ms, max_score, detection_count,
                        top_bbox_json, top_detections_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    postings_batch,
                )
                total_postings_inserted += len(postings_batch)
                postings_batch.clear()
                
    if postings_batch:
        conn.executemany(
            """INSERT INTO object_postings (
                class_id, keyframe_uid, video_id, local_keyframe_no,
                frame_idx, timestamp_ms, max_score, detection_count,
                top_bbox_json, top_detections_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            postings_batch,
        )
        total_postings_inserted += len(postings_batch)
        postings_batch.clear()
        
    # 4. Insert class dictionary rows
    class_rows = [
        (
            info.class_id,
            info.class_name,
            info.class_entity,
            info.class_label,
            info.class_norm,
            info.frame_count,
            info.detection_count,
            round(info.max_score, 6),
            round(info.min_score, 6),
        )
        for info in sorted(class_registry.values(), key=lambda x: x.class_id)
    ]
    conn.executemany(
        """INSERT INTO class_dictionary (
            class_id, class_name, class_entity, class_label, class_norm,
            frame_count, detection_count, max_score, min_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        class_rows,
    )
    
    # 5. Create indexes
    logger.info("Creating index structures on SQLite database...")
    conn.execute("CREATE INDEX idx_postings_class_score ON object_postings(class_id, max_score DESC);")
    conn.execute("CREATE INDEX idx_postings_class_video ON object_postings(class_id, video_id, max_score DESC);")
    conn.execute("CREATE INDEX idx_postings_kf ON object_postings(keyframe_uid);")
    conn.execute("CREATE INDEX idx_class_dict_norm ON class_dictionary(class_norm);")
    conn.execute("CREATE INDEX idx_class_dict_entity ON class_dictionary(class_entity);")
    conn.execute("CREATE INDEX idx_class_dict_name ON class_dictionary(class_name);")
    
    # 6. Store metadata
    conn.execute("""
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    meta_entries = [
        ("schema_version", "v1"),
        ("build_id", build_tag),
        ("source_archive", str(actual_zip)),
        ("canonical_btc_frames", str(total_frames_read)),
        ("canonical_detections", str(total_detections_read)),
        ("indexed_classes", str(len(class_registry))),
        ("total_postings", str(total_postings_inserted)),
        ("created_at", datetime.now(timezone.utc).isoformat()),
    ]
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta_entries)
    
    conn.commit()
    conn.close()
    
    # 7. Write classes.json
    classes_json_data = [
        {
            "class_id": info.class_id,
            "class_name": info.class_name,
            "class_entity": info.class_entity,
            "class_label": info.class_label,
            "class_norm": info.class_norm,
            "frame_count": info.frame_count,
            "detection_count": info.detection_count,
            "max_score": round(info.max_score, 6),
            "min_score": round(info.min_score, 6),
        }
        for info in sorted(class_registry.values(), key=lambda x: x.frame_count, reverse=True)
    ]
    with open(classes_json_file, "w", encoding="utf-8") as fp:
        json.dump(classes_json_data, fp, indent=2, ensure_ascii=False)
        
    # 8. Write passport and manifest
    db_checksum = compute_sha256(db_file)
    classes_checksum = compute_sha256(classes_json_file)
    
    passport_data = {
        "provider": "btc_objects",
        "lane_id": "btc_objects",
        "entity_type": "FRAME",
        "frame_space": "BTC",
        "score_type": "btc_object_support",
        "score_direction": "HIGHER_IS_BETTER",
        "build_id": build_tag,
        "source_archive": str(actual_zip),
        "source_archive_checksum": compute_sha256(actual_zip),
        "btc_canonical_frame_count": total_frames_read,
        "total_detection_count": total_detections_read,
        "indexed_class_count": len(class_registry),
        "total_postings_count": total_postings_inserted,
        "database_file": db_file.name,
        "database_sha256": db_checksum,
        "classes_file": classes_json_file.name,
        "classes_sha256": classes_checksum,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(passport_file, "w", encoding="utf-8") as fp:
        json.dump(passport_data, fp, indent=2, ensure_ascii=False)
        
    manifest_data = {
        "artifact_id": "btc_objects_v1",
        "build_id": build_tag,
        "files": {
            db_file.name: {
                "size_bytes": db_file.stat().st_size,
                "sha256": db_checksum,
            },
            classes_json_file.name: {
                "size_bytes": classes_json_file.stat().st_size,
                "sha256": classes_checksum,
            },
            passport_file.name: {
                "size_bytes": passport_file.stat().st_size,
                "sha256": compute_sha256(passport_file),
            },
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(manifest_file, "w", encoding="utf-8") as fp:
        json.dump(manifest_data, fp, indent=2, ensure_ascii=False)
        
    done_data = {
        "status": "COMPLETED",
        "build_id": build_tag,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.perf_counter() - t_start, 2),
    }
    with open(done_file, "w", encoding="utf-8") as fp:
        json.dump(done_data, fp, indent=2, ensure_ascii=False)
        
    # 9. Commit atomic move to final output_dir
    if out_path.exists():
        # backup or remove
        backup_dir = out_path.parent / f"_old_{out_path.name}_{int(time.time())}"
        out_path.rename(backup_dir)
        
    temp_dir.rename(out_path)
    
    elapsed = time.perf_counter() - t_start
    logger.info(
        "BTC objects index build complete in %.2fs: %d frames, %d detections, %d classes, %d postings.",
        elapsed,
        total_frames_read,
        total_detections_read,
        len(class_registry),
        total_postings_inserted,
    )
    
    return {
        "build_id": build_tag,
        "output_dir": str(out_path),
        "frames": total_frames_read,
        "detections": total_detections_read,
        "classes": len(class_registry),
        "postings": total_postings_inserted,
        "elapsed_sec": round(elapsed, 2),
        "db_sha256": db_checksum,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build compact SQLite postings index for BTC Objects (M5D)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output artifact directory")
    parser.add_argument("--zip-path", default=None, help="Path to objects zip archive")
    parser.add_argument("--mapping-db", default=str(DEFAULT_MAPPING_DB), help="Path to runtime mapping.sqlite")
    parser.add_argument("--build-id", default=None, help="Optional build ID string")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    res = build_btc_objects_index(
        output_dir=args.output_dir,
        zip_path=args.zip_path,
        mapping_db=args.mapping_db,
        build_id=args.build_id,
    )
    print("Build result:", json.dumps(res, indent=2))
