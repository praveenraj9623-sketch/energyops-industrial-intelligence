CREATE TABLE IF NOT EXISTS monitoring.ingestion_runs (
    ingestion_run_id UUID PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL CHECK (source_file_sha256 ~ '^[0-9a-f]{64}$'),
    source_file_size_bytes BIGINT NOT NULL CHECK (source_file_size_bytes >= 0),
    source_expected_rows INTEGER,
    source_read_rows INTEGER NOT NULL DEFAULT 0,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0,
    inserted_rows INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    run_status TEXT NOT NULL CHECK (run_status IN ('running','completed','failed','skipped_duplicate')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    pipeline_version TEXT NOT NULL,
    source_min_timestamp TIMESTAMP WITHOUT TIME ZONE,
    source_max_timestamp TIMESTAMP WITHOUT TIME ZONE,
    timezone_status TEXT NOT NULL DEFAULT 'unspecified' CHECK (timezone_status = 'unspecified'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_read_rows >= 0 AND accepted_rows >= 0 AND rejected_rows >= 0
           AND inserted_rows >= 0 AND duplicate_rows >= 0)
);
