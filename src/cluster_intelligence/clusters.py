"""Formal cluster aggregation from a verified NAICS-to-cluster crosswalk.

The U.S. Cluster Mapping Project (Delgado, Porter and Stern 2016) assigns
6-digit NAICS industries to traded and local clusters. No crosswalk is
bundled with this repository: it must be downloaded from clustermapping.us,
its terms checked, and saved as data/external/cluster_crosswalk.csv with the
columns below. Without it, no cluster results are produced.

A cluster value is reported only when every member industry with activity
in the region is disclosed. Partial sums would understate employment."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

REQUIRED = ["naics6", "cluster_code", "cluster_name", "cluster_type", "naics_edition"]


def load_crosswalk(path: Path) -> pd.DataFrame:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path}: empty crosswalk")
    missing = [c for c in REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f"{path}: crosswalk missing columns {missing}")
    df = pd.DataFrame(rows)
    df["naics6"] = df["naics6"].str.strip()
    if not df["naics6"].str.fullmatch(r"\d{6}").all():
        raise ValueError(f"{path}: naics6 must be 6-digit codes")
    if df["naics6"].duplicated().any():
        raise ValueError(f"{path}: an industry is assigned to more than one cluster")
    return df


def aggregate(industry_rows: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Sum 6-digit rows (columns area, industry, year, emp) into clusters.

    Industries with no row in an area are zero; a row with missing emp makes
    the whole cluster-area-year missing."""
    merged = industry_rows.merge(crosswalk[["naics6", "cluster_code", "cluster_name", "cluster_type"]],
                                 left_on="industry", right_on="naics6", how="inner")
    grouped = merged.groupby(["area", "year", "cluster_code", "cluster_name", "cluster_type"])
    out = grouped["emp"].agg(emp=lambda s: s.sum() if s.notna().all() else float("nan"),
                             members_reported="count", members_present="size").reset_index()
    return out
