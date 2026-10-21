"""LEHD Quarterly Workforce Indicators: labor-market dynamics.

QWI adds flows (hires, separations, firm job gains and losses) that QCEW does
not measure. Counts are summed from our county list (Chicago spans Illinois
and Indiana, so state-specific metro files would split it). A county-quarter
whose status flag is not 1 (fully published) makes the metro value missing.

Rates use the QWI convention of dividing by average employment over the
quarter, here approximated with beginning-of-quarter employment (Emp)."""
from __future__ import annotations

MEASURES = ["Emp", "EmpS", "HirA", "Sep", "FrmJbGn", "FrmJbLs", "EarnS"]
OK_FLAG = "1"


def api_url(year: int, quarter: int, state_fips: str, county_codes: list[str]) -> str:
    fields = ",".join(MEASURES + ["s" + m for m in MEASURES])
    return (f"https://api.census.gov/data/timeseries/qwi/sa?get={fields}"
            f"&for=county:{','.join(county_codes)}&in=state:{state_fips}"
            f"&year={year}&quarter={quarter}&ownercode=A05")


def parse_response(rows: list[list[str]]) -> list[dict]:
    header, *data = rows
    idx = {h: i for i, h in enumerate(header)}
    for m in MEASURES + ["year", "quarter", "state", "county"]:
        if m not in idx:
            raise ValueError(f"QWI response missing {m}")
    out = []
    for r in data:
        rec = {"county": r[idx["state"]] + r[idx["county"]], "year": int(r[idx["year"]]),
               "quarter": int(r[idx["quarter"]])}
        for m in MEASURES:
            flag = r[idx["s" + m]] if "s" + m in idx else OK_FLAG
            try:
                val = float(r[idx[m]])
            except (TypeError, ValueError):
                val = None
            rec[m] = val if flag == OK_FLAG else None
        out.append(rec)
    return out


def annual_metro(records: list[dict], counties: list[str], year: int) -> dict | None:
    """Annual rates for one metro, or None if any county-quarter is incomplete."""
    recs = [r for r in records if r["county"] in counties and r["year"] == year]
    if len({(r["county"], r["quarter"]) for r in recs}) != 4 * len(counties):
        return None
    if any(r[m] is None for r in recs for m in MEASURES):
        return None
    emp = sum(r["Emp"] for r in recs)
    emps = sum(r["EmpS"] for r in recs)
    if emp <= 0 or emps <= 0:
        return None
    return {
        "year": year,
        "avg_employment": emp / 4,
        "hire_rate": sum(r["HirA"] for r in recs) / emp,
        "separation_rate": sum(r["Sep"] for r in recs) / emp,
        "job_creation_rate": sum(r["FrmJbGn"] for r in recs) / emp,
        "job_destruction_rate": sum(r["FrmJbLs"] for r in recs) / emp,
        # Employment-weighted average monthly earnings of stable (full-quarter) jobs.
        "avg_monthly_earnings_stable": sum(r["EarnS"] * r["EmpS"] for r in recs) / emps,
    }
