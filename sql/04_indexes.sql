-- The UNIQUE timestamp and (hash,row) constraints already supply btree indexes.
CREATE INDEX IF NOT EXISTS readings_load_type_idx ON raw.steel_energy_readings(load_type);
CREATE INDEX IF NOT EXISTS readings_week_status_idx ON raw.steel_energy_readings(week_status);
CREATE INDEX IF NOT EXISTS readings_day_of_week_idx ON raw.steel_energy_readings(day_of_week);
CREATE INDEX IF NOT EXISTS readings_ingestion_run_idx ON raw.steel_energy_readings(ingestion_run_id);
CREATE INDEX IF NOT EXISTS ingestion_runs_source_hash_idx ON monitoring.ingestion_runs(source_file_sha256);
