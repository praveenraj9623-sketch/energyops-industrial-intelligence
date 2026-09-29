CREATE TABLE IF NOT EXISTS raw.steel_energy_readings (
    reading_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_timestamp_local TIMESTAMP WITHOUT TIME ZONE NOT NULL UNIQUE,
    usage_kwh NUMERIC NOT NULL CHECK (usage_kwh >= 0),
    lagging_reactive_power_kvarh NUMERIC NOT NULL CHECK (lagging_reactive_power_kvarh >= 0),
    leading_reactive_power_kvarh NUMERIC NOT NULL CHECK (leading_reactive_power_kvarh >= 0),
    co2_value NUMERIC NOT NULL CHECK (co2_value >= 0),
    lagging_power_factor_pct NUMERIC NOT NULL CHECK (lagging_power_factor_pct BETWEEN 0 AND 100),
    leading_power_factor_pct NUMERIC NOT NULL CHECK (leading_power_factor_pct BETWEEN 0 AND 100),
    seconds_from_midnight INTEGER NOT NULL CHECK (seconds_from_midnight BETWEEN 0 AND 86399),
    week_status TEXT NOT NULL CHECK (week_status IN ('Weekday','Weekend')),
    day_of_week TEXT NOT NULL CHECK (day_of_week IN ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')),
    load_type TEXT NOT NULL CHECK (load_type IN ('Light_Load','Medium_Load','Maximum_Load')),
    source_row_number INTEGER NOT NULL CHECK (source_row_number >= 2),
    source_filename TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL CHECK (source_file_sha256 ~ '^[0-9a-f]{64}$'),
    ingestion_run_id UUID NOT NULL REFERENCES monitoring.ingestion_runs(ingestion_run_id),
    source_timezone_status TEXT NOT NULL DEFAULT 'unspecified' CHECK (source_timezone_status = 'unspecified'),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_file_sha256, source_row_number)
);

CREATE TABLE IF NOT EXISTS raw.steel_energy_rejections (
    rejection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingestion_run_id UUID NOT NULL REFERENCES monitoring.ingestion_runs(ingestion_run_id),
    source_filename TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number >= 2),
    raw_payload JSONB NOT NULL,
    rejection_reasons JSONB NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
