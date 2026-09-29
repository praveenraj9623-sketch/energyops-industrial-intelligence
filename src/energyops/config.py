"""Repository paths and source selection."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "raw" / "Steel_industry_data.csv"
DEFAULT_PROFILE = PROJECT_ROOT / "evidence" / "source_profile.json"


def source_path(cli_path: str | Path | None = None) -> Path:
    """CLI path takes precedence over environment and repository default."""
    selected = cli_path or os.environ.get("ENERGYOPS_SOURCE_CSV") or DEFAULT_SOURCE
    path = Path(selected).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Source CSV not found: {path}. Pass --source, set ENERGYOPS_SOURCE_CSV, "
            "or put Steel_industry_data.csv in data/raw/."
        )
    return path
