"""BEA GDP by county and metropolitan area.

CAGDP2 is current-dollar GDP; CAGDP9 is real GDP in chained 2017 dollars.
Both report thousands of dollars. Chained-dollar values are not additive, so
real GDP is taken from BEA's own metro row, and that row is only used when the
current-dollar county sum for our county list matches BEA's metro row (which
shows BEA used the same delineation)."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

TABLE_URL = "https://apps.bea.gov/regional/zip/{table}.zip"
CONSISTENCY_TOLERANCE = 0.001


def read_table(zip_path: Path) -> pd.DataFrame:
    """Read the ALL_AREAS CSV inside a BEA regional zip into long format.

    Returns columns geo, name, line, description, unit, year, value. BEA's
    non-numeric markers such as (D) suppressed and (NA) become NaN."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if "ALL_AREAS" in n and n.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{zip_path}: expected one ALL_AREAS csv, found {names}")
        raw = z.read(names[0]).decode("latin-1")
    df = pd.read_csv(io.StringIO(raw), dtype=str)
    df = df[df["GeoFIPS"].notna() & df["LineCode"].notna()]
    year_cols = [c for c in df.columns if c.strip().isdigit()]
    if not year_cols:
        raise ValueError(f"{zip_path}: no year columns")
    df["geo"] = df["GeoFIPS"].str.replace('"', "").str.strip()
    long = df.melt(id_vars=["geo", "GeoName", "LineCode", "Description", "Unit"],
                   value_vars=year_cols, var_name="year", value_name="raw")
    long["value"] = pd.to_numeric(long["raw"].str.strip(), errors="coerce")
    long["year"] = long["year"].str.strip().astype(int)
    long["line"] = pd.to_numeric(long["LineCode"], errors="coerce")
    return long.rename(columns={"GeoName": "name", "Description": "description", "Unit": "unit"})[
        ["geo", "name", "line", "description", "unit", "year", "value"]]


def all_industry(df: pd.DataFrame) -> pd.DataFrame:
    total = df[df["line"] == 1]
    if total.empty:
        raise ValueError("BEA table has no line 1 (all-industry total)")
    return total


def metro_series(nominal: pd.DataFrame, real: pd.DataFrame, cbsa: str, counties: list[str]) -> list[dict]:
    """Yearly GDP for one metro with a delineation check per year."""
    nom = all_industry(nominal)
    rl = all_industry(real)
    out = []
    for year in sorted(nom["year"].unique()):
        n_year = nom[nom["year"] == year]
        county_vals = n_year[n_year["geo"].isin(counties)]["value"]
        county_sum = county_vals.sum() if len(county_vals) == len(counties) and county_vals.notna().all() else None
        metro_nom = n_year[n_year["geo"] == cbsa]["value"]
        metro_nom = float(metro_nom.iloc[0]) if len(metro_nom) and pd.notna(metro_nom.iloc[0]) else None
        consistent = bool(county_sum is not None and metro_nom is not None and \
            abs(metro_nom - county_sum) / county_sum <= CONSISTENCY_TOLERANCE)
        metro_real = rl[(rl["year"] == year) & (rl["geo"] == cbsa)]["value"]
        metro_real = float(metro_real.iloc[0]) if len(metro_real) and pd.notna(metro_real.iloc[0]) else None
        out.append({
            "year": int(year),
            "gdp_nominal": county_sum,  # additive, so always from our county list
            "gdp_real": metro_real if consistent else None,
            "delineation_consistent": consistent,
        })
    return out


def area_series(nominal: pd.DataFrame, real: pd.DataFrame, geo: str) -> list[dict]:
    nom, rl = all_industry(nominal), all_industry(real)
    out = []
    for year in sorted(nom["year"].unique()):
        n = nom[(nom["year"] == year) & (nom["geo"] == geo)]["value"]
        r = rl[(rl["year"] == year) & (rl["geo"] == geo)]["value"]
        out.append({"year": int(year),
                    "gdp_nominal": float(n.iloc[0]) if len(n) and pd.notna(n.iloc[0]) else None,
                    "gdp_real": float(r.iloc[0]) if len(r) and pd.notna(r.iloc[0]) else None})
    return out
