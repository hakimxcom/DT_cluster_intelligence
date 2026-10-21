"""Download every raw source file into data/raw/ and log each attempt.

Usage (from the repository root):

    python scripts/fetch_sources.py --contact you@example.com
    python scripts/fetch_sources.py --contact you@example.com --start 2014 --only qcew,bea

BLS asks automated clients to identify themselves, so --contact is sent in the
User-Agent header. A free Census API key (https://api.census.gov/data/key_signup.html)
can be supplied with the CENSUS_API_KEY environment variable; without one the
Census API allows a limited number of requests per day, which this script
stays well under. Existing files are kept unless --refresh is given.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cluster_intelligence import acs, bea, cbp, prices, qcew, qwi  # noqa: E402
from cluster_intelligence.geography import load_config, load_metros  # noqa: E402
from cluster_intelligence.sources import RetrievalLog  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ALL = ["delineation", "qcew", "cbp", "bea", "acs", "qwi", "cpi"]


class Fetcher:
    def __init__(self, contact: str, refresh: bool, trim_qcew: bool = False):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = f"cluster-intelligence research pipeline ({contact})"
        self.refresh = refresh
        self.trim_qcew = trim_qcew
        self.log = RetrievalLog(RAW / "retrieval_log.json")
        self.key = os.environ.get("CENSUS_API_KEY")

    def get(self, source: str, url: str, dest: Path, census: bool = False) -> bool:
        if dest.exists() and not self.refresh:
            print(f"  keep   {dest.relative_to(ROOT)}")
            return True
        if census and self.key:
            url += f"&key={self.key}"
        for attempt in range(4):
            try:
                # The Census API answers a rejected request (e.g. no key) with a
                # redirect to an HTML page; following it would save HTML as data.
                r = self.s.get(url, timeout=120, allow_redirects=not census)
            except requests.RequestException as e:
                msg = str(e)
                err = f"{type(e).__name__}: " + ("connection refused by the network proxy (403)" if "403" in msg else msg[:160])
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200 and r.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                content, detail = r.content, ""
                if source == "qcew" and self.trim_qcew and dest.suffix == ".csv" and dest.name != "industry_titles.csv":
                    content, detail = trim_qcew(content)
                dest.write_bytes(content)
                self.log.record(source, url.split("&key=")[0], dest, "ok", detail)
                print(f"  ok     {dest.relative_to(ROOT)} ({len(r.content):,} bytes)")
                return True
            err = f"HTTP {r.status_code}"
            if r.is_redirect:
                err += f" redirect to {r.headers.get('Location', '?')}"
                break
            if r.status_code in (204, 400, 404):
                break  # not published (yet); retrying will not help
            time.sleep(2 ** attempt)
        self.log.record(source, url.split("&key=")[0], None, "failed", err)
        print(f"  FAIL   {url.split('&key=')[0]} -> {err}")
        return False


def trim_qcew(content: bytes) -> tuple[bytes, str]:
    """Keep only the private-ownership rows at the aggregation levels the
    pipeline reads, so a full download is small enough to hand over. The
    original file's checksum is recorded so the trim is traceable."""
    import csv
    import hashlib
    import io
    keep = {lvl for levels in qcew.AGGLVL.values() for lvl in levels}
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    own, agg = header.index("own_code"), header.index("agglvl_code")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    w.writerows(row for row in reader if row and row[own] == qcew.OWN_PRIVATE and row[agg] in keep)
    original = hashlib.sha256(content).hexdigest()
    return out.getvalue().encode(), f"trimmed to own_code 5 and agglvl {sorted(keep)}; original sha256 {original}, {len(content)} bytes"


def latest_qcew_year(f: Fetcher, start: int) -> int:
    for year in range(dt.date.today().year, start, -1):
        if f.get("qcew", qcew.area_url(year, "US000"), qcew.raw_path(RAW, year, "US000")):
            return year
    raise SystemExit("No QCEW annual file found; check the network or the BLS site.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contact", required=True, help="email or URL identifying you to BLS/Census")
    ap.add_argument("--start", type=int, default=2014, help="first QCEW year (default 2014)")
    ap.add_argument("--only", default=",".join(ALL), help=f"comma-separated subset of {ALL}")
    ap.add_argument("--refresh", action="store_true", help="re-download files that already exist")
    ap.add_argument("--trim-qcew", action="store_true",
                    help="store only the QCEW rows the pipeline uses (smaller files for handing data over)")
    args = ap.parse_args()
    only = set(args.only.split(","))
    f = Fetcher(args.contact, args.refresh, args.trim_qcew)
    metros, cfg = load_metros(), load_config()
    by_state: dict[str, list[str]] = {}
    for m in metros:
        for c in m.county_fips:
            by_state.setdefault(c[:2], []).append(c[2:])
    try:
        if "delineation" in only:
            print("Delineation file")
            f.get("delineation", cfg["delineation"]["file_url"], RAW / "delineation" / "list1_2023.xlsx")

        end = None
        if "qcew" in only:
            print("QCEW")
            end = latest_qcew_year(f, args.start)
            f.get("qcew", "https://data.bls.gov/cew/doc/titles/industry/industry_titles.csv",
                  RAW / "qcew" / "industry_titles.csv")
            areas = [m.qcew_area for m in metros] + [c for m in metros for c in m.county_fips] \
                + [s["qcew_area"] for s in cfg["states"]] + ["US000"]
            for year in range(args.start, end + 1):
                for area in areas:
                    f.get("qcew", qcew.area_url(year, area), qcew.raw_path(RAW, year, area))
        end = end or dt.date.today().year - 1

        if "cbp" in only:
            print("CBP")
            got = []
            for year in range(dt.date.today().year - 1, 2016, -1):
                if all(f.get("cbp", cbp.api_url(year, st, cs), RAW / "cbp" / f"{year}_{st}.json", census=True)
                       for st, cs in by_state.items()):
                    got.append(year)
                    break
            base = max(args.start, 2017)  # CBP API with NAICS2017 variables starts in 2017
            if got and base < got[0]:
                for st, cs in by_state.items():
                    f.get("cbp", cbp.api_url(base, st, cs), RAW / "cbp" / f"{base}_{st}.json", census=True)

        if "bea" in only:
            print("BEA")
            for table in ("CAGDP2", "CAGDP9"):
                f.get("bea", bea.TABLE_URL.format(table=table), RAW / "bea" / f"{table}.zip")

        if "acs" in only:
            print("ACS")
            cbsas = ",".join(m.cbsa_code for m in metros)
            states = ",".join(s["fips"] for s in cfg["states"])
            for year in range(dt.date.today().year - 1, 2018, -1):
                ok = f.get("acs", acs.api_url(year, f"metropolitan%20statistical%20area/micropolitan%20statistical%20area:{cbsas}"),
                           RAW / "acs" / f"{year}_metro.json", census=True)
                if ok:
                    f.get("acs", acs.api_url(year, f"state:{states}"), RAW / "acs" / f"{year}_state.json", census=True)
                    break

        if "qwi" in only:
            print("QWI")
            for year in range(max(args.start, end - 4), end + 1):
                for q in range(1, 5):
                    for st, cs in by_state.items():
                        f.get("qwi", qwi.api_url(year, q, st, cs), RAW / "qwi" / f"{year}_q{q}_{st}.json", census=True)

        if "cpi" in only:
            print("CPI")
            f.get("cpi", prices.URL, RAW / "cpi" / "cu.data.1.AllItems")
    finally:
        f.log.save()
        print(f"Retrieval log: {f.log.path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
