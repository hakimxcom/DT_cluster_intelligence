import pytest

from cluster_intelligence.shift_share import decompose


def test_manual_example():
    # Local industry 1,000 -> 1,150; national industry 10,000 -> 10,500 (+5%);
    # national total 100,000 -> 102,000 (+2%).
    ss = decompose(1000, 1150, 10_000, 10_500, 100_000, 102_000)
    assert ss.status == "ok"
    assert ss.national == pytest.approx(20)        # 1000 * 0.02
    assert ss.industry_mix == pytest.approx(30)    # 1000 * (0.05 - 0.02)
    assert ss.regional == pytest.approx(100)       # 1000 * (0.15 - 0.05)
    assert ss.national + ss.industry_mix + ss.regional == pytest.approx(ss.observed_change)
    assert abs(ss.residual) < 1e-9


def test_declining_industry_negative_components():
    ss = decompose(2000, 1800, 50_000, 45_000, 1_000_000, 1_010_000)
    assert ss.status == "ok"
    assert ss.industry_mix < 0
    assert ss.national + ss.industry_mix + ss.regional == pytest.approx(-200)


def test_zero_base_returns_change_without_components():
    ss = decompose(0, 50, 100, 120, 1000, 1100)
    assert ss.status == "zero_base" and ss.observed_change == 50
    assert ss.national is None and ss.regional is None


@pytest.mark.parametrize("local", [(None, 10), (10, None)])
def test_missing_local_never_produces_regional_effect(local):
    ss = decompose(*local, 100, 120, 1000, 1100)
    assert ss.status == "missing_local" and ss.regional is None


def test_missing_national_never_produces_regional_effect():
    ss = decompose(100, 120, None, 120, 1000, 1100)
    assert ss.status == "missing_national" and ss.regional is None and ss.observed_change == 20


def test_reconciliation_holds_across_many_inputs():
    import random
    rnd = random.Random(1)
    for _ in range(1000):
        e0, e1 = rnd.uniform(1, 1e6), rnd.uniform(0, 1e6)
        n0, n1 = rnd.uniform(1, 1e8), rnd.uniform(1, 1e8)
        t0, t1 = rnd.uniform(1e8, 2e8), rnd.uniform(1e8, 2e8)
        ss = decompose(e0, e1, n0, n1, t0, t1)
        assert ss.status == "ok", ss
