"""American Community Survey 1-year estimates with margins of error.

ACS describes *residents* of an area, wherever they work. QCEW and CBP count
*jobs at establishments* located in the area. The two are never combined into
a single ratio here.

MOE formulas follow the Census Bureau's "Understanding and Using ACS Data"
handbook (2020), chapter 8: sums use the root-sum-of-squares of component
MOEs, and proportions use the ratio formula with the proportion adjustment."""
from __future__ import annotations

import math

Z90 = 1.645

VARIABLES = {
    "pop25": "B15003_001",          # population 25 years and over
    "bachelors": "B15003_022",
    "masters": "B15003_023",
    "professional": "B15003_024",
    "doctorate": "B15003_025",
    "median_hh_income": "B19013_001",
    "workers16": "B08301_001",      # workers 16 years and over
    "work_from_home": "B08301_021",
}


def api_url(year: int, geo: str) -> str:
    fields = ",".join(["NAME"] + [f"{v}{s}" for v in VARIABLES.values() for s in ("E", "M")])
    return f"https://api.census.gov/data/{year}/acs/acs1?get={fields}&for={geo}"


def moe_sum(moes: list[float]) -> float:
    return math.sqrt(sum(m * m for m in moes))


def moe_proportion(num: float, den: float, moe_num: float, moe_den: float) -> float:
    """MOE of p = num/den when num is a subset of den."""
    p = num / den
    radicand = moe_num ** 2 - p ** 2 * moe_den ** 2
    if radicand < 0:  # Census guidance: fall back to the ratio formula
        radicand = moe_num ** 2 + p ** 2 * moe_den ** 2
    return math.sqrt(radicand) / den


def significantly_different(est1: float, moe1: float, est2: float, moe2: float) -> bool:
    """Two-sided test at the 90% level used by the Census Bureau."""
    return abs(est1 - est2) > math.sqrt(moe1 ** 2 + moe2 ** 2)


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    # The API uses large negative sentinels (e.g. -666666666) for unavailable values.
    return None if x < -1e5 else x


def parse_response(rows: list[list[str]]) -> list[dict]:
    """Turn a Census API JSON table into tidy indicator records."""
    header, *data = rows
    idx = {h: i for i, h in enumerate(header)}
    for code in VARIABLES.values():
        for s in ("E", "M"):
            if code + s not in idx:
                raise ValueError(f"ACS response is missing {code}{s}")
    out = []
    for r in data:
        get = lambda key, s: _num(r[idx[VARIABLES[key] + s]])
        geo_id = r[-1]
        rec = {"geo_code": geo_id, "name": r[idx["NAME"]], "indicators": {}}
        parts = ["bachelors", "masters", "professional", "doctorate"]
        est = [get(k, "E") for k in parts]
        moe = [get(k, "M") for k in parts]
        pop, pop_m = get("pop25", "E"), get("pop25", "M")
        if None not in est + moe and pop and pop_m is not None:
            num = sum(est)
            rec["indicators"]["bachelors_or_higher_pct"] = {
                "estimate": 100 * num / pop,
                "moe": 100 * moe_proportion(num, pop, moe_sum(moe), pop_m),
                "universe": "Residents aged 25 and over",
            }
        inc, inc_m = get("median_hh_income", "E"), get("median_hh_income", "M")
        if inc is not None and inc_m is not None:
            rec["indicators"]["median_household_income"] = {
                "estimate": inc, "moe": inc_m,
                "universe": "Households; nominal dollars of the survey year",
            }
        w, w_m = get("workers16", "E"), get("workers16", "M")
        h, h_m = get("work_from_home", "E"), get("work_from_home", "M")
        if None not in (w, w_m, h, h_m) and w:
            rec["indicators"]["work_from_home_pct"] = {
                "estimate": 100 * h / w,
                "moe": 100 * moe_proportion(h, w, h_m, w_m),
                "universe": "Workers aged 16 and over living in the area",
            }
        out.append(rec)
    return out
