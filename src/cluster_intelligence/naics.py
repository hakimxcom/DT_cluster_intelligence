"""NAICS sector titles, hierarchy and revision comparability.

QCEW publishes each year under the NAICS edition in force at the time and does
not reconvert earlier years: NAICS 2012 for 2012-2016, NAICS 2017 for
2017-2021 and NAICS 2022 from 2022. Sector (2-digit) definitions are stable
across these editions. The 2022 edition restructured Retail Trade (44-45) and
Information (51) at the 3-digit level, so subsectors in those sectors are not
compared across the 2021/2022 boundary."""
from __future__ import annotations

SECTOR_TITLES = {
    "11": "Agriculture, forestry, fishing and hunting",
    "21": "Mining, quarrying, and oil and gas extraction",
    "22": "Utilities",
    "23": "Construction",
    "31-33": "Manufacturing",
    "42": "Wholesale trade",
    "44-45": "Retail trade",
    "48-49": "Transportation and warehousing",
    "51": "Information",
    "52": "Finance and insurance",
    "53": "Real estate and rental and leasing",
    "54": "Professional, scientific, and technical services",
    "55": "Management of companies and enterprises",
    "56": "Administrative and support and waste management and remediation services",
    "61": "Educational services",
    "62": "Health care and social assistance",
    "71": "Arts, entertainment, and recreation",
    "72": "Accommodation and food services",
    "81": "Other services (except public administration)",
    "92": "Public administration",
}

NAICS_EDITIONS = [(2012, 2016, "NAICS 2012"), (2017, 2021, "NAICS 2017"), (2022, 9999, "NAICS 2022")]
# Sectors whose 3-digit subsectors were redefined in a given edition.
SUBSECTOR_BREAKS = {"NAICS 2022": {"44-45", "51"}}


def edition(year: int) -> str:
    for start, end, name in NAICS_EDITIONS:
        if start <= year <= end:
            return name
    raise ValueError(f"No NAICS edition configured for {year}")


def sector_of(code: str) -> str:
    """Parent sector for a sector or subsector code (e.g. '336' -> '31-33')."""
    if code in SECTOR_TITLES:
        return code
    two = code[:2]
    for sector in SECTOR_TITLES:
        if "-" in sector:
            lo, hi = sector.split("-")
            if lo <= two <= hi:
                return sector
        elif sector == two:
            return sector
    raise ValueError(f"Unknown NAICS code {code}")


def comparable(code: str, level: str, start: int, end: int) -> bool:
    """Whether an industry's definition is constant between two QCEW years."""
    if level in ("total", "sector"):
        return True
    for _, _, name in NAICS_EDITIONS:
        first = next(s for s, _, n in NAICS_EDITIONS if n == name)
        if start < first <= end and sector_of(code) in SUBSECTOR_BREAKS.get(name, set()):
            return False
    return True


def load_titles(path) -> dict[str, str]:
    """Industry titles from the BLS QCEW industry_titles.csv, if downloaded."""
    import csv
    titles = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row["industry_code"].strip()
            title = row["industry_title"].strip()
            # BLS prefixes titles with "NAICS 336 " etc.; keep only the name.
            parts = title.split(" ", 2)
            if len(parts) == 3 and parts[0] == "NAICS" and parts[1] == code:
                title = parts[2]
            titles[code] = title
    return titles
