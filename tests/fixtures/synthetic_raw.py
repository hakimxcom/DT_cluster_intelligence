"""SYNTHETIC raw files for tests only.

Every number produced here is invented to exercise parsing, suppression,
aggregation and validation paths. None of it describes a real economy, and it
must never be exported to the website. The generated manifest is tagged with
``synthetic_fixture`` by the tests that use it."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from cluster_intelligence.geography import load_config, load_metros

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]
SECTORS = {"23": 40, "31-33": 120, "44-45": 90, "54": 70, "62": 110, "72": 80, "99": 2}
# subsector -> (sector, share of the sector)
SUBSECTORS = {"336": ("31-33", 0.4), "332": ("31-33", 0.2), "441": ("44-45", 0.2),
              "452": ("44-45", 0.3), "622": ("62", 0.35), "722": ("72", 0.8)}
REST_OF_US = 400.0  # multiplier for the part of the U.S. outside the 25 counties

HEADER = ["area_fips", "own_code", "industry_code", "agglvl_code", "size_code", "year", "qtr",
          "disclosure_code", "annual_avg_estabs", "annual_avg_emplvl", "total_annual_wages",
          "taxable_annual_wages", "annual_contributions", "annual_avg_wkly_wage", "avg_annual_pay"]
LEVELS = {"national": ("11", "14", "15"), "state": ("51", "54", "55"),
          "msa": ("41", "44", "45"), "county": ("71", "74", "75")}

# Cells deliberately suppressed (disclosure code N, zeros in value columns).
SUPPRESSED = {("18111", "336"), ("39007", "332"), ("26087", "622")}
# Cells with no establishments (no row at all).
ABSENT = {("26163", "452", 2019), ("26087", "452", 2019), ("26093", "452", 2019), ("26099", "452", 2019),
          ("26125", "452", 2019), ("26147", "452", 2019)}


def _county_value(fips: str, ind: str, year: int) -> float:
    seed = int(fips) % 97 + 3
    if ind in SECTORS:
        base = SECTORS[ind] * seed * 10
    else:
        sector, s = SUBSECTORS[ind]
        base = SECTORS[sector] * seed * 10 * s
    trend = 1 + ((int(fips) + len(ind) + sum(map(ord, ind))) % 7 - 3) * 0.01
    return round(base * trend ** (year - YEARS[0]))


def _row(area, level_code, ind, year, emp, suppressed=False):
    estabs = max(1, round(emp / 12))
    wages = round(emp * 52 * (900 + (sum(map(ord, ind)) % 400)))
    if suppressed:
        return [area, "5", ind, level_code, "0", year, "A", "N", estabs, 0, 0, 0, 0, 0, 0]
    return [area, "5", ind, level_code, "0", year, "A", "", estabs, emp, wages, 0, 0,
            round(wages / emp / 52) if emp else 0, round(wages / emp) if emp else 0]


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def _industries(year):
    subs = [s for s in SUBSECTORS if not (s == "452" and year >= 2022)]
    if year >= 2022:
        subs.append("455")  # NAICS 2022 retail subsector replacing 452
    return list(SECTORS), subs


def _value(fips, ind, year):
    if ind == "455":
        return _county_value(fips, "452", year)
    return _county_value(fips, ind, year)


def build(raw: Path) -> None:
    metros, cfg = load_metros(), load_config()
    counties = [c for m in metros for c in m.county_fips]
    for year in YEARS:
        sectors, subs = _industries(year)
        values = {}
        for c in counties:
            rows = []
            for ind, lvl in [(s, 1) for s in sectors] + [(s, 2) for s in subs]:
                if (c, ind, year) in ABSENT:
                    continue
                v = _value(c, ind, year)
                values[(c, ind)] = v
                rows.append(_row(c, LEVELS["county"][lvl], ind, year, v, (c, ind) in SUPPRESSED))
            total = sum(values[(c, s)] for s in sectors)
            values[(c, "10")] = total
            rows.insert(0, _row(c, "71", "10", year, total))
            rows.append([c, "0", "10", "70", "0", year, "A", "", 1, total * 2, 1, 0, 0, 0, 0])  # all-ownership row, ignored
            _write(raw / "qcew" / str(year) / f"{c}.csv", rows)
        for m in metros:
            # BLS's published metro: through 2023 Cleveland is C1746 (Cleveland-Elyria),
            # which excludes Ashtabula; from 2024 it is C1741 with Ashtabula.
            members = [c for c in m.county_fips if not (m.id == "cleveland" and c == "39007" and year <= 2023)]
            area = m.qcew_area_for(year)
            rows = []
            for ind in ["10"] + sectors + subs:
                v = sum(values.get((c, ind), 0) for c in members)
                if v == 0:
                    continue
                lvl = "41" if ind == "10" else ("44" if ind in sectors else "45")
                rows.append(_row(area, lvl, ind, year, v))
            _write(raw / "qcew" / str(year) / f"{area}.csv", rows)
        rows = []
        for ind in ["10"] + sectors + subs:
            v = sum(values.get((c, ind), 0) for c in counties) + REST_OF_US * _value("01001", ind if ind != "10" else "23", year)
            lvl = "11" if ind == "10" else ("14" if ind in sectors else "15")
            rows.append(_row("US000", lvl, ind, year, round(v)))
        # Make the national total equal the sum of national sectors.
        rows[0] = _row("US000", "11", "10", year, sum(r[9] for r in rows[1:1 + len(sectors)]))
        _write(raw / "qcew" / str(year) / "US000.csv", rows)
        for s in cfg["states"]:
            st = [c for c in counties if c[:2] == s["fips"]]
            v = round(sum(values[(c, "10")] for c in st) * 1.6)
            _write(raw / "qcew" / str(year) / f"{s['qcew_area']}.csv", [_row(s["qcew_area"], "51", "10", year, v)])

    # CBP (latest year only), one file per state.
    by_state = {}
    for c in counties:
        by_state.setdefault(c[:2], []).append(c)
    for st, cs in by_state.items():
        rows = [["NAICS2017", "ESTAB", "EMP", "EMP_N", "PAYANN", "PAYANN_N", "EMPSZES", "EMPSZES_LABEL", "state", "county"]]
        for c in cs:
            for code in ["00", "31-33", "62"]:
                rows.append([code, "1000", "12000", "G", "600000", "G", "001", "All establishments", st, c[2:]])
                rows.append([code, "600", "0", "", "0", "", "210", "Establishments with less than 5 employees", st, c[2:]])
                rows.append([code, "300", "0", "", "0", "", "241", "Establishments with 20 to 49 employees", st, c[2:]])
                rows.append([code, "100", "0", "", "0", "", "260", "Establishments with 1,000 employees or more", st, c[2:]])
        (raw / "cbp").mkdir(parents=True, exist_ok=True)
        (raw / "cbp" / f"2022_{st}.json").write_text(json.dumps(rows))

    # BEA zips: GDP by county, state and nation. Like the real CAGDP files,
    # they carry no metropolitan rows.
    (raw / "bea").mkdir(parents=True, exist_ok=True)
    geos = {c: 1000.0 + int(c) % 50 for c in counties}
    for s in cfg["states"]:
        geos[s["fips"] + "000"] = 5000.0
    geos["00000"] = 100000.0
    for table, growth in (("CAGDP2", 0.04), ("CAGDP9", 0.02)):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["GeoFIPS", "GeoName", "Region", "TableName", "LineCode", "IndustryClassification", "Description", "Unit"] + [str(y) for y in YEARS])
        for g, v in geos.items():
            w.writerow([f' "{g}"', "Area " + g, "", table, "1", "...", "All industry total", "Thousands of dollars"]
                       + [f"{v * (1 + growth) ** i:.0f}" for i in range(len(YEARS))])
        with zipfile.ZipFile(raw / "bea" / f"{table}.zip", "w") as z:
            z.writestr(f"{table}__ALL_AREAS_2019_2023.csv", buf.getvalue())

    # ACS metro and state responses.
    from cluster_intelligence.acs import VARIABLES
    head = ["NAME"] + [f"{v}{s}" for v in VARIABLES.values() for s in ("E", "M")]
    def acs_rows(geo_col, codes):
        rows = [head + [geo_col]]
        for i, code in enumerate(codes):
            vals = {"B15003_001": (1000000, 2000), "B15003_022": (200000 + i * 20000, 3000), "B15003_023": (80000, 2000),
                    "B15003_024": (20000, 800), "B15003_025": (15000, 700), "B19013_001": (70000 + i * 1000, 800),
                    "B08301_001": (900000, 3000), "B08301_021": (110000, 2500)}
            rows.append([f"Area {code}"] + [str(vals[v][k]) for v in VARIABLES.values() for k in (0, 1)] + [code])
        return rows
    (raw / "acs").mkdir(parents=True, exist_ok=True)
    (raw / "acs" / "2023_metro.json").write_text(json.dumps(acs_rows("metropolitan statistical area/micropolitan statistical area", [m.cbsa_code for m in metros])))
    (raw / "acs" / "2023_state.json").write_text(json.dumps(acs_rows("state", [s["fips"] for s in cfg["states"]])))

    # QWI for 2023.
    from cluster_intelligence.qwi import MEASURES
    (raw / "qwi").mkdir(parents=True, exist_ok=True)
    for q in range(1, 5):
        for st, cs in by_state.items():
            rows = [MEASURES + ["s" + m for m in MEASURES] + ["year", "quarter", "ownercode", "state", "county"]]
            for c in cs:
                rows.append(["10000", "9000", "1200", "1100", "500", "450", "5000"] + ["1"] * len(MEASURES)
                            + ["2023", str(q), "A05", st, c[2:]])
            (raw / "qwi" / f"2023_q{q}_{st}.json").write_text(json.dumps(rows))

    # CPI flat file.
    (raw / "cpi").mkdir(parents=True, exist_ok=True)
    lines = ["series_id        \tyear\tperiod\tvalue\tfootnote_codes"]
    for i, y in enumerate(YEARS):
        lines.append(f"CUUR0000SA0      \t{y}\tM13\t{255 + i * 10:.3f}\t")
        lines.append(f"CUUR0000SA0      \t{y}\tM01\t{254 + i * 10:.3f}\t")
    (raw / "cpi" / "cu.data.1.AllItems").write_text("\n".join(lines) + "\n")
