import math

import numpy as np
import pandas as pd
import pytest

from cluster_intelligence import qcew
from cluster_intelligence.geography import Metro
from tests.fixtures.synthetic_raw import HEADER


def _csv(tmp_path, rows, name="f.csv"):
    p = tmp_path / name
    pd.DataFrame(rows, columns=HEADER).to_csv(p, index=False)
    return p


def _r(area, own, ind, agg, emp, disc="", estabs=10, wages=None, year=2023):
    wages = emp * 52 * 1000 if wages is None else wages
    return [area, own, ind, agg, "0", year, "A", disc, estabs, emp, wages, 0, 0, 0, 0]


def test_suppressed_values_become_missing_not_zero(tmp_path):
    p = _csv(tmp_path, [_r("26163", "5", "336", "75", 0, disc="N", estabs=42, wages=0),
                        _r("26163", "5", "331", "75", 0, disc="N", estabs=0, wages=0)])
    df = qcew.read_area_file(p, "county")
    row = df[df["industry"] == "336"].iloc[0]
    assert math.isnan(row["emp"]) and math.isnan(row["wages"])
    assert row["estabs"] == 42  # establishment counts are kept when published
    assert math.isnan(df[df["industry"] == "331"].iloc[0]["estabs"])


def test_only_private_ownership_and_known_levels_are_kept(tmp_path):
    p = _csv(tmp_path, [_r("26163", "5", "10", "71", 100), _r("26163", "0", "10", "70", 999),
                        _r("26163", "1", "10", "71", 5), _r("26163", "5", "3361", "76", 7)])
    df = qcew.read_area_file(p, "county")
    assert list(df["emp"]) == [100]


def test_duplicate_rows_are_rejected(tmp_path):
    p = _csv(tmp_path, [_r("26163", "5", "10", "71", 100), _r("26163", "5", "10", "71", 100)])
    with pytest.raises(ValueError, match="duplicate"):
        qcew.read_area_file(p, "county")


def test_missing_columns_are_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("area_fips,own_code\n26163,5\n")
    with pytest.raises(ValueError, match="missing QCEW columns"):
        qcew.read_area_file(p, "county")


METRO = Metro("m", "M", "19820", "t", "C1982", ("MI",), {"26001": "a", "26003": "b"})


def _frame(rows):
    return pd.DataFrame(rows, columns=["area", "industry", "level", "year", "emp", "wages", "estabs", "suppressed"])


def _base(published_total=300.0, a_336=50.0, published_336=80.0):
    return _frame([
        ["US000", "10", "total", 2023, 1e6, 1e9, 1e4, False],
        ["US000", "336", "subsector", 2023, 1e4, 1e7, 100, False],
        ["US000", "332", "subsector", 2023, 1e4, 1e7, 100, False],
        ["26001", "10", "total", 2023, 100.0, 1e5, 10, False],
        ["26003", "10", "total", 2023, 200.0, 2e5, 20, False],
        ["26001", "336", "subsector", 2023, a_336, 5e4, 5, np.isnan(a_336)],
        ["26003", "336", "subsector", 2023, 30.0, 3e4, 3, False],
        ["C1982", "10", "total", 2023, published_total, 3e5, 30, False],
        ["C1982", "336", "subsector", 2023, published_336, 8e4, 8, False],
    ])


LOADED = {("26001", 2023), ("26003", 2023), ("C1982", 2023), ("US000", 2023)}


def _agg(data):
    cons = qcew.delineation_consistency(data, METRO, [2023], LOADED)
    return cons, qcew.aggregate_metro(data, METRO, [2023], LOADED, cons).set_index("industry")


def test_county_sum_used_when_all_disclosed_and_absent_rows_are_zero():
    cons, out = _agg(_base())
    assert cons[2023]["consistent"]
    assert out.loc["336", "emp"] == 80 and out.loc["336", "source"] == "county_sum"
    assert out.loc["332", "emp"] == 0 and out.loc["332", "source"] == "county_sum"
    assert out.loc["10", "emp"] == 300


def test_published_metro_used_for_suppressed_county_when_delineation_matches():
    _, out = _agg(_base(a_336=np.nan, published_336=77.0))
    assert out.loc["336", "emp"] == 77 and out.loc["336", "source"] == "msa_published"


def test_suppressed_when_published_metro_uses_different_counties():
    cons, out = _agg(_base(published_total=450.0, a_336=np.nan))
    assert not cons[2023]["consistent"]
    assert math.isnan(out.loc["336", "emp"]) and out.loc["336", "source"] == "suppressed"


def test_missing_county_file_never_counts_as_zero():
    data = _base()
    loaded = LOADED - {("26003", 2023)}
    cons = qcew.delineation_consistency(data, METRO, [2023], loaded)
    out = qcew.aggregate_metro(data, METRO, [2023], loaded, cons).set_index("industry")
    assert math.isnan(out.loc["332", "emp"]) and out.loc["332", "source"] == "missing"


def test_metro_total_is_not_added_to_its_counties():
    _, out = _agg(_base())
    assert out.loc["10", "emp"] == 300  # not 600 (counties + published metro)


def test_weekly_wage():
    w = qcew.weekly_wage(pd.Series([52_000.0, 1.0]), pd.Series([1.0, 0.0]))
    assert w.iloc[0] == 1000 and math.isnan(w.iloc[1])
