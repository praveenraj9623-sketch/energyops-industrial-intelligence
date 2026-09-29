# Reproduce Phase 1

Use Python 3.11 from the repository root. The dataset is distributed by [UCI under CC BY 4.0](docs/SOURCE_ATTRIBUTION.md); download and extract it yourself. Place `Steel_industry_data.csv` in `data/raw/` (Git ignored). Optionally retain the ZIP outside the repository to record its checksum.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts/profile_source.py --archive 'C:\Users\admin\Downloads\energyops-source\steel-industry-energy-consumption.zip'
python -m pytest -q
python scripts/verify_phase1.py
git check-ignore -v data/raw/Steel_industry_data.csv
git status --short
```

If the CSV is elsewhere, pass `--source path\to\Steel_industry_data.csv` to both scripts or set `ENERGYOPS_SOURCE_CSV` in the environment. `--archive` is optional; omitting it records no ZIP checksum in a regenerated profile. The archived ZIP is never needed for validation. `verify_phase1.py` compares the CSV fingerprint with the saved profile and checks the Phase 1 quality gates.
