import math

import pytest

from cluster_intelligence import acs, cbp, naics, prices, qwi
from cluster_intelligence.sources import SOURCES


def test_inventory_covers_every_requested_source():
    ids = {s["id"] for s in SOURCES}
    assert {"qcew", "cbp", "bea", "qwi", "acs", "cluster_mapping", "mcda", "semcog", "cmap", "ohiolmi"} <= ids
    for s in SOURCES:
        assert s["url"].startswith("https://") and s["publisher"] and s["licence"]


def test_acs_moe_proportion_and_fallback():
    assert acs.moe_proportion(300, 1000, 30, 50) == pytest.approx(math.sqrt(900 - 0.09 * 2500) / 1000)
    assert acs.moe_proportion(900, 1000, 10, 100) == pytest.approx(math.sqrt(100 + 0.81 * 10000) / 1000)
    assert acs.moe_sum([3, 4]) == 5


def test_acs_significance():
    assert acs.significantly_different(40, 1, 35, 1)
    assert not acs.significantly_different(40, 3, 37, 3)


def test_acs_sentinel_values_are_dropped():
    head = ["NAME"] + [f"{v}{s}" for v in acs.VARIABLES.values() for s in ("E", "M")] + ["state"]
    row = ["X"] + ["-666666666"] * (len(head) - 2) + ["26"]
    out = acs.parse_response([head, row])
    assert out[0]["indicators"] == {}


def test_cbp_withheld_values_are_missing_and_labels_checked():
    head = ["NAICS2017", "ESTAB", "EMP", "EMP_N", "PAYANN", "PAYANN_N", "EMPSZES", "EMPSZES_LABEL", "state", "county"]
    rows = [head, ["31-33", "10", "0", "D", "0", "D", "001", "All establishments", "26", "163"],
            ["3361", "5", "100", "G", "1", "G", "001", "All establishments", "26", "163"]]
    out = cbp.parse_response(rows, 2022)
    assert len(out) == 1 and out[0]["emp"] is None and out[0]["estab"] == 10
    bad = [head, ["31-33", "10", "5", "G", "1", "G", "212", "Establishments with 1,000 employees or more", "26", "163"]]
    with pytest.raises(ValueError):
        cbp.parse_response(bad, 2022)


def test_cbp_aggregate_requires_every_county():
    recs = [{"county": "26163", "naics": "10", "size": "001", "estab": 5, "emp": 50, "payann": 9, "year": 2022}]
    assert cbp.aggregate(recs, ["26163", "26125"])["10"]["establishments"] is None
    assert cbp.aggregate(recs, ["26163"])["10"]["establishments"] == 5


def test_qwi_flagged_values_make_metro_missing():
    head = qwi.MEASURES + ["s" + m for m in qwi.MEASURES] + ["year", "quarter", "state", "county"]
    def rows(flag):
        return [head] + [["100", "90", "10", "9", "5", "4", "4000"] + [flag] * 7 + ["2023", str(q), "26", "163"] for q in range(1, 5)]
    ok = qwi.annual_metro(qwi.parse_response(rows("1")), ["26163"], 2023)
    assert ok["hire_rate"] == pytest.approx(0.1) and ok["avg_monthly_earnings_stable"] == 4000
    assert qwi.annual_metro(qwi.parse_response(rows("5")), ["26163"], 2023) is None


def test_cpi_and_deflate(tmp_path):
    p = tmp_path / "cpi"
    p.write_text("series_id\tyear\tperiod\tvalue\tfootnote_codes\nCUUR0000SA0\t2020\tM13\t250.0\t\nCUUR0000SA0\t2023\tM13\t300.0\t\nCUUR0000SA0\t2023\tM01\t1.0\t\n")
    cpi = prices.read_annual_cpi(p)
    assert cpi == {2020: 250.0, 2023: 300.0}
    assert prices.deflate(1000, 2020, 2023, cpi) == pytest.approx(1200)
    assert prices.deflate(1000, 2019, 2023, cpi) is None


def test_naics_comparability_across_2022_revision():
    assert naics.comparable("31-33", "sector", 2019, 2023)
    assert naics.comparable("336", "subsector", 2019, 2023)
    assert not naics.comparable("452", "subsector", 2019, 2023)
    assert not naics.comparable("511", "subsector", 2021, 2022)
    assert naics.comparable("455", "subsector", 2022, 2024)
    assert naics.sector_of("336") == "31-33" and naics.sector_of("722") == "72"


def test_fetch_trim_keeps_only_rows_the_pipeline_reads():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import fetch_sources
    src = b"area_fips,own_code,industry_code,agglvl_code\n26163,5,10,71\n26163,0,10,70\n26163,5,3361,76\n"
    out, detail = fetch_sources.trim_qcew(src)
    assert out.decode().splitlines() == ["area_fips,own_code,industry_code,agglvl_code", "26163,5,10,71"]
    assert "original sha256" in detail
