"""CPI-U annual averages for inflation-adjusted wage comparisons."""
from __future__ import annotations

from pathlib import Path

SERIES = "CUUR0000SA0"
URL = "https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems"


def read_annual_cpi(path: Path) -> dict[int, float]:
    """Annual-average CPI-U (period M13) by year from the BLS flat file."""
    out = {}
    lines = Path(path).read_text().splitlines()
    if not lines or "series_id" not in lines[0]:
        raise ValueError(f"{path}: not a BLS time-series flat file")
    for line in lines[1:]:
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4:
            continue
        series, year, period, value = parts[:4]
        if series == SERIES and period == "M13":
            out[int(year)] = float(value)
    return out


def deflate(value: float | None, year: int, base_year: int, cpi: dict[int, float]) -> float | None:
    """Express a nominal value from ``year`` in ``base_year`` dollars."""
    if value is None or year not in cpi or base_year not in cpi:
        return None
    return value * cpi[base_year] / cpi[year]
