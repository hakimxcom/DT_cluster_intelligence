from pathlib import Path

import pandas as pd
import pytest

from cluster_intelligence.geography import (Metro, check_internal_consistency, load_metros,
                                            read_delineation_file, verify_against_delineation)

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / "data" / "raw" / "delineation" / "list1_2023.xlsx"


def test_three_metros_with_expected_county_counts():
    metros = {m.id: m for m in load_metros()}
    assert set(metros) == {"detroit", "chicago", "cleveland"}
    assert len(metros["detroit"].counties) == 6
    assert len(metros["chicago"].counties) == 13
    assert len(metros["cleveland"].counties) == 6


def test_chicago_spans_illinois_and_indiana_and_excludes_kenosha():
    chicago = next(m for m in load_metros() if m.id == "chicago")
    assert {f[:2] for f in chicago.counties} == {"17", "18"}
    assert "55059" not in chicago.counties


def test_no_county_in_two_metros():
    seen = [c for m in load_metros() for c in m.counties]
    assert len(seen) == len(set(seen))


def test_consistency_rejects_double_assignment_and_foreign_state():
    a = Metro("a", "A", "19820", "t", "C1982", ("MI",), {"26163": "Wayne"})
    b = Metro("b", "B", "17460", "t", "C1746", ("MI",), {"26163": "Wayne"})
    with pytest.raises(ValueError, match="both"):
        check_internal_consistency([a, b])
    c = Metro("c", "C", "17460", "t", "C1746", ("OH",), {"26163": "Wayne"})
    with pytest.raises(ValueError, match="outside"):
        check_internal_consistency([c])


def _workbook(tmp_path, metros, drop=None, add=None):
    rows = []
    for m in metros:
        for fips in m.counties:
            if (m.id, fips) == drop:
                continue
            rows.append([m.cbsa_code, "", "", m.cbsa_title, "Metropolitan Statistical Area", "", "", "",
                         "x County", "State", fips[:2], fips[2:], "Central"])
    if add:
        m = next(x for x in metros if x.id == add[0])
        rows.append([m.cbsa_code, "", "", m.cbsa_title, "Metropolitan Statistical Area", "", "", "",
                     "x County", "State", add[1][:2], add[1][2:], "Outlying"])
    header = ["CBSA Code", "Metropolitan Division Code", "CSA Code", "CBSA Title",
              "Metropolitan/Micropolitan Statistical Area", "Metropolitan Division Title", "CSA Title",
              "County/County Equivalent", "County Name", "State Name", "FIPS State Code", "FIPS County Code",
              "Central/Outlying County"]
    df = pd.DataFrame([["List 1. CORE BASED STATISTICAL AREAS"] + [""] * 12, [""] * 13, header] + rows)
    path = tmp_path / "list1.xlsx"
    df.to_excel(path, header=False, index=False)
    return path


def test_verification_passes_on_matching_file(tmp_path):
    metros = load_metros()
    df = read_delineation_file(_workbook(tmp_path, metros))
    assert verify_against_delineation(metros, df) == []


def test_verification_reports_missing_and_extra_counties(tmp_path):
    metros = load_metros()
    df = read_delineation_file(_workbook(tmp_path, metros, drop=("cleveland", "39007"), add=("chicago", "55059")))
    problems = verify_against_delineation(metros, df)
    assert any("cleveland" in p and "39007" in p for p in problems)
    assert any("chicago" in p and "55059" in p for p in problems)


@pytest.mark.skipif(not OFFICIAL.exists(), reason="official delineation file not downloaded (run scripts/fetch_sources.py)")
def test_config_matches_official_delineation_file():
    assert verify_against_delineation(load_metros(), read_delineation_file(OFFICIAL)) == []
