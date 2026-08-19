PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    record_count INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    producer TEXT,
    status TEXT NOT NULL DEFAULT 'READY',
    notes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    ordinal INTEGER UNIQUE,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    series TEXT NOT NULL DEFAULT '',
    relpath TEXT NOT NULL UNIQUE,
    duration_ms INTEGER,
    duration_sec REAL,
    fps REAL,
    width INTEGER,
    height INTEGER,
    batch TEXT,
    status_flags TEXT NOT NULL DEFAULT 'OK',
    source_id TEXT NOT NULL DEFAULT '',
    source_sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_videos_ordinal ON videos(ordinal);
CREATE INDEX IF NOT EXISTS idx_videos_series ON videos(series);

CREATE TABLE IF NOT EXISTS custom_keyframes (
    keyframe_uid TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    raw_pts_time REAL NOT NULL,
    shot_id INTEGER NOT NULL DEFAULT 0,
    cluster_id INTEGER NOT NULL DEFAULT 0,
    embedding_index INTEGER NOT NULL DEFAULT 0,
    source_keyframe_id INTEGER NOT NULL DEFAULT 0,
    file_name TEXT NOT NULL,
    image_relpath TEXT NOT NULL,
    qwen_status TEXT NOT NULL DEFAULT 'OK',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, frame_idx)
);

CREATE INDEX IF NOT EXISTS idx_custom_kf_video_frame ON custom_keyframes(video_id, frame_idx);
CREATE INDEX IF NOT EXISTS idx_custom_kf_video_ordinal ON custom_keyframes(video_ordinal);
CREATE INDEX IF NOT EXISTS idx_custom_kf_timestamp ON custom_keyframes(video_id, timestamp_ms);

CREATE TABLE IF NOT EXISTS qwen_frames (
    keyframe_uid TEXT PRIMARY KEY REFERENCES custom_keyframes(keyframe_uid),
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, frame_idx)
);

CREATE INDEX IF NOT EXISTS idx_qwen_video_frame ON qwen_frames(video_id, frame_idx);

