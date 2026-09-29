# Source attribution and provenance

- **Dataset:** Steel Industry Energy Consumption, UCI Machine Learning Repository dataset 851.
- **Creators:** Sathishkumar V E, Changsun Shin and Yongyun Cho.
- **Citation:** V E, S., Shin, C., & Cho, Y. (2021). *Steel Industry Energy Consumption* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C52G8C
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Source:** https://archive.ics.uci.edu/dataset/851/steel%2Bindustry%2Benergy%2Bconsumption
- **Access method:** manually downloaded ZIP outside the repository and extracted locally; CSV copied into ignored `data/raw/` for profiling.
- **Download date:** 2026-09-29, based on the local ZIP modification timestamp; no separate HTTP download log is available.
- **Source filename:** `Steel_industry_data.csv` (2,731,389 bytes).
- **CSV SHA-256:** `9b1cee6f9cb9cd9df2b95814ca90a9a2ff15b7f5f1fba0fae3c643e82072eacc`.
- **Archive filename:** `steel-industry-energy-consumption.zip` (481,973 bytes).
- **ZIP SHA-256:** `d82d28b33780ff1582507fcf08ae764ff648af459d58234370c551e62aadeaef`.

The repository records checksums and a small profile, not the downloaded data or ZIP. UCI lists the `CO2(tCO2)` field's unit as `ppm`, conflicting with its label; its feature-count summary and WeekStatus coding description also differ from the actual CSV. These discrepancies are documented in the [contract](DATA_CONTRACT.md) and [quality audit](DATA_QUALITY.md).
