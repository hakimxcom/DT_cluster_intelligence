# Great Lakes Cluster Intelligence (DT_cluster_intelligence)

Regional economic intelligence comparing Detroit, Chicago, and Cleveland through industry clusters, employment, wages, and economic indicators.

This repository is the **research engine** behind the *Regional Industry & Cluster Intelligence* dashboard on [hakimx.com](https://hakimx.com). It acquires official source data, aggregates it to fixed metropolitan geographies, calculates location quotients, employment growth and shift-share decompositions, validates the results, and produces the compact, checksummed JSON files that the website renders. The website lives in a separate repository, [`hakimxcom/hakimxcom`](https://github.com/hakimxcom/hakimxcom), and contains no analytical code beyond display.

> **Data status:** the pipeline and its tests are complete. This repository does **not yet contain official data**. The build environment it was developed in could not reach BLS, Census or BEA servers, so no official data has been processed and no findings have been published. Run the steps under [Refreshing the data](#refreshing-the-data) on a machine with normal internet access to produce the first real dataset.

## What it compares

| Region | Official CBSA (OMB Bulletin 23-01, July 2023) | Counties |
|---|---|---|
| Metro Detroit | 19820 Detroit-Warren-Dearborn, MI | Lapeer, Livingston, Macomb, Oakland, St. Clair, Wayne |
| Metro Chicago | 16980 Chicago-Naperville-Elgin, IL-IN | Cook, DeKalb, DuPage, Grundy, Kane, Kendall, Lake (IL), McHenry, Will; Jasper, Lake (IN), Newton, Porter |
| Greater Cleveland | 17460 Cleveland, OH | Ashtabula, Cuyahoga, Geauga, Lake, Lorain, Medina |

These county lists are in [`config/geography.json`](config/geography.json). They were compiled from the 2023 delineation and cross-checked against secondary references. They have **not yet been machine-verified** against the official Census delineation workbook, because that file could not be downloaded in the development environment. `scripts/verify_geography.py` performs that check and fails on any difference. Every build records the verification result in its manifest.

A separate **state context** compares Michigan, Illinois and Ohio. Metro Chicago includes four Indiana counties, so the state panel and the metro panels describe different geographic units.

## Setup

Requires Python 3.11 or later.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Tests

```bash
pytest
```

The tests are self-contained and need no network access. The end-to-end tests run the full build on a **synthetic** fixture (`tests/fixtures/synthetic_raw.py`). Its numbers are invented to exercise the code paths and are never exported. One test checks the official delineation file and is skipped until that file has been downloaded.

## Refreshing the data

```bash
# 1. Download raw files (about 400 requests; logged to data/raw/retrieval_log.json)
python scripts/fetch_sources.py --contact you@example.com
#    optional: export CENSUS_API_KEY=... first; add --trim-qcew to keep only the rows used

# 2. Verify the metro county lists against the official delineation file
python scripts/verify_geography.py

# 3. Build and validate (exits 1 if any validation check fails)
python scripts/build_dataset.py

# 4. Hand the validated files to the website repository
python scripts/export_to_website.py --website ../hakimxcom
```

Step 4 refuses to run if the manifest is missing, if any file's checksum differs from the manifest, or if validation failed. It replaces `public/data/cluster-dashboard/` in the website repository and re-verifies the copied files. Commit the result in the website repository on a branch. Nothing in this repository deploys the website.

### Handing downloaded data to another machine

If the data is downloaded on one computer and the build runs elsewhere (for example in a sandbox without access to government sites), run step 1 with `--trim-qcew`. This keeps only the QCEW rows the pipeline reads, and the original checksums are kept in the retrieval log. Then send the whole `data/raw/` folder, including `retrieval_log.json`, as a zip file or on a throwaway branch:

```bash
git switch -c raw-data-drop
git add -f data/raw
git commit -m "Raw source files for the first build"
git push -u origin raw-data-drop
```

Raw files are excluded from the main branch on purpose. Delete the throwaway branch after the build.

When BLS publishes a new QCEW annual release (normally in September), rerun steps 1–4. Existing raw files are kept unless you pass `--refresh`.

## Outputs

| Path | Contents |
|---|---|
| `data/processed/website/manifest.json` | Dataset version, generation time, pipeline commit, geography and its verification status, source inventory with per-build status, year coverage, units, validation results, and SHA-256 checksums of every file |
| `data/processed/website/annual.json` | Employment, establishments, average weekly wage (nominal and CPI-adjusted), employment share and location quotient by metro, industry and year, plus a source code for every cell |
| `data/processed/website/pairs/{start}-{end}.json` | Growth and shift-share components for every start/end year pair |
| `data/processed/website/context.json` | CBP, BEA, ACS, QWI and state-level QCEW context |
| `data/processed/website/findings.json` | Rule-based findings with the rule text and the evidence behind each one |
| `data/processed/website/clusters.json` | Formal cluster results, or the reason they are unavailable |
| `data/processed/*.csv` | Full tidy tables for analysis |

## Repository layout

```
config/geography.json        metro, county and state definitions
scripts/                     fetch, verify, build and export commands
src/cluster_intelligence/
  geography.py               geography loading and delineation verification
  qcew.py                    QCEW parsing, suppression handling, county-to-metro aggregation
  metrics.py                 employment share, location quotient, growth
  shift_share.py             three-component shift-share with reconciliation
  naics.py                   sector titles and NAICS revision comparability
  cbp.py bea.py acs.py qwi.py prices.py   context sources
  clusters.py                cluster aggregation from a verified crosswalk
  findings.py                rule-based findings
  validation.py              data-quality checks recorded in the manifest
  build.py                   orchestration and output
  handoff.py                 checksum-verified export to the website
tests/                       unit and end-to-end tests
docs/                        methodology, source inventory, QA report
```

## Documentation

- [Methodology](docs/methodology.md)
- [Data sources](docs/data_sources.md)
- [QA report](docs/CLUSTER_DASHBOARD_QA.md)

## Licence

The repository already carried an MIT licence when this pipeline was added, and it has been left unchanged. It covers the code in this repository. The source data are U.S. federal works, apart from the optional Harvard cluster crosswalk, which has its own terms and is not bundled. Please confirm that MIT is the licence you intend.
