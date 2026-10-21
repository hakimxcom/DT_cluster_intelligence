"""Source inventory and retrieval provenance.

``SOURCES`` is the documented inventory. Each entry's ``role`` says how the
source is meant to be used; its *actual* status in a given build (integrated,
not retrieved, not integrated) is decided at build time from the files and
retrieval log present, never asserted here."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCES: list[dict] = [
    {
        "id": "qcew", "name": "Quarterly Census of Employment and Wages (QCEW)",
        "publisher": "U.S. Bureau of Labor Statistics",
        "url": "https://www.bls.gov/cew/downloadable-data-files.htm",
        "access": "QCEW Open Data area slices, annual averages: https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv",
        "role": "core", "pipeline": "integrated when retrieved",
        "use": "Private-sector employment, establishments and wages by county, metro, state and nation; location quotients; shift-share.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "cbp", "name": "County Business Patterns (CBP)",
        "publisher": "U.S. Census Bureau",
        "url": "https://www.census.gov/programs-surveys/cbp.html",
        "access": "Census Data API: https://api.census.gov/data/{year}/cbp",
        "role": "core", "pipeline": "integrated when retrieved",
        "use": "Establishment counts by employment-size class and annual payroll, aggregated from counties.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "bea", "name": "GDP by county and metropolitan area (CAGDP2, CAGDP9)",
        "publisher": "U.S. Bureau of Economic Analysis",
        "url": "https://www.bea.gov/data/by-place-county-metro-local",
        "access": "https://apps.bea.gov/regional/zip/CAGDP2.zip and CAGDP9.zip",
        "role": "core", "pipeline": "integrated when retrieved",
        "use": "Current-dollar GDP (CAGDP2) and real GDP in chained 2017 dollars (CAGDP9) for metros, states and the nation.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "qwi", "name": "Quarterly Workforce Indicators (QWI)",
        "publisher": "U.S. Census Bureau, LEHD program",
        "url": "https://lehd.ces.census.gov/data/",
        "access": "Census Data API: https://api.census.gov/data/timeseries/qwi/sa",
        "role": "additional", "pipeline": "integrated when retrieved",
        "use": "Hires, separations, firm job gains and losses, and stable-job earnings for private employers, summed from counties.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "acs", "name": "American Community Survey 1-year estimates (ACS)",
        "publisher": "U.S. Census Bureau",
        "url": "https://www.census.gov/programs-surveys/acs/data/data-tables.html",
        "access": "Census Data API: https://api.census.gov/data/{year}/acs/acs1",
        "role": "additional", "pipeline": "integrated when retrieved",
        "use": "Resident educational attainment, household income and working from home, with 90% margins of error.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "cpi", "name": "Consumer Price Index for All Urban Consumers (CPI-U), U.S. city average",
        "publisher": "U.S. Bureau of Labor Statistics",
        "url": "https://www.bls.gov/cpi/",
        "access": "https://download.bls.gov/pub/time.series/cu/cu.data.1.AllItems (series CUUR0000SA0, period M13)",
        "role": "additional", "pipeline": "integrated when retrieved",
        "use": "Deflator for inflation-adjusted wage comparisons (end-year dollars).",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "delineation", "name": "Core-based statistical area delineation file (July 2023)",
        "publisher": "U.S. Census Bureau / Office of Management and Budget",
        "url": "https://www.census.gov/programs-surveys/metro-micro/about/delineation-files.html",
        "access": "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx",
        "role": "core", "pipeline": "used to verify config/geography.json",
        "use": "Authoritative metro county membership.",
        "licence": "U.S. federal government work; public domain in the United States.",
    },
    {
        "id": "cluster_mapping", "name": "U.S. Cluster Mapping Project cluster definitions",
        "publisher": "Harvard Business School, Institute for Strategy and Competitiveness",
        "url": "https://www.clustermapping.us/",
        "access": "Manual download of the NAICS-to-cluster crosswalk into data/external/cluster_crosswalk.csv after checking its terms of use.",
        "role": "additional", "pipeline": "integrated only when a verified crosswalk file is supplied",
        "use": "Formal traded/local cluster classification (Delgado, Porter and Stern 2016). Without it the dashboard reports NAICS-sector specialization, not clusters.",
        "licence": "Not a federal work. Terms of use must be checked before redistributing the crosswalk or derived tables.",
    },
    {
        "id": "mcda", "name": "Michigan Center for Data and Analytics, labor market information",
        "publisher": "State of Michigan",
        "url": "https://www.michigan.gov/mcda/labor-market-information",
        "role": "local", "pipeline": "context only; not merged into the cross-metro comparison",
        "use": "Michigan industry and occupational projections.",
        "licence": "State publication; check terms before redistribution.",
    },
    {
        "id": "semcog", "name": "SEMCOG data portal",
        "publisher": "Southeast Michigan Council of Governments",
        "url": "https://data.semcog.org/",
        "role": "local", "pipeline": "context only; not merged into the cross-metro comparison",
        "use": "Southeast Michigan forecasts and planning data. Its seven-county region adds Monroe and Washtenaw and omits Lapeer, so it is not the Detroit MSA.",
        "licence": "Regional agency publication; check terms before redistribution.",
    },
    {
        "id": "cmap", "name": "CMAP Data Hub and regional economy analyses",
        "publisher": "Chicago Metropolitan Agency for Planning",
        "url": "https://datahub.cmap.illinois.gov/",
        "role": "local", "pipeline": "methodological cross-check only",
        "use": "CMAP cluster and job-quality analyses cover its seven-county northeastern Illinois region, which excludes the Indiana counties and DeKalb and Grundy.",
        "licence": "Regional agency publication; check terms before redistribution.",
    },
    {
        "id": "ohiolmi", "name": "Ohio Labor Market Information",
        "publisher": "Ohio Department of Job and Family Services",
        "url": "https://ohiolmi.com/",
        "role": "local", "pipeline": "context only; not merged into the cross-metro comparison",
        "use": "Ohio and Cleveland-area projections and occupational demand.",
        "licence": "State publication; check terms before redistribution.",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class RetrievalLog:
    """Append-only record of every download attempt, kept next to the raw data."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []

    def record(self, source: str, url: str, path: Path | None, status: str, detail: str = "") -> dict:
        entry = {
            "source": source, "url": url, "status": status, "detail": detail,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if path is not None and Path(path).exists():
            entry["file"] = str(path)
            entry["sha256"] = sha256(path)
            entry["bytes"] = Path(path).stat().st_size
        self.entries.append(entry)
        return entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=1))

    def latest(self, source: str) -> list[dict]:
        """Most recent entry per URL for one source."""
        by_url: dict[str, dict] = {}
        for e in self.entries:
            if e["source"] == source:
                by_url[e["url"]] = e
        return list(by_url.values())
