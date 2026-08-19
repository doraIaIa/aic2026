"""Qwen Structured Facet Index Builder and Vocabulary Normalization (M5A).

Builds a deterministic, explainable structured facet postings index over the
116,767 canonical Qwen observations attached to CUSTOM keyframes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CANONICAL_CUSTOM_FRAME_COUNT = 116767
CANONICAL_QWEN_ROW_COUNT = 116767
NORMALIZER_VERSION = "deterministic_text_v1"
ALIAS_POLICY_VERSION = "explicit_alias_v1"

# Semantic namespace definitions
NAMESPACE_MAPPING = {
    "objects_json": "object",
    "attributes_json": "attribute",
    "spatial_relations_json": "relation",
    "counts_json": "count",
    "scene_json": "scene",
    "visible_actions_json": "action",
}

VALID_NAMESPACES = set(NAMESPACE_MAPPING.values())


def normalize_facet_phrase(phrase: str) -> str:
    """Deterministic, conservative normalization for facet phrases.
    
    1. Unicode NFC
    2. Lowercase / casefold
    3. Collapse multiple whitespace
    4. Strip non-alphanumeric leading/trailing punctuation while preserving internal hyphens/apostrophes.
    """
    if not phrase or not isinstance(phrase, str):
        return ""
    # NFC normalization
    s = unicodedata.normalize("NFC", phrase).strip()
    # Lowercase
    s = s.casefold()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # Strip edge punctuation (like quotes, colons, brackets, dots at edges)
    s = re.sub(r"^[\s\"'“”‘’\(\)\[\]\{\}\.,:;!?\-_/\\#@]+", "", s)
    s = re.sub(r"[\s\"'“”‘’\(\)\[\]\{\}\.,:;!?\-_/\\#@]+$", "", s)
    return s.strip()


def to_accentless(phrase: str) -> str:
    """Derive accentless search alias without changing semantic token boundaries."""
    if not phrase:
        return ""
    # NFD decomposition to split diacritics
    nfd = unicodedata.normalize("NFD", phrase)
    without_diacritics = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Replace Vietnamese D/d with stroke
    without_diacritics = without_diacritics.replace("đ", "d").replace("Đ", "d")
    return unicodedata.normalize("NFC", without_diacritics).strip()


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file in 64KB blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class VocabularyAuditReport:
    total_qwen_rows: int
    frames_with_zero_facets: int
    frames_with_any_facets: int
    namespace_metrics: dict[str, dict[str, Any]]
    total_raw_observations: int
    total_unique_raw_phrases: int
    total_unique_normalized_facets: int
    safe_normalization_collisions: int
    review_required_collisions: int


def run_vocabulary_audit(conn: sqlite3.Connection) -> tuple[VocabularyAuditReport, dict[str, Any]]:
    """Inspect all 116,767 Qwen observations and compute detailed namespace statistics."""
    c = conn.cursor()
    
    # Check total rows
    total_rows = c.execute("SELECT COUNT(*) FROM qwen_frames").fetchone()[0]
    if total_rows != CANONICAL_QWEN_ROW_COUNT:
        raise ValueError(f"Qwen row count mismatch: expected {CANONICAL_QWEN_ROW_COUNT}, got {total_rows}")
        
    namespace_raw_counts: dict[str, Counter[str]] = {ns: Counter() for ns in VALID_NAMESPACES}
    namespace_norm_counts: dict[str, Counter[str]] = {ns: Counter() for ns in VALID_NAMESPACES}
    namespace_frame_counts: dict[str, set[str]] = {ns: set() for ns in VALID_NAMESPACES}
    namespace_video_counts: dict[str, set[str]] = {ns: set() for ns in VALID_NAMESPACES}
    
    # Track collisions: normalized_key -> set of raw variants
    norm_to_raw: dict[tuple[str, str], set[str]] = defaultdict(set)
    
    frames_with_facets = set()
    
    c.execute("""
        SELECT keyframe_uid, video_id, objects_json, attributes_json, spatial_relations_json, counts_json, scene_json, visible_actions_json
        FROM qwen_frames
    """)
    
    for row in c:
        uid = row[0]
        vid = row[1]
        has_any_facet = False
        
        for col_idx, (col_name, ns) in enumerate(NAMESPACE_MAPPING.items(), start=2):
            raw_json = row[col_idx]
            if not raw_json or raw_json == "[]":
                continue
            try:
                items = json.loads(raw_json)
                if not isinstance(items, list):
                    items = [items] if isinstance(items, str) else []
            except Exception:
                continue
                
            for item in items:
                if not item or not isinstance(item, str):
                    continue
                raw_str = item.strip()
                if not raw_str:
                    continue
                    
                norm_str = normalize_facet_phrase(raw_str)
                if not norm_str:
                    continue
                    
                has_any_facet = True
                namespace_raw_counts[ns][raw_str] += 1
                namespace_norm_counts[ns][norm_str] += 1
                namespace_frame_counts[ns].add(uid)
                namespace_video_counts[ns].add(vid)
                norm_to_raw[(ns, norm_str)].add(raw_str)
                
        if has_any_facet:
            frames_with_facets.add(uid)
            
    # Calculate collision categories
    safe_collisions = 0
    review_collisions = 0
    collision_details = []
    
    for (ns, norm_str), raw_set in norm_to_raw.items():
        if len(raw_set) > 1:
            # Check if differences are purely case/whitespace/edge punctuation
            is_purely_format = all(
                re.sub(r"[^\w\s]", "", r.casefold()).strip() == re.sub(r"[^\w\s]", "", norm_str).strip()
                for r in raw_set
            )
            if is_purely_format:
                safe_collisions += 1
            else:
                review_collisions += 1
                if len(collision_details) < 20:
                    collision_details.append({
                        "namespace": ns,
                        "normalized": norm_str,
                        "raw_variants": list(raw_set)[:5],
                    })

    namespace_metrics = {}
    total_raw_obs = 0
    total_unique_raw = 0
    total_unique_norm = 0

    for ns in sorted(VALID_NAMESPACES):
        raw_cnt = namespace_raw_counts[ns]
        norm_cnt = namespace_norm_counts[ns]
        frames_cnt = len(namespace_frame_counts[ns])
        
        obs_count = sum(raw_cnt.values())
        unique_raw = len(raw_cnt)
        unique_norm = len(norm_cnt)
        
        total_raw_obs += obs_count
        total_unique_raw += unique_raw
        total_unique_norm += unique_norm
        
        phrase_lens = [len(phrase) for phrase in raw_cnt.keys()]
        if phrase_lens:
            phrase_lens.sort()
            p50 = phrase_lens[len(phrase_lens) // 2]
            p90 = phrase_lens[int(len(phrase_lens) * 0.9)]
            p99 = phrase_lens[int(len(phrase_lens) * 0.99)]
            max_len = phrase_lens[-1]
            longest_phrase = max(raw_cnt.keys(), key=len)[:60]
        else:
            p50 = p90 = p99 = max_len = 0
            longest_phrase = ""
            
        top_50 = [{"phrase": p, "count": c} for p, c in norm_cnt.most_common(50)]
        
        namespace_metrics[ns] = {
            "total_observations": obs_count,
            "unique_raw_phrases": unique_raw,
            "unique_normalized_facets": unique_norm,
            "frames_with_values": frames_cnt,
            "frames_without_values": total_rows - frames_cnt,
            "top_50_frequencies": top_50,
            "p50_length": p50,
            "p90_length": p90,
            "p99_length": p99,
            "max_length": max_len,
            "longest_sample": longest_phrase,
        }

    report = VocabularyAuditReport(
        total_qwen_rows=total_rows,
        frames_with_zero_facets=total_rows - len(frames_with_facets),
        frames_with_any_facets=len(frames_with_facets),
        namespace_metrics=namespace_metrics,
        total_raw_observations=total_raw_obs,
        total_unique_raw_phrases=total_unique_raw,
        total_unique_normalized_facets=total_unique_norm,
        safe_normalization_collisions=safe_collisions,
        review_required_collisions=review_collisions,
    )
    
    audit_dict = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "normalizer_version": NORMALIZER_VERSION,
        "alias_policy": ALIAS_POLICY_VERSION,
        "summary": asdict(report),
        "collision_sample": collision_details,
    }
    
    return report, audit_dict


def build_qwen_structured_index(
    runtime_db_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Builds the derived qwen_facets.sqlite index, passport, and audit files."""
    t0 = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    sqlite_out = output_dir / "qwen_facets.sqlite"
    if sqlite_out.exists():
        sqlite_out.unlink()
        
    src_conn = sqlite3.connect(runtime_db_path)
    src_conn.row_factory = sqlite3.Row
    
    # 1. Run vocabulary audit
    logger.info("Running Qwen vocabulary audit...")
    audit_report, audit_dict = run_vocabulary_audit(src_conn)
    
    with open(output_dir / "vocabulary_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_dict, f, indent=2, ensure_ascii=False)
        
    with open(output_dir / "vocabulary_audit.md", "w", encoding="utf-8") as f:
        f.write("# Qwen Vocabulary Audit Report (M5A)\n\n")
        f.write(f"- **Total Qwen rows:** {audit_report.total_qwen_rows}\n")
        f.write(f"- **Frames with structured facets:** {audit_report.frames_with_any_facets}\n")
        f.write(f"- **Frames with zero structured facets:** {audit_report.frames_with_zero_facets}\n")
        f.write(f"- **Total raw observations:** {audit_report.total_raw_observations}\n")
        f.write(f"- **Unique normalized facets:** {audit_report.total_unique_normalized_facets}\n")
        f.write(f"- **Safe formatting collisions:** {audit_report.safe_normalization_collisions}\n")
        f.write(f"- **Review required collisions:** {audit_report.review_required_collisions}\n\n")
        f.write("## Namespace Metrics\n\n")
        f.write("| Namespace | Observations | Unique Facets | Frame Coverage | p50 / p90 Len |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for ns, m in sorted(audit_report.namespace_metrics.items()):
            f.write(f"| `{ns}` | {m['total_observations']:,} | {m['unique_normalized_facets']:,} | {m['frames_with_values']:,} | {m['p50_length']} / {m['p90_length']} chars |\n")
            
    # 2. Build Derived SQLite Index
    logger.info("Building derived qwen_facets.sqlite database...")
    dest_conn = sqlite3.connect(sqlite_out)
    dest_conn.execute("PRAGMA journal_mode = WAL")
    dest_conn.execute("PRAGMA synchronous = NORMAL")
    
    dest_conn.executescript("""
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
            normalization_method TEXT NOT NULL,
            FOREIGN KEY (facet_ordinal) REFERENCES facet_dictionary(facet_ordinal)
        );

        CREATE TABLE frame_facets (
            frame_ordinal INTEGER NOT NULL,
            facet_ordinal INTEGER NOT NULL,
            raw_value TEXT NOT NULL,
            source_field TEXT NOT NULL,
            PRIMARY KEY (frame_ordinal, facet_ordinal, raw_value),
            FOREIGN KEY (frame_ordinal) REFERENCES frame_registry(frame_ordinal),
            FOREIGN KEY (facet_ordinal) REFERENCES facet_dictionary(facet_ordinal)
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
    
    # 3. Read source rows and populate frame_registry
    logger.info("Populating frame_registry from mapping.sqlite...")
    src_cursor = src_conn.cursor()
    src_cursor.execute("""
        SELECT keyframe_uid, video_id, frame_idx, timestamp_ms, caption, semantic_status,
               objects_json, attributes_json, spatial_relations_json, counts_json, scene_json, visible_actions_json
        FROM qwen_frames
        ORDER BY video_id, frame_idx
    """)
    
    # Mapping data structures
    facet_map: dict[tuple[str, str], int] = {}  # (namespace, canonical_norm) -> facet_ordinal
    facet_df_frames: Counter[int] = Counter()
    facet_df_videos: dict[int, set[str]] = defaultdict(set)
    facet_raw_aliases: dict[int, set[str]] = defaultdict(set)
    
    frame_rows = []
    frame_facets_batch = []
    
    frame_ordinal = 1
    total_postings = 0
    
    for row in src_cursor:
        uid = row["keyframe_uid"]
        vid = row["video_id"]
        frame_idx = row["frame_idx"]
        ts_ms = row["timestamp_ms"]
        caption = row["caption"] or ""
        status = row["semantic_status"] or "OK"
        
        frame_rows.append((frame_ordinal, uid, vid, frame_idx, ts_ms, caption, status))
        
        # Process namespaces
        seen_facets_in_frame: set[int] = set()
        
        for col_name, ns in NAMESPACE_MAPPING.items():
            raw_json = row[col_name]
            if not raw_json or raw_json == "[]":
                continue
            try:
                items = json.loads(raw_json)
                if not isinstance(items, list):
                    items = [items] if isinstance(items, str) else []
            except Exception:
                continue
                
            for item in items:
                if not item or not isinstance(item, str):
                    continue
                raw_str = item.strip()
                if not raw_str:
                    continue
                    
                norm_str = normalize_facet_phrase(raw_str)
                if not norm_str:
                    continue
                    
                facet_key = (ns, norm_str)
                if facet_key not in facet_map:
                    new_ord = len(facet_map) + 1
                    facet_map[facet_key] = new_ord
                    
                f_ord = facet_map[facet_key]
                facet_raw_aliases[f_ord].add(raw_str)
                
                # Add frame facet posting (dedup identical within same frame/facet/raw_value)
                frame_facets_batch.append((frame_ordinal, f_ord, raw_str, col_name))
                total_postings += 1
                
                if f_ord not in seen_facets_in_frame:
                    seen_facets_in_frame.add(f_ord)
                    facet_df_frames[f_ord] += 1
                    facet_df_videos[f_ord].add(vid)
                    
        frame_ordinal += 1
        
    # Insert frame_registry
    dest_conn.executemany(
        "INSERT INTO frame_registry VALUES (?, ?, ?, ?, ?, ?, ?)",
        frame_rows
    )
    
    # Insert facet_dictionary
    logger.info(f"Inserting {len(facet_map)} unique facets into facet_dictionary...")
    facet_dict_rows = []
    facet_fts_rows = []
    facet_alias_rows = []
    
    for (ns, norm_str), f_ord in sorted(facet_map.items(), key=lambda x: x[1]):
        facet_id = f"{ns}/{norm_str}"
        df_f = facet_df_frames[f_ord]
        df_v = len(facet_df_videos[f_ord])
        
        facet_dict_rows.append((f_ord, facet_id, ns, norm_str, df_f, df_v))
        
        # Primary FTS term
        accentless = to_accentless(norm_str)
        facet_fts_rows.append((f_ord, facet_id, ns, norm_str, norm_str, accentless))
        
        # Raw alias terms
        for raw_v in facet_raw_aliases[f_ord]:
            if raw_v.casefold() != norm_str:
                facet_alias_rows.append((f_ord, raw_v, "raw_variant"))
                raw_accentless = to_accentless(raw_v.casefold())
                facet_fts_rows.append((f_ord, facet_id, ns, raw_v, raw_v.casefold(), raw_accentless))
                
    dest_conn.executemany(
        "INSERT INTO facet_dictionary (facet_ordinal, facet_id, namespace, canonical_value, df_frames, df_videos) VALUES (?, ?, ?, ?, ?, ?)",
        facet_dict_rows
    )
    
    if facet_alias_rows:
        dest_conn.executemany(
            "INSERT INTO facet_aliases (facet_ordinal, alias_value, normalization_method) VALUES (?, ?, ?)",
            facet_alias_rows
        )
        
    dest_conn.executemany(
        "INSERT INTO facet_fts (facet_ordinal, facet_id, namespace, term_raw, term_norm, term_accentless) VALUES (?, ?, ?, ?, ?, ?)",
        facet_fts_rows
    )
    
    # Insert frame_facets
    logger.info(f"Inserting {len(frame_facets_batch)} frame facet postings...")
    # Deduplicate exact tuples in batch before insertion
    unique_frame_facets = list(set(frame_facets_batch))
    dest_conn.executemany(
        "INSERT OR IGNORE INTO frame_facets (frame_ordinal, facet_ordinal, raw_value, source_field) VALUES (?, ?, ?, ?)",
        unique_frame_facets
    )
    
    # Create indexes
    logger.info("Creating relational indexes...")
    dest_conn.executescript("""
        CREATE INDEX idx_frame_facets_facet ON frame_facets (facet_ordinal, frame_ordinal);
        CREATE INDEX idx_frame_facets_frame ON frame_facets (frame_ordinal);
        CREATE INDEX idx_facet_dict_ns ON facet_dictionary (namespace, canonical_value);
        CREATE INDEX idx_frame_reg_vid ON frame_registry (video_id);
    """)
    
    dest_conn.commit()
    dest_conn.close()
    src_conn.close()
    
    elapsed_sec = time.perf_counter() - t0
    sha256 = compute_sha256(sqlite_out)
    sqlite_size_bytes = sqlite_out.stat().st_size
    
    # 4. Generate Passport & DONE.json
    passport = {
        "artifact_id": "qwen_structured_v1",
        "artifact_type": "QWEN_STRUCTURED_POSTINGS",
        "entity_space": "CUSTOM_FRAME",
        "canonical_qwen_rows": CANONICAL_QWEN_ROW_COUNT,
        "custom_frame_rows": CANONICAL_CUSTOM_FRAME_COUNT,
        "frame_registry_rows": len(frame_rows),
        "frames_with_zero_structured_facets": audit_report.frames_with_zero_facets,
        "frames_with_any_structured_facets": audit_report.frames_with_any_facets,
        "total_unique_facets": len(facet_map),
        "total_postings": len(unique_frame_facets),
        "normalizer_version": NORMALIZER_VERSION,
        "alias_policy_version": ALIAS_POLICY_VERSION,
        "facet_counts_by_namespace": {
            ns: m["unique_normalized_facets"] for ns, m in audit_report.namespace_metrics.items()
        },
        "observation_counts_by_namespace": {
            ns: m["total_observations"] for ns, m in audit_report.namespace_metrics.items()
        },
        "sqlite_checksum_sha256": sha256,
        "sqlite_size_bytes": sqlite_size_bytes,
        "build_duration_sec": round(elapsed_sec, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "OK",
    }
    
    with open(output_dir / "qwen_structured_passport.json", "w", encoding="utf-8") as f:
        json.dump(passport, f, indent=2, ensure_ascii=False)
        
    done_payload = {
        "status": "PASS",
        "artifact_id": "qwen_structured_v1",
        "frame_registry_rows": len(frame_rows),
        "total_unique_facets": len(facet_map),
        "total_postings": len(unique_frame_facets),
        "sqlite_sha256": sha256,
        "build_duration_sec": round(elapsed_sec, 2),
    }
    with open(output_dir / "DONE.json", "w", encoding="utf-8") as f:
        json.dump(done_payload, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Qwen structured index built successfully in {elapsed_sec:.2f}s: {sqlite_out} (SHA256: {sha256})")
    return passport
