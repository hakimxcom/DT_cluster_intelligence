import math

import pytest

from cluster_intelligence.metrics import growth, location_quotient, share


def test_lq_manual_example():
    # Local: 5,000 of 100,000 jobs (5%). Nation: 1m of 50m (2%). LQ = 2.5.
    assert location_quotient(5_000, 100_000, 1_000_000, 50_000_000) == pytest.approx(2.5)


def test_lq_equal_concentration_is_one():
    assert location_quotient(20, 200, 1_000, 10_000) == pytest.approx(1.0)


def test_lq_below_one():
    assert location_quotient(10, 1_000, 300, 10_000) == pytest.approx(1 / 3)


@pytest.mark.parametrize("args", [
    (None, 100, 10, 1000), (5, None, 10, 1000), (5, 100, None, 1000), (5, 100, 10, None),
    (5, 0, 10, 1000), (5, 100, 0, 1000), (float("nan"), 100, 10, 1000),
])
def test_lq_missing_or_undefined_inputs_return_none(args):
    assert location_quotient(*args) is None


def test_lq_zero_local_employment_is_zero_not_missing():
    assert location_quotient(0, 100, 10, 1000) == 0


def test_share():
    assert share(25, 100) == 0.25
    assert share(None, 100) is None
    assert share(5, 0) is None


def test_growth_positive():
    g = growth(1000, 1100)
    assert (g.change, g.pct, g.status) == (100, pytest.approx(0.1), "ok")


def test_growth_negative():
    g = growth(1000, 900)
    assert g.change == -100 and g.pct == pytest.approx(-0.1)


def test_growth_zero_base_has_change_but_no_percentage():
    g = growth(0, 250)
    assert g.change == 250 and g.pct is None and g.status == "zero_base"


@pytest.mark.parametrize("start,end", [(None, 5), (5, None), (math.nan, 5)])
def test_growth_missing(start, end):
    g = growth(start, end)
    assert g.change is None and g.pct is None and g.status == "missing"
