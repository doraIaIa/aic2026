PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    relpath TEXT NOT NULL UNIQUE,
    duration_sec REAL,
    fps REAL,
    width INTEGER,
    height INTEGER,
    batch TEXT,
    source_sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS ocr_text (
    ocr_id INTEGER PRIMARY KEY,
    keyframe_id TEXT NOT NULL REFERENCES keyframes(keyframe_id),
    text_raw TEXT NOT NULL,
    text_norm TEXT NOT NULL,
    confidence REAL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
    text_norm,
    content='ocr_text',
    content_rowid='ocr_id'
);

CREATE TRIGGER IF NOT EXISTS ocr_ai AFTER INSERT ON ocr_text BEGIN
    INSERT INTO ocr_fts(rowid, text_norm) VALUES (new.ocr_id, new.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS ocr_ad AFTER DELETE ON ocr_text BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text_norm) VALUES('delete', old.ocr_id, old.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS ocr_au AFTER UPDATE ON ocr_text BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text_norm) VALUES('delete', old.ocr_id, old.text_norm);
    INSERT INTO ocr_fts(rowid, text_norm) VALUES (new.ocr_id, new.text_norm);
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
