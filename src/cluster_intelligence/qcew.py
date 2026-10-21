"""BLS Quarterly Census of Employment and Wages (QCEW): parsing, suppression
handling and county-to-metro aggregation.

Source files are the annual-average "area slices" from the QCEW Open Data
interface: https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv

Rules applied here (documented in docs/methodology.md):

* Only private ownership (own_code 5) is used, for local and national values.
* A row with disclosure_code "N" is suppressed. BLS writes 0 in the value
  columns of such rows; those zeros are replaced with missing values.
* A county with no row for an industry has no establishments in it, which is a
  true zero, but only when that county's file for the year was loaded.
* A metro value is the sum of its constituent counties when every county is
  disclosed. Otherwise the BLS-published metro value is used, but only for
  years in which the published metro total matches the sum of our county list
  (i.e. BLS's delineation for that year equals ours). Otherwise it is missing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .geography import Metro

OWN_PRIVATE = "5"
# agglvl codes for private-ownership totals, NAICS sectors and 3-digit subsectors.
AGGLVL = {
    "national": {"11": "total", "14": "sector", "15": "subsector"},
    "state": {"51": "total", "54": "sector", "55": "subsector"},
    "msa": {"41": "total", "44": "sector", "45": "subsector"},
    "county": {"71": "total", "74": "sector", "75": "subsector"},
}
# Unclassified establishments are part of the totals but are not an industry.
EXCLUDED_INDUSTRIES = {"99", "999"}
CONSISTENCY_TOLERANCE = 0.001  # 0.1% of total private employment

REQUIRED_COLUMNS = [
    "area_fips", "own_code", "industry_code", "agglvl_code", "year",
    "disclosure_code", "annual_avg_estabs", "annual_avg_emplvl", "total_annual_wages",
]


def area_url(year: int, area: str) -> str:
    return f"https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv"


def raw_path(raw_dir: Path, year: int, area: str) -> Path:
    return Path(raw_dir) / "qcew" / str(year) / f"{area}.csv"


def read_area_file(path: Path, kind: str) -> pd.DataFrame:
    """Read one QCEW area CSV and return private-ownership rows at the
    aggregation levels used here, with suppressed values set to NaN."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing QCEW columns {missing}")
    levels = AGGLVL[kind]
    df = df[(df["own_code"] == OWN_PRIVATE) & (df["agglvl_code"].isin(levels))].copy()
    if "qtr" in df.columns:
        df = df[df["qtr"].isin(["A", "a"])]
    df["level"] = df["agglvl_code"].map(levels)
    for col in ["annual_avg_estabs", "annual_avg_emplvl", "total_annual_wages"]:
        df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="raise").astype(float)
    df["year"] = df["year"].astype(int)
    suppressed = df["disclosure_code"].str.strip().str.upper() == "N"
    df["suppressed"] = suppressed
    df.loc[suppressed, ["annual_avg_emplvl", "total_annual_wages"]] = np.nan
    # Establishment counts are normally published for suppressed cells. A zero
    # in a suppressed row is the BLS placeholder, not an observation.
    df.loc[suppressed & (df["annual_avg_estabs"] <= 0), "annual_avg_estabs"] = np.nan
    if (df.loc[~suppressed, ["annual_avg_emplvl", "total_annual_wages", "annual_avg_estabs"]] < 0).any().any():
        raise ValueError(f"{path}: negative values in disclosed rows")
    out = df.rename(columns={
        "area_fips": "area", "industry_code": "industry", "annual_avg_estabs": "estabs",
        "annual_avg_emplvl": "emp", "total_annual_wages": "wages",
    })[["area", "industry", "level", "year", "emp", "wages", "estabs", "suppressed"]]
    dupes = out.duplicated(["area", "industry", "level", "year"])
    if dupes.any():
        raise ValueError(f"{path}: duplicate area/industry/year rows {out[dupes].head().to_dict('records')}")
    return out