CREATE TABLE IF NOT EXISTS asr_video_coverage (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    segment_count INTEGER NOT NULL,
    duration_sec REAL NOT NULL,
    duration_ms INTEGER NOT NULL,
    asr_status TEXT NOT NULL DEFAULT 'HAS_SEGMENTS',
    source_id TEXT NOT NULL DEFAULT 'asr_whisper_medium_vi_full_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asr_video_status ON asr_video_coverage(asr_status);

CREATE TABLE IF NOT EXISTS canonical_asr_segments (
    segment_uid TEXT PRIMARY KEY,
    source_segment_id TEXT NOT NULL,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    text_raw TEXT NOT NULL,
    text_norm TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'vi',
    model TEXT NOT NULL DEFAULT 'whisper-medium',
    avg_logprob REAL,
    no_speech_prob REAL,
    compression_ratio REAL,
    batch_id TEXT,
    source_file TEXT,
    source_id TEXT NOT NULL DEFAULT 'asr_whisper_medium_vi_full_v1',
    schema_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_canonical_asr_video ON canonical_asr_segments(video_id, start_ms, end_ms);
CREATE INDEX IF NOT EXISTS idx_canonical_asr_ordinal ON canonical_asr_segments(video_ordinal);

CREATE TABLE IF NOT EXISTS ocr_keyframes (
    keyframe_uid TEXT PRIMARY KEY REFERENCES custom_keyframes(keyframe_uid),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    raw_pts_time REAL NOT NULL,
    file_name TEXT NOT NULL,
    image_relpath TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    source_id TEXT NOT NULL DEFAULT 'ocr_custom_manifest_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ocr_kf_video_frame ON ocr_keyframes(video_id, frame_idx);

CREATE TABLE IF NOT EXISTS ocr_items (
    ocr_uid TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    frame_space TEXT NOT NULL DEFAULT 'CUSTOM',
    keyframe_uid TEXT NOT NULL REFERENCES ocr_keyframes(keyframe_uid),
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    raw_pts_time REAL NOT NULL,
    local_text_index INTEGER NOT NULL,
    text_raw TEXT NOT NULL,
    text_norm TEXT NOT NULL,
    bbox_json TEXT,
    ocr_confidence REAL,
    ocr_type TEXT,
    dense_embedding_ref TEXT,
    source_id TEXT NOT NULL DEFAULT 'ocr_custom_manifest_v1',
    schema_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ocr_items_kf ON ocr_items(keyframe_uid);
CREATE INDEX IF NOT EXISTS idx_ocr_items_video_time ON ocr_items(video_id, timestamp_ms);

CREATE TABLE IF NOT EXISTS ocr_bge_rowmap (
    rowmap_id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id TEXT NOT NULL DEFAULT 'ocr_bge_m3_single_text_v1',
    shard_id TEXT NOT NULL,
    row_in_shard INTEGER NOT NULL,
    global_row INTEGER,
    ocr_uid TEXT NOT NULL,
    keyframe_uid TEXT NOT NULL,
    video_id TEXT NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    source_metadata_ref TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(shard_id, row_in_shard)
);

CREATE INDEX IF NOT EXISTS idx_ocr_bge_ocr_uid ON ocr_bge_rowmap(ocr_uid);
CREATE INDEX IF NOT EXISTS idx_ocr_bge_kf_uid ON ocr_bge_rowmap(keyframe_uid);

-- Legacy tables preserved
CREATE TABLE IF NOT EXISTS keyframes (
    keyframe_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    frame_idx INTEGER NOT NULL,
    pts_time REAL,
    relpath TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'btc',
    UNIQUE(video_id, frame_idx)
);

CREATE INDEX IF NOT EXISTS idx_keyframes_video_frame ON keyframes(video_id, frame_idx);

CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    config_hash TEXT NOT NULL,
    index_version TEXT NOT NULL,
    vector_dim INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(target_type, target_id, model_name, model_version, config_hash, index_version)
);

-- Legacy transcripts table preserved
CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    text_raw TEXT NOT NULL,
    text_norm TEXT NOT NULL,
    confidence REAL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text_norm,
    content='transcripts',
    content_rowid='transcript_id'
);

CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
    INSERT INTO transcripts_fts(rowid, text_norm) VALUES (new.transcript_id, new.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text_norm) VALUES('delete', old.transcript_id, old.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text_norm) VALUES('delete', old.transcript_id, old.text_norm);
    INSERT INTO transcripts_fts(rowid, text_norm) VALUES (new.transcript_id, new.text_norm);
END;


CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    shard_id TEXT,
    model_name TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    config_hash TEXT NOT NULL,
    input_manifest_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','running','completed','failed','rejected')),
    artifact_relpath TEXT,
    started_at TEXT,
    finished_at TEXT,
    error_message TEXT,
    UNIQUE(task_type, shard_id, model_name, model_version, config_hash, input_manifest_sha256)
);

CREATE TABLE IF NOT EXISTS eval_experiments (
    experiment_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    pipeline_version TEXT,
    git_commit TEXT,
    config_json TEXT,
    notes TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS eval_queries (
    query_id INTEGER PRIMARY KEY,
    query_type TEXT NOT NULL CHECK(query_type IN ('KIS','QA','TRAKE')),
    query_text TEXT NOT NULL,
    question_text TEXT,
    trap_category TEXT,
    split TEXT NOT NULL DEFAULT 'dev' CHECK(split IN ('dev','holdout')),
    gt_video_id TEXT,
    gt_ranges_json TEXT,
    gt_answer TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id INTEGER PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES eval_experiments(experiment_id),
    query_id INTEGER NOT NULL REFERENCES eval_queries(query_id),
    submitted_answers_json TEXT NOT NULL,
    r_at_1 REAL,
    r_at_5 REAL,
    r_at_20 REAL,
    r_at_50 REAL,
    r_at_100 REAL,
    final_score REAL,
    first_correct_rank INTEGER,
    latency_ms REAL,
    run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(experiment_id, query_id)
);

-- =====================================================================
-- Canonical BTC Data Hub Tables (M1D)
-- =====================================================================

CREATE TABLE IF NOT EXISTS btc_keyframes (
    keyframe_uid TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    local_keyframe_no INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    raw_pts_time REAL NOT NULL,
    fps REAL NOT NULL,
    image_relpath TEXT NOT NULL,
    frame_space TEXT NOT NULL DEFAULT 'BTC',
    btc_space_id TEXT NOT NULL DEFAULT 'btc_keyframes_v1',
    map_source_id TEXT NOT NULL DEFAULT 'btc_map_keyframes_raw_v1',
    clip_status TEXT NOT NULL DEFAULT 'HAS_CLIP_ROW',
    object_status TEXT NOT NULL DEFAULT 'HAS_OBJECTS',
    schema_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, local_keyframe_no)
);

CREATE INDEX IF NOT EXISTS idx_btc_kf_video_n ON btc_keyframes(video_id, local_keyframe_no);
CREATE INDEX IF NOT EXISTS idx_btc_kf_video_time ON btc_keyframes(video_id, timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_btc_kf_video_ordinal ON btc_keyframes(video_ordinal);

CREATE TABLE IF NOT EXISTS btc_clip_rows (
    clip_source_id TEXT NOT NULL DEFAULT 'btc_clip_features_32_v1',
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    row_in_video INTEGER NOT NULL,
    keyframe_uid TEXT NOT NULL REFERENCES btc_keyframes(keyframe_uid),
    local_keyframe_no INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    feature_relpath TEXT NOT NULL,
    dimension INTEGER NOT NULL DEFAULT 512,
    dtype TEXT NOT NULL DEFAULT 'float16',
    normalized INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(video_id, row_in_video),
    UNIQUE(keyframe_uid)
);

CREATE INDEX IF NOT EXISTS idx_btc_clip_kf ON btc_clip_rows(keyframe_uid);

CREATE TABLE IF NOT EXISTS btc_objects (
    detection_uid TEXT PRIMARY KEY,
    keyframe_uid TEXT NOT NULL REFERENCES btc_keyframes(keyframe_uid),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    local_keyframe_no INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    local_detection_index INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    class_entity TEXT,
    class_label TEXT,
    confidence REAL NOT NULL,
    bbox_json TEXT NOT NULL,
    frame_space TEXT NOT NULL DEFAULT 'BTC',
    source_id TEXT NOT NULL DEFAULT 'btc_objects_raw_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_btc_obj_kf ON btc_objects(keyframe_uid);
CREATE INDEX IF NOT EXISTS idx_btc_obj_class ON btc_objects(class_name);
CREATE INDEX IF NOT EXISTS idx_btc_obj_entity ON btc_objects(class_entity);

CREATE TABLE IF NOT EXISTS btc_object_coverage (
    keyframe_uid TEXT PRIMARY KEY REFERENCES btc_keyframes(keyframe_uid),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    local_keyframe_no INTEGER NOT NULL,
    frame_idx INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    detection_count INTEGER NOT NULL DEFAULT 0,
    object_status TEXT NOT NULL DEFAULT 'HAS_OBJECTS',
    source_file_relpath TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_btc_obj_cov_status ON btc_object_coverage(object_status);

CREATE TABLE IF NOT EXISTS media_info (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id),
    video_ordinal INTEGER NOT NULL,
    ordinal_space_id TEXT NOT NULL DEFAULT 'v1_natural_series_video',
    title TEXT NOT NULL,
    description TEXT,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    author TEXT,
    channel_id TEXT,
    channel_url TEXT,
    publish_date TEXT,
    duration_sec INTEGER,
    thumbnail_url TEXT,
    watch_url TEXT,
    source_id TEXT NOT NULL DEFAULT 'btc_media_info_raw_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- Data Hub Runtime & Taxonomy Tables (M1E)
-- =====================================================================

CREATE TABLE IF NOT EXISTS runtime_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS taxonomy_nodes (
    branch_id TEXT PRIMARY KEY,
    branch_type TEXT NOT NULL,
    label_vi TEXT NOT NULL,
    label_en TEXT NOT NULL,
    parent_ids_json TEXT NOT NULL DEFAULT '[]',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    requires_region_index INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    source_id TEXT NOT NULL DEFAULT 'taxonomy_authority_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tax_type ON taxonomy_nodes(branch_type);

CREATE TABLE IF NOT EXISTS video_memberships (
    membership_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    branch_id TEXT NOT NULL REFERENCES taxonomy_nodes(branch_id),
    membership_type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL,
    score_type TEXT DEFAULT 'heuristic',
    evidence TEXT,
    prune_override TEXT,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    source_id TEXT NOT NULL DEFAULT 'taxonomy_authority_v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(video_id, branch_id)
);

CREATE INDEX IF NOT EXISTS idx_vm_branch_video ON video_memberships(branch_id, video_id);
CREATE INDEX IF NOT EXISTS idx_vm_video_branch ON video_memberships(video_id, branch_id);
CREATE INDEX IF NOT EXISTS idx_vm_status ON video_memberships(status);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    entity_space TEXT NOT NULL,
    logical_ref TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY',
    built_from TEXT NOT NULL,
    producer TEXT,
    notes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artifacts_space ON artifacts(entity_space);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status);

CREATE TABLE IF NOT EXISTS vector_indexes (
    index_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    entity_space TEXT NOT NULL,
    frame_space TEXT,
    model_id TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    dtype TEXT NOT NULL,
    normalized INTEGER NOT NULL DEFAULT 1,
    row_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    logical_ref TEXT NOT NULL,
    built_from TEXT NOT NULL,
    model_revision TEXT,
    metric TEXT,
    rowmap_count INTEGER,
    rowmap_checksum TEXT,
    artifact_checksum TEXT,
    query_preprocessing_version TEXT,
    ordinal_space_id TEXT,
    notes_json TEXT NOT NULL DEFAULT '[]',
    schema_version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vec_space ON vector_indexes(entity_space);
CREATE INDEX IF NOT EXISTS idx_vec_status ON vector_indexes(status);

-- =====================================================================
-- Modality-Separated FTS5 Virtual Tables (M1E)
-- =====================================================================

CREATE VIRTUAL TABLE IF NOT EXISTS asr_fts USING fts5(
    segment_uid UNINDEXED,
    video_id UNINDEXED,
    text_raw,
    text_norm,
    text_accentless,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
    ocr_uid UNINDEXED,
    keyframe_uid UNINDEXED,
    video_id UNINDEXED,
    text_raw,
    text_norm,
    text_accentless,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS qwen_caption_fts USING fts5(
    keyframe_uid UNINDEXED,
    video_id UNINDEXED,
    caption_raw,
    caption_norm,
    caption_accentless,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
    video_id UNINDEXED,
    title_raw,
    title_norm,
    title_accentless,
    keywords,
    description,
    tokenize = 'unicode61'
);


