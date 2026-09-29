# EnergyOps — Industrial Energy Intelligence

Phases 1–2 provide a reproducible intake and local PostgreSQL foundation for the [UCI Steel Industry Energy Consumption dataset](https://archive.ics.uci.edu/dataset/851/steel%2Bindustry%2Benergy%2Bconsumption). They check source identity and quality, load typed historical records with an audit and rejection path, and expose a staging view. The local CSV is ignored by Git; [`evidence/source_profile.json`](evidence/source_profile.json) holds the source baseline. `python scripts/verify_phase2.py` writes `evidence/phase2_reconciliation.json` after a verified database load.

Start with [START_HERE.md](START_HERE.md) for setup and commands. The [data contract](docs/DATA_CONTRACT.md), [quality audit](docs/DATA_QUALITY.md), [PostgreSQL guide](docs/POSTGRESQL.md), [ingestion guide](docs/INGESTION.md), [source attribution](docs/SOURCE_ATTRIBUTION.md), [limitations](docs/LIMITATIONS.md), and [architecture](docs/ARCHITECTURE.md) describe the source and project scope.

Planned later phases include analytical SQL models, historical baselines, investigation rules, Apache Superset 3.0, local Celery/Redis/Mailpit alert verification, and a public snapshot presented with Streamlit. These components are not implemented. The dataset provides historical plant-level observations and cannot prove waste, savings, carbon reduction, OEE or equipment failure.