def load_raw(raw_dir: Path, years: list[int], areas: dict[str, str]) -> tuple[pd.DataFrame, set[tuple[str, int]]]:
    """Load every available area file. ``areas`` maps area code -> kind.
    Returns the combined frame and the set of (area, year) files loaded."""
    frames, loaded = [], set()
    for year in years:
        for area, kind in areas.items():
            path = raw_path(raw_dir, year, area)
            if path.exists():
                frames.append(read_area_file(path, kind))
                loaded.add((area, year))
    if not frames:
        return pd.DataFrame(columns=["area", "industry", "level", "year", "emp", "wages", "estabs", "suppressed"]), loaded
    return pd.concat(frames, ignore_index=True), loaded


def delineation_consistency(data: pd.DataFrame, metro: Metro, years: list[int],
                            loaded: set[tuple[str, int]]) -> dict[int, dict]:
    """Compare BLS's published metro total with the sum of our county list.

    A match means BLS used the same county set that year, so its published
    metro cells can stand in for suppressed county sums."""
    out = {}
    for year in years:
        counties_ok = all((c, year) in loaded for c in metro.county_fips)
        tot = data[(data["level"] == "total") & (data["industry"] == "10") & (data["year"] == year)]
        county_vals = tot[tot["area"].isin(metro.county_fips)].set_index("area")["emp"]
        county_sum = county_vals.sum() if counties_ok and county_vals.notna().all() and len(county_vals) == len(metro.county_fips) else None
        pub = tot[tot["area"] == metro.qcew_area]["emp"]
        published = float(pub.iloc[0]) if len(pub) and pd.notna(pub.iloc[0]) else None
        rel = None
        if county_sum is not None and published:
            rel = abs(published - county_sum) / county_sum
        out[year] = {
            "county_sum": county_sum, "published": published, "relative_difference": rel,
            "consistent": bool(rel is not None and rel <= CONSISTENCY_TOLERANCE),
        }
    return out


def aggregate_metro(data: pd.DataFrame, metro: Metro, years: list[int],
                    loaded: set[tuple[str, int]], consistency: dict[int, dict]) -> pd.DataFrame:
    """Metro rows for every industry present in the national file."""
    nat = data[data["area"] == "US000"][["industry", "level", "year"]].drop_duplicates()
    rows = []
    for year in years:
        have_all_counties = all((c, year) in loaded for c in metro.county_fips)
        sub = data[(data["year"] == year) & (data["area"].isin(metro.county_fips))]
        pub = data[(data["year"] == year) & (data["area"] == metro.qcew_area)].set_index(["industry", "level"])
        by_ind = {k: g for k, g in sub.groupby(["industry", "level"])}
        for ind, level in nat[nat["year"] == year][["industry", "level"]].itertuples(index=False):
            g = by_ind.get((ind, level))
            rec = {"area": metro.id, "industry": ind, "level": level, "year": year,
                   "emp": np.nan, "wages": np.nan, "estabs": np.nan, "source": "missing"}
            county_complete = have_all_counties and (g is None or not g["emp"].isna().any())
            if county_complete:
                if g is None:
                    rec.update(emp=0.0, wages=0.0, estabs=0.0)
                else:
                    rec.update(emp=g["emp"].sum(), wages=g["wages"].sum(),
                               estabs=g["estabs"].sum() if g["estabs"].notna().all() else np.nan)
                rec["source"] = "county_sum"
            elif consistency.get(year, {}).get("consistent") and (ind, level) in pub.index \
                    and pd.notna(pub.loc[(ind, level), "emp"]):
                p = pub.loc[(ind, level)]
                rec.update(emp=p["emp"], wages=p["wages"], estabs=p["estabs"], source="msa_published")
            else:
                rec["source"] = "suppressed" if have_all_counties else "missing"
                if g is not None and have_all_counties and g["estabs"].notna().all():
                    rec["estabs"] = g["estabs"].sum()
            rows.append(rec)
    return pd.DataFrame(rows)


def national(data: pd.DataFrame) -> pd.DataFrame:
    us = data[data["area"] == "US000"].copy()
    us["area"] = "us"
    us["source"] = np.where(us["emp"].isna(), "suppressed", "published")
    return us.drop(columns=["suppressed"])


def weekly_wage(wages: pd.Series, emp: pd.Series) -> pd.Series:
    """Average weekly wage = total annual wages / annual average employment / 52."""
    with np.errstate(divide="ignore", invalid="ignore"):
        w = wages / emp / 52
    return w.where(emp > 0)
