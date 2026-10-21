"""Regression tests on small excerpts of the real source files.

Every file in tests/fixtures/real_excerpts/ was cut, unmodified apart from
dropping rows, from the responses retrieved on 21 October 2026 (see
docs/CLUSTER_DASHBOARD_QA.md section 1). They pin the formats the adapters
were checked against, so a format change upstream fails here first."""
import json
import math
import zipfile
from pathlib import Path

import pytest

from cluster_intelligence import acs, bea, cbp, prices, qcew, qwi

EX = Path(__file__).parent / "fixtures" / "real_excerpts"


def test_qcew_area_slice_suppressed_rows_keep_establishments():
    df = qcew.read_area_file(EX / "qcew_2019_18111.csv", "county")
    df = df.set_index(["industry", "level"])
    # Disclosed total: values as published.
    assert df.loc[("10", "total"), "emp"] == 2539 and df.loc[("10", "total"), "estabs"] == 236
    # disclosure_code "N": BLS writes 0 for employment and wages but publishes
    # the establishment count. Values become missing, establishments are kept.
    sup = df.loc[("11", "sector")]
    assert sup["suppressed"] and math.isnan(sup["emp"]) and math.isnan(sup["wages"]) and sup["estabs"] == 21
    assert not df.loc[("31-33", "sector"), "suppressed"] and df.loc[("31-33", "sector"), "emp"] == 563


def test_cbp_2022_api_format():
    rows = json.loads((EX / "cbp_2022_26.json").read_text())
    assert rows[0][0] == "NAICS2017"  # the 2017-2023 API names the variable NAICS2017
    recs = cbp.parse_response(rows, 2022)
    agg = cbp.aggregate(recs, ["26087"])
    total = agg["10"]
    assert total["establishments"] == 1771 and total["employment"] == 19894
    # "less than 5 employees" is size class 210 and must land in the 1-19 band.
    assert total["size_bands"]["1-19"] == 970 + 377 + 220
    # The published size classes sum to 1,769, two fewer than the all-sizes
    # total, so the bands are never assumed to reconcile exactly.
    assert sum(total["size_bands"].values()) == 1769
    # 262 (1,000-1,499) is a sub-class of 260 and is never added to a band.
    assert cbp.aggregate(recs, ["26099"])["10"]["size_bands"]["500+"] == 0


def test_cbp_rejects_ambiguous_or_missing_naics_column():
    rows = json.loads((EX / "cbp_2022_26.json").read_text())
    renamed = [["NAICS2012"] + rows[0][1:]] + rows[1:]
    with pytest.raises(ValueError):
        cbp.parse_response(renamed, 2022)
    assert cbp.naics_var(2023) == "NAICS2017"


def _bea_zip(tmp_path, table):
    p = tmp_path / f"{table}.zip"
    name = f"{table}__ALL_AREAS_2001_2024.csv"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(name, (EX / name).read_bytes())
    return p


def test_bea_all_areas_format_and_missing_metro_rows(tmp_path):
    nom = bea.read_table(_bea_zip(tmp_path, "CAGDP2"))
    real = bea.read_table(_bea_zip(tmp_path, "CAGDP9"))
    # GeoFIPS is quoted with a leading space in the file; footer notes are dropped.
    assert set(nom["geo"]) == {"00000", "26000", "26087", "26163", "98000"}
    us = bea.area_series(nom, real, "00000")
    assert us[-1] == {"year": 2024, "gdp_nominal": 29298013000.0, "gdp_real": us[-1]["gdp_real"]}
    assert us[-1]["gdp_real"] > 0
    # The county file has no metro row: nominal GDP is the county sum and real
    # GDP is unavailable, with the reason recorded rather than a false
    # "delineation differs".
    s = bea.metro_series(nom, real, "19820", ["26087", "26163"])[-1]
    assert s["gdp_nominal"] is not None and s["gdp_real"] is None
    assert s["real_gdp_status"] == "metro_not_in_file" and s["delineation_consistent"] is None


def test_acs_2024_metro_response():
    out = acs.parse_response(json.loads((EX / "acs_2024_metro.json").read_text()))
    by = {r["geo_code"]: r for r in out}
    assert set(by) == {"16980", "19820"}
    det = by["19820"]["indicators"]
    assert det["median_household_income"] == {"estimate": 76403.0, "moe": 998.0,
                                              "universe": "Households; nominal dollars of the survey year"}
    num = 660741 + 338235 + 69904 + 39125
    assert det["bachelors_or_higher_pct"]["estimate"] == pytest.approx(100 * num / 3114323)


def test_qwi_status_minus_one_is_missing():
    complete = qwi.parse_response(json.loads((EX / "qwi_2024_q1_17.json").read_text()))
    assert all(r["year"] == 2024 and r["quarter"] == 1 for r in complete)
    assert all(r[m] is not None for r in complete for m in qwi.MEASURES)
    edge = qwi.parse_response(json.loads((EX / "qwi_2025_q4_17.json").read_text()))
    # Status -1 comes with a null value (measures that need the next quarter).
    assert edge[0]["Emp"] is not None and edge[0]["EmpS"] is None and edge[0]["Sep"] is None


def test_cpi_flat_file_crlf_and_padding():
    cpi = prices.read_annual_cpi(EX / "cpi_excerpt.txt")
    assert cpi == {2024: 313.689, 2025: 321.943}
