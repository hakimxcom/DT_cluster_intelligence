"""County Business Patterns: establishments by size class and payroll.

CBP establishment counts are published for every cell. Since 2017 CBP protects
employment and payroll with noise infusion instead of withholding cells, and the
API's EMP_N / PAYANN_N variables are noise ranges. In the live 2017, 2022 and
2023 responses for our states every one of them is "0" and no cell is withheld.
A value flagged "D" (withheld) or "S" (does not meet publication standards), as
in the published CBP flag scheme, would still be treated as missing, never zero.
EMP is employment in the pay period including March 12, so EMP = 0 with
positive payroll is a reported value, not a suppression.
Metro values are summed from our county list so the geography is fixed."""
from __future__ import annotations

# Employment-size classes (EMPSZES) grouped into four bands. The API's
# EMPSZES_LABEL is checked against these expectations when parsing.
SIZE_BANDS = {
    # 210 is "less than 5 employees" in the API (212 is the separate "1 to 4" class).
    "1-19": {"210": "less than 5", "220": "5 to 9", "230": "10 to 19"},
    "20-99": {"241": "20 to 49", "242": "50 to 99"},
    "100-499": {"251": "100 to 249", "252": "250 to 499"},
    # 260 is "1,000 or more"; from 2022 the API also returns its sub-classes
    # 262, 263, 271 and 273, which are not added again.
    "500+": {"254": "500 to 999", "260": "1,000"},
}
ALL_SIZES = "001"
WITHHELD_FLAGS = {"D", "S"}


# Checked against the live API: 2017 through 2023 expose only NAICS2017, and
# 2023 still uses 2017 codes (452, 454 and 511 exist; 455, 459 and 513 do not).
NAICS_VARS = ("NAICS2017", "NAICS2022")


def naics_var(year: int) -> str:
    """NAICS variable to request. NAICS2017 is verified for 2017-2023. Later
    years are unverified; if the API renames the variable the request fails
    and the fetch log records it rather than the parser guessing."""
    return "NAICS2017" if year <= 2023 else "NAICS2022"


def api_url(year: int, state_fips: str, county_codes: list[str]) -> str:
    nv = naics_var(year)
    fields = f"{nv},ESTAB,EMP,EMP_N,PAYANN,PAYANN_N,EMPSZES,EMPSZES_LABEL"
    return (f"https://api.census.gov/data/{year}/cbp?get={fields}"
            f"&for=county:{','.join(county_codes)}&in=state:{state_fips}")


def is_sector(code: str) -> bool:
    return code == "00" or (len(code) == 2 and code.isdigit()) or code in {"31-33", "44-45", "48-49"}


def _int(v: str | None) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_response(rows: list[list[str]], year: int) -> list[dict]:
    header, *data = rows
    idx = {h: i for i, h in enumerate(header)}
    found = [v for v in NAICS_VARS if v in idx]
    if len(found) != 1:
        raise ValueError(f"CBP {year} response has NAICS columns {found}, expected exactly one of {NAICS_VARS}")
    nv = found[0]
    for col in (nv, "ESTAB", "EMP", "PAYANN", "EMPSZES", "EMPSZES_LABEL", "state", "county"):
        if col not in idx:
            raise ValueError(f"CBP {year} response missing column {col}")
    expected = {code: label for band in SIZE_BANDS.values() for code, label in band.items()}
    out = []
    for r in data:
        code = r[idx[nv]]
        if not is_sector(code):
            continue
        size = r[idx["EMPSZES"]]
        if size in expected and expected[size].lower() not in r[idx["EMPSZES_LABEL"]].lower():
            raise ValueError(f"CBP {year}: size code {size} labelled {r[idx['EMPSZES_LABEL']]!r}")
        emp_flag = r[idx["EMP_N"]] if "EMP_N" in idx else ""
        pay_flag = r[idx["PAYANN_N"]] if "PAYANN_N" in idx else ""
        out.append({
            "county": r[idx["state"]] + r[idx["county"]], "naics": "10" if code == "00" else code,
            "size": size, "estab": _int(r[idx["ESTAB"]]),
            "emp": None if emp_flag in WITHHELD_FLAGS else _int(r[idx["EMP"]]),
            "payann": None if pay_flag in WITHHELD_FLAGS else _int(r[idx["PAYANN"]]),
            "year": year,
        })
    return out


def aggregate(records: list[dict], counties: list[str]) -> dict:
    """Sum county records for one metro and year into sector summaries."""
    by = {}
    present = {r["county"] for r in records}
    complete_geo = set(counties) <= present
    for r in records:
        if r["county"] not in counties:
            continue
        by.setdefault(r["naics"], []).append(r)
    out = {}
    for naics, recs in by.items():
        total = [r for r in recs if r["size"] == ALL_SIZES]
        estab = sum(r["estab"] or 0 for r in total) if complete_geo else None
        emp_vals = [r["emp"] for r in total]
        pay_vals = [r["payann"] for r in total]
        # A sector absent from a county means no establishments there, so the
        # sum is complete as long as every present value is disclosed.
        emp = sum(emp_vals) if complete_geo and None not in emp_vals else None
        pay = sum(pay_vals) if complete_geo and None not in pay_vals else None
        bands = {}
        for band, codes in SIZE_BANDS.items():
            bands[band] = sum(r["estab"] or 0 for r in recs if r["size"] in codes) if complete_geo else None
        out[naics] = {"establishments": estab, "employment": emp, "payroll_thousands": pay, "size_bands": bands}
    return out
