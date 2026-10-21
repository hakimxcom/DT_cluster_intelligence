"""Data-quality checks recorded in the build manifest.

A failed check does not stop the build; it sets the manifest status to
``failed_validation`` so the website can say so instead of hiding it."""
from __future__ import annotations

import math

import pandas as pd

from .shift_share import RECONCILIATION_TOLERANCE


class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})

    @property
    def ok(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def as_list(self) -> list[dict]:
        return list(self.checks)


def validate_annual(a: pd.DataFrame, report: Report) -> None:
    dup = a.duplicated(["area", "industry", "level", "year"])
    report.add("no_duplicate_area_industry_year", not dup.any(), f"{int(dup.sum())} duplicate rows")

    sup = a[a["source"].isin(["suppressed", "missing"])]
    leaked = sup["emp"].notna().sum()
    report.add("suppressed_not_zero", leaked == 0,
               f"{len(sup)} suppressed/missing metro cells; {int(leaked)} carry an employment value")

    totals = a[a["level"] == "total"]
    report.add("totals_present", totals["emp"].notna().all(),
               f"{int(totals['emp'].isna().sum())} area-years without total private employment")

    # Disclosed sectors cannot exceed the total; when every sector is disclosed
    # the sum should be close to the total (the gap is NAICS 99, unclassified).
    over, gap_max = 0, 0.0
    for (area, year), g in a[a["level"] == "sector"].groupby(["area", "year"]):
        total = totals[(totals["area"] == area) & (totals["year"] == year)]["emp"]
        if total.empty or pd.isna(total.iloc[0]):
            continue
        s = g["emp"].sum(min_count=1)
        if s > total.iloc[0] * 1.0005:
            over += 1
        if g["emp"].notna().all():
            gap_max = max(gap_max, (total.iloc[0] - s) / total.iloc[0])
    report.add("sectors_within_total", over == 0, f"{over} area-years where sectors exceed the total; "
               f"largest unclassified gap {gap_max:.2%}")
    report.add("unclassified_gap_small", gap_max <= 0.02, f"largest gap between total and sector sum {gap_max:.2%} (limit 2%)")

    lq = a["lq"].dropna()
    report.add("lq_plausible", ((lq >= 0) & (lq < 100)).all(), f"LQ range {lq.min():.3f}–{lq.max():.3f}" if len(lq) else "no LQ values")

    us = a[a["area"] == "us"]
    us_lq = us["lq"].dropna()
    report.add("us_lq_equals_one", bool(((us_lq - 1).abs() < 1e-9).all()), "U.S. benchmark LQ must be exactly 1")


def validate_pairs(pairs: dict, report: Report) -> None:
    worst, failed, pct_zero = 0.0, 0, 0
    for rec in pairs.values():
        for d in rec["metros"].values():
            for v in d.values():
                if v["status"] == "ok":
                    r = abs(v["residual"]) / max(1.0, abs(v["e0"]))
                    worst = max(worst, r)
                elif v["status"] == "reconciliation_failed":
                    failed += 1
                if v["pct"] is not None and (v["e0"] is None or v["e0"] <= 0):
                    pct_zero += 1
                if v["status"] != "ok" and v["rc"] is not None:
                    failed += 1
    report.add("shift_share_reconciles", failed == 0 and worst <= RECONCILIATION_TOLERANCE,
               f"{failed} failed decompositions; largest relative residual {worst:.2e} (tolerance {RECONCILIATION_TOLERANCE:g})")
    report.add("no_pct_from_zero_base", pct_zero == 0, f"{pct_zero} growth rates computed from a zero or missing base")
    n = sum(1 for rec in pairs.values() for d in rec["metros"].values() for v in d.values() if v["status"] == "not_comparable")
    report.add("naics_revision_flagged", True, f"{n} industry-period cells withheld because NAICS definitions changed")
