"""Build the processed tables and the compact website dataset from raw files.

Inputs live under data/raw (see scripts/fetch_sources.py). Outputs:

* data/processed/*.csv            full tidy tables for analysis
* data/processed/website/*.json   the exact files the dashboard consumes
"""
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import acs, bea, cbp, clusters, findings, naics, prices, qcew, qwi
from .geography import ROOT, load_config, load_metros
from .metrics import growth, location_quotient
from .shift_share import decompose
from .sources import NOTICES, SOURCES, RetrievalLog, sha256
from .validation import Report, validate_annual, validate_pairs

SRC_CODE = {"county_sum": "c", "msa_published": "m", "published": "p", "suppressed": "s", "missing": "x"}


def _r(x, nd=0):
    """Round for JSON; NaN/None become null."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return int(round(x)) if nd == 0 else round(float(x), nd)


def _git_commit(path: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


class Builder:
    def __init__(self, raw_dir: Path, out_dir: Path, years: list[int], external_dir: Path | None = None,
                 generated_at: str | None = None, synthetic: bool = False):
        self.raw = Path(raw_dir)
        self.synthetic = synthetic
        self.out = Path(out_dir)
        self.web = self.out / "website"
        self.years_requested = years
        self.external = Path(external_dir) if external_dir else ROOT / "data" / "external"
        self.metros = load_metros()
        self.cfg = load_config()
        self.log = RetrievalLog(self.raw / "retrieval_log.json")
        self.report = Report()
        self.generated_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.source_status: dict[str, dict] = {}
        self.titles = dict(naics.SECTOR_TITLES)

    # ------------------------------------------------------------------ QCEW
    def load_qcew(self):
        areas = {"US000": "national"}
        for m in self.metros:
            for area in m.qcew_areas:
                areas[area] = "msa"
            for c in m.county_fips:
                areas[c] = "county"
        for s in self.cfg["states"]:
            areas[s["qcew_area"]] = "state"
        data, loaded = qcew.load_raw(self.raw, self.years_requested, areas)
        years = [y for y in self.years_requested
                 if ("US000", y) in loaded and all((c, y) in loaded for m in self.metros for c in m.county_fips)]
        self.qcew_raw, self.qcew_loaded, self.years = data, loaded, years
        titles = self.raw / "qcew" / "industry_titles.csv"
        if titles.exists():
            self.titles.update(naics.load_titles(titles))

    def build_annual(self) -> pd.DataFrame:
        frames = [qcew.national(self.qcew_raw[self.qcew_raw["year"].isin(self.years)])]
        self.consistency = {}
        for m in self.metros:
            cons = qcew.delineation_consistency(self.qcew_raw, m, self.years, self.qcew_loaded)
            self.consistency[m.id] = cons
            frames.append(qcew.aggregate_metro(self.qcew_raw, m, self.years, self.qcew_loaded, cons))
        annual = pd.concat(frames, ignore_index=True)
        annual = annual[~annual["industry"].isin(qcew.EXCLUDED_INDUSTRIES) | (annual["level"] == "total")]
        annual = annual[annual["industry"] != "92"]  # no private-ownership public administration

        tot = annual[annual["level"] == "total"].set_index(["area", "year"])["emp"]
        us = annual[annual["area"] == "us"].set_index(["industry", "level", "year"])["emp"]
        annual["area_total"] = [tot.get((a, y), np.nan) for a, y in zip(annual["area"], annual["year"])]
        annual["us_industry"] = [us.get((i, l, y), np.nan) for i, l, y in zip(annual["industry"], annual["level"], annual["year"])]
        annual["us_total"] = [tot.get(("us", y), np.nan) for y in annual["year"]]
        annual["share"] = np.where(annual["area_total"] > 0, annual["emp"] / annual["area_total"], np.nan)
        annual["lq"] = [
            location_quotient(*(None if pd.isna(v) else float(v) for v in vals))
            for vals in annual[["emp", "area_total", "us_industry", "us_total"]].itertuples(index=False)
        ]
        annual["lq"] = annual["lq"].astype(float)
        annual["wkwage"] = qcew.weekly_wage(annual["wages"], annual["emp"])
        cpi_path = self.raw / "cpi" / "cu.data.1.AllItems"
        self.cpi = prices.read_annual_cpi(cpi_path) if cpi_path.exists() else {}
        self.cpi_base = max((y for y in self.years if y in self.cpi), default=None)
        if self.cpi_base:
            annual["wkwage_real"] = [prices.deflate(None if pd.isna(w) else w, y, self.cpi_base, self.cpi)
                                     for w, y in zip(annual["wkwage"], annual["year"])]
        else:
            annual["wkwage_real"] = np.nan
        annual["wkwage_real"] = annual["wkwage_real"].astype(float)
        self.annual = annual
        validate_annual(annual, self.report)
        return annual

    def build_pairs(self) -> dict[str, dict]:
        a = self.annual.set_index(["area", "industry", "level", "year"])
        pairs = {}
        inds = self.annual[self.annual["level"].isin(["sector", "subsector"])][["industry", "level"]].drop_duplicates()
        for i, start in enumerate(self.years):
            for end in self.years[i + 1:]:
                us0, us1 = a.loc[("us", "10", "total", start), "emp"], a.loc[("us", "10", "total", end), "emp"]
                rec = {"start": start, "end": end, "metros": {}, "us": {}, "totals": {}}
                for code, level in inds.itertuples(index=False):
                    n0 = a["emp"].get(("us", code, level, start), np.nan)
                    n1 = a["emp"].get(("us", code, level, end), np.nan)
                    g = growth(None if pd.isna(n0) else n0, None if pd.isna(n1) else n1)
                    rec["us"][code] = {"e0": g.start, "e1": g.end, "chg": g.change, "pct": g.pct}
                for m in self.metros:
                    out = {}
                    for code, level in inds.itertuples(index=False):
                        e0 = a["emp"].get((m.id, code, level, start), np.nan)
                        e1 = a["emp"].get((m.id, code, level, end), np.nan)
                        e0 = None if pd.isna(e0) else float(e0)
                        e1 = None if pd.isna(e1) else float(e1)
                        if not naics.comparable(code, level, start, end):
                            out[code] = {"e0": e0, "e1": e1, "chg": None, "pct": None, "ns": None,
                                         "im": None, "rc": None, "status": "not_comparable", "level": level}
                            continue
                        n = rec["us"][code]
                        ss = decompose(e0, e1, n["e0"], n["e1"], us0, us1)
                        g = growth(e0, e1)
                        out[code] = {"e0": e0, "e1": e1, "chg": g.change, "pct": g.pct, "ns": ss.national,
                                     "im": ss.industry_mix, "rc": ss.regional, "status": ss.status,
                                     "residual": ss.residual, "level": level}
                    rec["metros"][m.id] = out
                    t0 = a["emp"].get((m.id, "10", "total", start), np.nan)
                    t1 = a["emp"].get((m.id, "10", "total", end), np.nan)
                    sectors = [v for v in out.values() if v["level"] == "sector" and v["status"] == "ok"]
                    base_cov = sum(v["e0"] for v in sectors)
                    gt = growth(None if pd.isna(t0) else float(t0), None if pd.isna(t1) else float(t1))
                    rec["totals"][m.id] = {
                        "e0": gt.start, "e1": gt.end, "chg": gt.change, "pct": gt.pct,
                        "ns": sum(v["ns"] for v in sectors) if sectors else None,
                        "im": sum(v["im"] for v in sectors) if sectors else None,
                        "rc": sum(v["rc"] for v in sectors) if sectors else None,
                        "coverage": base_cov / gt.start if sectors and gt.start else None,
                    }
                pairs[f"{start}-{end}"] = rec
        validate_pairs(pairs, self.report)
        self.pairs = pairs
        return pairs

    # --------------------------------------------------------------- context
    def _json_files(self, sub: str) -> list[Path]:
        d = self.raw / sub
        return sorted(d.glob("*.json")) if d.exists() else []

    def build_context(self) -> dict:
        ctx = {}
        # CBP
        recs, years = [], set()
        for p in self._json_files("cbp"):
            year = int(p.stem.split("_")[0])
            recs += cbp.parse_response(json.loads(p.read_text()), year)
            years.add(year)
        if recs:
            latest = max(years)
            ctx["cbp"] = {"status": "integrated", "year": latest, "years": sorted(years), "unit_payroll": "thousands of current dollars",
                          "metros": {m.id: {str(y): cbp.aggregate([r for r in recs if r["year"] == y], m.county_fips)
                                            for y in sorted(years)} for m in self.metros}}
        # BEA
        z2, z9 = self.raw / "bea" / "CAGDP2.zip", self.raw / "bea" / "CAGDP9.zip"
        if z2.exists() and z9.exists():
            nom, real = bea.read_table(z2), bea.read_table(z9)
            ctx["bea"] = {"status": "integrated", "unit": "thousands of dollars",
                          "real_basis": "chained 2017 dollars", "nominal_basis": "current dollars",
                          "metros": {m.id: bea.metro_series(nom, real, m.cbsa_code, m.county_fips) for m in self.metros},
                          "states": {s["id"]: bea.area_series(nom, real, s["fips"] + "000") for s in self.cfg["states"]},
                          "us": bea.area_series(nom, real, "00000")}
        # ACS
        acs_files = self._json_files("acs")
        if acs_files:
            latest = max(int(p.stem.split("_")[0]) for p in acs_files)
            block = {"status": "integrated", "year": latest, "survey": "ACS 1-year", "metros": {}, "states": {}}
            for p in acs_files:
                if int(p.stem.split("_")[0]) != latest:
                    continue
                for r in acs.parse_response(json.loads(p.read_text())):
                    m = next((m for m in self.metros if m.cbsa_code == r["geo_code"]), None)
                    s = next((s for s in self.cfg["states"] if s["fips"] == r["geo_code"]), None)
                    if m and "metro" in p.stem:
                        block["metros"][m.id] = r
                    elif s and "state" in p.stem:
                        block["states"][s["id"]] = r
            ctx["acs"] = block
        # QWI
        qrecs = []
        for p in self._json_files("qwi"):
            qrecs += qwi.parse_response(json.loads(p.read_text()))
        if qrecs:
            qyears = sorted({r["year"] for r in qrecs})
            ctx["qwi"] = {"status": "integrated", "years": qyears, "ownership": "private (A05)",
                          "metros": {m.id: [x for y in qyears if (x := qwi.annual_metro(qrecs, m.county_fips, y))]
                                     for m in self.metros}}
        # QCEW state context
        st = self.qcew_raw[(self.qcew_raw["level"] == "total") & (self.qcew_raw["industry"] == "10")]
        states = {}
        for s in self.cfg["states"]:
            rows = st[st["area"] == s["qcew_area"]].sort_values("year")
            if len(rows):
                states[s["id"]] = [{"year": int(r.year), "emp": _r(r.emp), "wkwage": _r(r.wages / r.emp / 52) if r.emp else None}
                                   for r in rows.itertuples()]
        if states:
            ctx["states_qcew"] = {"status": "integrated", "states": states}
        self.context = ctx
        return ctx

    def build_clusters(self) -> dict:
        path = self.external / "cluster_crosswalk.csv"
        if not path.exists():
            return {"status": "not_available",
                    "reason": "No verified NAICS-to-cluster crosswalk was supplied (data/external/cluster_crosswalk.csv). "
                              "Results are reported as NAICS sector and subsector specialization, not formal clusters."}
        cw = clusters.load_crosswalk(path)
        editions = set(cw["naics_edition"])
        usable = [y for y in self.years if naics.edition(y) in editions]
        if len(usable) < 2:
            return {"status": "not_available",
                    "reason": f"Crosswalk edition {sorted(editions)} does not match the NAICS edition of at least two QCEW years."}
        return {"status": "not_available",
                "reason": "Crosswalk found, but 6-digit QCEW aggregation is not enabled in this build."}

    # ------------------------------------------------------------- findings
    def build_findings(self) -> list[dict]:
        if not self.years or len(self.years) < 2:
            return []
        start, end = self.years[0], self.years[-1]
        pair = self.pairs[f"{start}-{end}"]
        a = self.annual[(self.annual["year"] == end) & self.annual["level"].isin(["sector", "subsector"])]
        end_lq = {m.id: {r.industry: (None if pd.isna(r.lq) else r.lq, None if pd.isna(r.emp) else r.emp)
                         for r in a[a["area"] == m.id].itertuples()} for m in self.metros}
        p = {m.id: {c: v for c, v in pair["metros"][m.id].items()} for m in self.metros}
        p["_totals"] = pair["totals"]
        ctx = {}
        b = self.context.get("bea")
        if b:
            yrs = sorted({r["year"] for r in b["metros"][self.metros[0].id] if r["gdp_real"] is not None})
            if len(yrs) >= 2:
                y0, y1 = max(yrs[0], start), yrs[-1]
                vals = {}
                for m in self.metros:
                    s = {r["year"]: r["gdp_real"] for r in b["metros"][m.id]}
                    vals[m.id] = (s[y1] / s[y0] - 1) if s.get(y0) and s.get(y1) else None
                ctx["gdp_growth"] = {"period": f"{y0}–{y1}", "values": vals}
        c = self.context.get("cbp")
        if c:
            y = str(c["year"])
            vals = {}
            for m in self.metros:
                tot = c["metros"][m.id][y].get("10", {})
                vals[m.id] = 1000 * tot["establishments"] / tot["employment"] if tot.get("establishments") and tot.get("employment") else None
            ctx["estabs_per_1000"] = {"year": c["year"], "values": vals}
        ac = self.context.get("acs")
        if ac:
            ctx["bachelors"] = {"year": ac["year"], "values": {
                m.id: ac["metros"].get(m.id, {}).get("indicators", {}).get("bachelors_or_higher_pct") for m in self.metros}}
        self.findings = findings.generate(end_lq, p, self.metros, lambda c: self.titles.get(c, c), ctx)
        for f in self.findings:
            f["period"] = f"{start}–{end}"
        return self.findings

    # ------------------------------------------------------------- sources
    def resolve_sources(self) -> list[dict]:
        present = {
            "qcew": bool(self.years), "cbp": "cbp" in self.context, "bea": "bea" in self.context,
            "qwi": "qwi" in self.context, "acs": "acs" in self.context, "cpi": bool(self.cpi),
            "delineation": (self.raw / "delineation" / "list1_2023.xlsx").exists(),
            "cluster_mapping": self.clusters["status"] == "integrated",
        }
        out = []
        for s in SOURCES:
            entry = {k: s[k] for k in ("id", "name", "publisher", "url", "role", "use", "licence")}
            if "citation" in s:
                entry["citation"] = s["citation"]
            attempts = self.log.latest(s["id"])
            ok = [e for e in attempts if e["status"] == "ok"]
            failed = [e for e in attempts if e["status"] != "ok"]
            if present.get(s["id"]):
                entry["status"] = "integrated" if s["id"] != "delineation" else "used_for_verification"
                entry["retrieved_at"] = max((e["retrieved_at"] for e in ok), default=None)
            elif s["role"] == "local":
                entry["status"] = "not_integrated"
                entry["reason"] = s["pipeline"] + ". Its geography and definitions differ from the standardized cross-metro comparison."
            elif s["id"] == "cluster_mapping":
                entry["status"] = "not_integrated"
                entry["reason"] = self.clusters["reason"]
            else:
                entry["status"] = "not_retrieved"
                entry["reason"] = (f"Last retrieval attempt failed: {failed[-1]['detail']}" if failed
                                   else "No retrieval has been attempted for this build.")
            out.append(entry)
        return out

    # --------------------------------------------------------------- output
    def write(self) -> dict:
        self.web.mkdir(parents=True, exist_ok=True)
        pairs_dir = self.web / "pairs"
        for old in self.web.rglob("*.json"):
            old.unlink()
        files = {}

        def dump(name, obj):
            path = self.web / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=_json_default))
            files[name] = {"sha256": sha256(path), "bytes": path.stat().st_size}

        has_data = len(self.years) >= 2
        if has_data:
            a = self.annual
            inds = (a[a["level"].isin(["sector", "subsector"])][["industry", "level"]].drop_duplicates()
                    .sort_values(["level", "industry"]))
            industries = [{"code": c, "title": self.titles.get(c, c), "level": l, "sector": naics.sector_of(c)}
                          for c, l in inds.itertuples(index=False)]
            geos = [m.id for m in self.metros] + ["us"]
            idx = a.set_index(["area", "industry", "level", "year"])
            data, totals = {}, {}
            for g in geos:
                data[g] = {}
                for ind in industries:
                    rows = []
                    for y in self.years:
                        key = (g, ind["code"], ind["level"], y)
                        if key in idx.index:
                            r = idx.loc[key]
                            rows.append([_r(r.emp), _r(r.estabs), _r(r.wkwage), _r(r.share, 6), _r(r.lq, 3),
                                         _r(r.wkwage_real), SRC_CODE[r.source]])
                        else:
                            rows.append([None, None, None, None, None, None, "x"])
                    data[g][ind["code"]] = rows
                totals[g] = []
                for y in self.years:
                    r = idx.loc[(g, "10", "total", y)]
                    totals[g].append([_r(r.emp), _r(r.estabs), _r(r.wkwage), _r(r.wkwage_real), SRC_CODE[r.source]])
            dump("annual.json", {"years": self.years, "geos": geos, "industries": industries,
                                 "fields": ["emp", "estabs", "wkwage", "share", "lq", "wkwage_real", "src"],
                                 "total_fields": ["emp", "estabs", "wkwage", "wkwage_real", "src"],
                                 "data": data, "totals": totals})
            for key, rec in self.pairs.items():
                compact = {"start": rec["start"], "end": rec["end"],
                           "fields": ["e0", "e1", "chg", "pct", "ns", "im", "rc", "status"],
                           "us": {c: [_r(v["e0"]), _r(v["e1"]), _r(v["chg"]), _r(v["pct"], 5)] for c, v in rec["us"].items()},
                           "metros": {m: {c: [_r(v["e0"]), _r(v["e1"]), _r(v["chg"]), _r(v["pct"], 5), _r(v["ns"]),
                                              _r(v["im"]), _r(v["rc"]), v["status"]] for c, v in d.items()}
                                      for m, d in rec["metros"].items()},
                           "totals": {m: {k: (_r(v, 5) if k in ("pct", "coverage") else _r(v)) for k, v in t.items()}
                                      for m, t in rec["totals"].items()}}
                dump(f"pairs/{key}.json", compact)
            dump("findings.json", {"period": f"{self.years[0]}–{self.years[-1]}", "rules": findings.RULES,
                                   "scope": "Rules are applied to NAICS sectors and 3-digit subsectors together, so a subsector can appear alongside its parent sector. QCEW private ownership.",
                                   "findings": self.findings})
            # Full tidy tables for researchers.
            self.out.mkdir(parents=True, exist_ok=True)
            a.drop(columns=["area_total", "us_industry", "us_total"]).to_csv(self.out / "qcew_annual_metrics.csv", index=False)
            rows = [{"pair": k, "metro": m, "industry": c, **v} for k, rec in self.pairs.items()
                    for m, d in rec["metros"].items() for c, v in d.items()]
            pd.DataFrame(rows).to_csv(self.out / "shift_share_all_pairs.csv", index=False)
        dump("context.json", json.loads(json.dumps(self.context, default=_json_default), parse_constant=_reject))
        dump("clusters.json", self.clusters)

        geo_verified = (self.raw / "delineation" / "verification.json")
        geo_status = json.loads(geo_verified.read_text()) if geo_verified.exists() else {"status": "not_run"}
        sources = self.resolve_sources()
        manifest = {
            "title": "Regional Industry & Cluster Intelligence",
            "dataset_version": self.generated_at[:10].replace("-", ".") + "+" + (_git_commit(ROOT) or "nogit"),
            "generated_at": self.generated_at,
            "synthetic_fixture": self.synthetic,
            "pipeline": {"repository": "hakimxcom/DT_cluster_intelligence", "commit": _git_commit(ROOT)},
            "status": "complete" if has_data and self.report.ok else ("failed_validation" if has_data else "no_data"),
            "years": self.years,
            "default_period": [self.years[0], self.years[-1]] if has_data else None,
            "ownership": "Private ownership (QCEW own_code 5)",
            "industry_levels": ["NAICS sector (2-digit)", "NAICS subsector (3-digit)"],
            "naics_editions": {str(y): naics.edition(y) for y in self.years},
            "cpi_base_year": self.cpi_base,
            "geography": {
                "delineation": self.cfg["delineation"]["reference"],
                "verification": geo_status,
                "metros": [{"id": m.id, "label": m.label, "cbsa_code": m.cbsa_code, "cbsa_title": m.cbsa_title,
                            "counties": m.counties, "boundary_note": m.boundary_note,
                            "published_metro_consistency": {str(y): v["consistent"] for y, v in self.consistency.get(m.id, {}).items()}}
                           for m in self.metros],
                "states": self.cfg["states"],
            },
            "coverage": self.coverage(),
            "sources": sources,
            "notices": NOTICES,
            "validation": self.report.as_list(),
            "files": files,
        }
        path = self.web / "manifest.json"
        path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, allow_nan=False, default=_json_default))
        self.manifest = manifest
        return manifest

    def coverage(self) -> dict:
        cov = {}
        if self.years:
            cov["qcew"] = {"years": [self.years[0], self.years[-1]], "unit": "jobs (annual average); dollars per week (nominal)"}
        if "cbp" in self.context:
            cov["cbp"] = {"years": self.context["cbp"]["years"], "unit": "establishments; payroll in thousands of current dollars"}
        if "bea" in self.context:
            ys = sorted({r["year"] for v in self.context["bea"]["metros"].values() for r in v})
            cov["bea"] = {"years": [ys[0], ys[-1]], "unit": "thousands of dollars (current; chained 2017 for states and the U.S. only)"}
        if "acs" in self.context:
            cov["acs"] = {"years": [self.context["acs"]["year"]], "unit": "percent of residents; dollars (nominal)"}
        if "qwi" in self.context:
            # Only years with a complete annual value count; a quarter on the
            # publication edge lacks flow measures and does not make a year.
            by_metro = {m: [r["year"] for r in v] for m, v in self.context["qwi"]["metros"].items()}
            cov["qwi"] = {"years": sorted({y for ys in by_metro.values() for y in ys}), "by_metro": by_metro,
                          "unit": "rates per beginning-of-quarter job; dollars per month"}
        if self.cpi_base:
            cov["cpi"] = {"base_year": self.cpi_base, "series": prices.SERIES}
        return cov

    def run(self) -> dict:
        self.load_qcew()
        if len(self.years) >= 2:
            self.build_annual()
            self.build_pairs()
        else:
            self.annual = pd.DataFrame()
            self.consistency = {}
            self.cpi, self.cpi_base, self.pairs = {}, None, {}
            self.report.add("qcew_years", False, f"Fewer than two complete QCEW years in {self.raw}; no comparison possible.")
        self.build_context()
        self.clusters = self.build_clusters()
        self.findings = self.build_findings() if self.pairs else []
        return self.write()


def _json_default(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    raise TypeError(type(o))


def _reject(c):
    raise ValueError(f"non-finite number {c} in output")
