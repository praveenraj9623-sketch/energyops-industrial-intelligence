# EnergyOps architecture

Phase 1 implements local source intake, provenance, validation, profiling and tests. Phase 2 adds a local PostgreSQL 16 service, typed raw loading with rejection/audit tables, and a staging view. Downstream nodes are planned only.

```mermaid
flowchart LR
    A[UCI historical CSV] --> B[Python validation and profiling<br/>Phase 1 implemented]
    B --> C[PostgreSQL raw and monitoring<br/>Phase 2 implemented]
    C --> D[Staging view<br/>Phase 2 implemented]
    D -. planned .-> E[Analytical SQL models]
    E -. planned .-> F[Baselines and investigation rules]
    F -. planned .-> G[Apache Superset 3.0]
    F -. planned .-> H[Celery / Redis / Mailpit<br/>local alert verification]
    G -. planned .-> I[Public snapshot]
    H -. planned .-> I
    I -. planned .-> J[Streamlit presentation]
```

Phase 1 stores the original CSV in a Git-ignored local path and emits a checked-in aggregate JSON profile. Phase 2 checks its checksum, streams typed readings into `raw`, retains rejected rows and audit runs, and exposes a nonmaterialized staging view. `analytics` exists but is empty. Analytical models and rules will require separate documented eligibility before dashboards or alerts are built. The eventual public snapshot must be a historical presentation, not a live operational feed.
