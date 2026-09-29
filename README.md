# EnergyOps — Industrial Energy Intelligence

Phase 1 is a reproducible intake and quality foundation for the [UCI Steel Industry Energy Consumption dataset](https://archive.ics.uci.edu/dataset/851/steel%2Bindustry%2Benergy%2Bconsumption). It checks source identity, schema, timestamps, categories, numeric values and interval continuity. The local CSV is ignored by Git; [`evidence/source_profile.json`](evidence/source_profile.json) holds aggregate evidence.

Start with [START_HERE.md](START_HERE.md) for setup and commands. The [data contract](docs/DATA_CONTRACT.md), [quality audit](docs/DATA_QUALITY.md), [source attribution](docs/SOURCE_ATTRIBUTION.md), [limitations](docs/LIMITATIONS.md), and [architecture](docs/ARCHITECTURE.md) describe the source and project scope.

Planned later phases include PostgreSQL raw/staging/analytical models, historical baselines, investigation rules, Apache Superset 3.0, local Celery/Redis/Mailpit alert verification, and a public snapshot presented with Streamlit. None of these components is implemented in Phase 1. The dataset provides historical plant-level observations and cannot prove waste, savings, carbon reduction, OEE or equipment failure.
