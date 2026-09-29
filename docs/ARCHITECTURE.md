# EnergyOps architecture

Only local source intake, provenance, validation, profiling, tests and documentation are implemented in Phase 1. The remaining nodes show design intent and have no running service or model in this repository.

```mermaid
flowchart LR
    A[UCI historical CSV] --> B[Python validation and profiling<br/>Phase 1 implemented]
    B -. planned .-> C[PostgreSQL raw layer]
    C -. planned .-> D[Staging layer]
    D -. planned .-> E[Analytical SQL models]
    E -. planned .-> F[Baselines and investigation rules]
    F -. planned .-> G[Apache Superset 3.0]
    F -. planned .-> H[Celery / Redis / Mailpit<br/>local alert verification]
    G -. planned .-> I[Public snapshot]
    H -. planned .-> I
    I -. planned .-> J[Streamlit presentation]
```

Phase 1 stores the original CSV in a Git-ignored local path and emits a checked-in aggregate JSON profile. `source_validation.py` defines the exact schema and quality checks. The raw future layer should preserve source values and identity. Staging should apply explicit mappings and quarantine violations. Analytical models and rules will require separate documented eligibility and reconciliation before dashboards or alerts are built. The eventual public snapshot must be a historical presentation, not a live operational feed.
