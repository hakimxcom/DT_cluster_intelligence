"""End-to-end build on the SYNTHETIC fixture, plus handoff checks."""
import json
import shutil
from pathlib import Path

import pytest

from cluster_intelligence.build import Builder
from cluster_intelligence.handoff import WEBSITE_SUBDIR, export, verify
from cluster_intelligence.sources import SOURCES
from tests.fixtures import synthetic_raw


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    synthetic_raw.build(root / "raw")
    b = Builder(root / "raw", root / "out", synthetic_raw.YEARS, external_dir=root / "none",
                generated_at="2026-01-01T00:00:00+00:00")
    manifest = b.run()
    return b, manifest, root


def test_build_completes_and_all_checks_pass(built):
    _, m, _ = built
    assert m["status"] == "complete", [c for c in m["validation"] if not c["passed"]]
    assert m["years"] == synthetic_raw.YEARS


def test_every_inventory_source_reported_with_status(built):
    _, m, _ = built
    by = {s["id"]: s for s in m["sources"]}
    assert set(by) == {s["id"] for s in SOURCES}
    for s in m["sources"]:
        assert s["status"] in {"integrated", "used_for_verification", "not_retrieved", "not_integrated"}
        if s["status"] in {"not_retrieved", "not_integrated"}:
            assert s["reason"]
    assert by["cluster_mapping"]["status"] == "not_integrated"


def test_suppressed_cells_stay_missing(built):
    b, _, _ = built
    a = b.annual
    cle = a[(a["area"] == "cleveland") & (a["industry"] == "332")].set_index("year")
    # Ashtabula's cell is suppressed; BLS's pre-2023 Cleveland metro excludes Ashtabula,
    # so no substitute is valid before 2023.
    assert cle.loc[2019, "source"] == "suppressed" and cle.loc[2019, "emp"] != cle.loc[2019, "emp"]
    assert cle.loc[2023, "source"] == "msa_published"
    chi = a[(a["area"] == "chicago") & (a["industry"] == "336")]
    assert set(chi["source"]) == {"msa_published"}


def test_same_years_and_industries_for_every_geography(built):
    b, _, root = built
    annual = json.loads((root / "out" / "website" / "annual.json").read_text())
    for g in annual["geos"]:
        assert set(annual["data"][g]) == {i["code"] for i in annual["industries"]}
        for rows in annual["data"][g].values():
            assert len(rows) == len(annual["years"])


def test_zero_base_has_no_percentage_and_naics_break_is_withheld(built):
    _, _, root = built
    pair = json.loads((root / "out" / "website" / "pairs" / "2019-2021.json").read_text())
    f = pair["fields"]
    det452 = dict(zip(f, pair["metros"]["detroit"]["452"]))
    assert det452["e0"] == 0 and det452["pct"] is None and det452["status"] == "zero_base"
    across = json.loads((root / "out" / "website" / "pairs" / "2019-2023.json").read_text())
    assert dict(zip(f, across["metros"]["detroit"]["452"]))["status"] == "not_comparable"


def test_shift_share_rows_reconcile_after_rounding(built):
    _, _, root = built
    for path in (root / "out" / "website" / "pairs").glob("*.json"):
        pair = json.loads(path.read_text())
        for metro in pair["metros"].values():
            for row in metro.values():
                e0, e1, chg, pct, ns, im, rc, status = row
                if status == "ok":
                    assert abs(ns + im + rc - chg) <= 2  # each component rounded to whole jobs


def test_lq_matches_manual_calculation(built):
    b, _, _ = built
    a = b.annual.set_index(["area", "industry", "level", "year"])
    local = a.loc[("detroit", "31-33", "sector", 2023)]
    us = a.loc[("us", "31-33", "sector", 2023)]
    lt = a.loc[("detroit", "10", "total", 2023), "emp"]
    ut = a.loc[("us", "10", "total", 2023), "emp"]
    assert local["lq"] == pytest.approx((local["emp"] / lt) / (us["emp"] / ut))


def test_units_and_periods_declared_for_each_integrated_indicator(built):
    _, m, _ = built
    for key in ("qcew", "cbp", "bea", "acs", "qwi"):
        assert key in m["coverage"] and m["coverage"][key].get("unit")
    assert m["cpi_base_year"] == 2023


def test_findings_generated_from_rules(built):
    _, _, root = built
    f = json.loads((root / "out" / "website" / "findings.json").read_text())
    ids = {x["id"] for x in f["findings"]}
    assert {"distinctive", "shared", "specialized_growing", "specialized_declining", "mix_vs_regional",
            "investigate", "context"} <= ids
    assert all(x["rule"] and x["text"] for x in f["findings"])


def test_handoff_copies_exact_files(built, tmp_path):
    _, m, root = built
    site = tmp_path / "site"
    (site / "public").mkdir(parents=True)
    (site / "wrangler.jsonc").write_text("{}")
    dest = export(root / "out" / "website", site)
    assert dest == site / WEBSITE_SUBDIR
    copied = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.json"))
    assert copied == sorted(set(m["files"]) | {"manifest.json"})
    for name in m["files"]:
        assert (dest / name).read_bytes() == (root / "out" / "website" / name).read_bytes()


def test_handoff_rejects_tampered_or_failed_dataset(built, tmp_path):
    _, _, root = built
    src = tmp_path / "web"
    shutil.copytree(root / "out" / "website", src)
    (src / "findings.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        verify(src)
    shutil.rmtree(src)
    shutil.copytree(root / "out" / "website", src)
    man = json.loads((src / "manifest.json").read_text())
    man["status"] = "failed_validation"
    (src / "manifest.json").write_text(json.dumps(man))
    site = tmp_path / "site"
    (site / "public").mkdir(parents=True)
    (site / "wrangler.jsonc").write_text("{}")
    with pytest.raises(ValueError, match="failed validation"):
        export(src, site)


def test_handoff_refuses_wrong_repository(built, tmp_path):
    _, _, root = built
    with pytest.raises(ValueError, match="does not look like"):
        export(root / "out" / "website", tmp_path)


def test_empty_raw_directory_reports_no_data_honestly(tmp_path):
    m = Builder(tmp_path / "raw", tmp_path / "out", [2022, 2023], external_dir=tmp_path / "none").run()
    assert m["status"] == "no_data" and m["years"] == []
    assert not any(s["status"] == "integrated" for s in m["sources"])
    assert set(m["files"]) == {"context.json", "clusters.json"}
