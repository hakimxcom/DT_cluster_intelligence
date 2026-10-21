# Cluster dashboard QA report

Date: 21 October 2026. Pipeline commit: `c0ed4d6` (this repository). Website branch: `claude/elegant-lamport-6du6qw` in `hakimxcom/hakimxcom`.

## Summary

| Area | State |
|---|---|
| Pipeline code (acquisition, aggregation, LQ, growth, shift-share, context sources, findings, validation, handoff) | Complete and unit-tested |
| Official source data | **Not yet retrieved.** The development container's network policy blocked every BLS, Census, BEA, LEHD and regional host (HTTP 403 at the egress proxy) |
| Dataset published to the website | `2026.10.21+c0ed4d6`, status **`no_data`**. It contains the source registry, geography and reasons only, with no figures |
| Dashboard | Built, integrated into the X Lab, and browser-tested with both the real (empty) dataset and a synthetic test dataset |
| Geography verification against the official delineation file | **Not run** (file not downloadable here). County lists were compiled from the 2023 delineation and cross-checked against secondary references |

Nothing in this report claims an economic finding. The first findings will come from the first build on official data.

## 1. Sources integrated

None with official data yet. Every adapter below is implemented, parses the documented file format, and is exercised by tests on synthetic inputs:

| Source | Adapter | Verified against live endpoint? |
|---|---|---|
| BLS QCEW area slices | `qcew.py` | No (host blocked) |
| Census CBP API | `cbp.py` | No |
| BEA CAGDP2 / CAGDP9 zips | `bea.py` | No |
| Census ACS 1-year API | `acs.py` | No |
| Census QWI API | `qwi.py` | No |
| BLS CPI-U flat file | `prices.py` | No |
| Census delineation workbook | `geography.py` | No |

**Because the adapters have not seen a real response, the first real run may surface format differences.** These include API variable names, the QWI status-flag semantics, and the CBP noise-flag codes. Every parser validates its columns and fails loudly instead of guessing. The points most worth confirming on the first run:

- QWI: the API's echo of `year`/`quarter` columns, and whether status flags other than `1` should be accepted.
- CBP: the `EMP_N`/`PAYANN_N` flag codes treated as withheld (`D`, `S`), and the NAICS variable name by year (`NAICS2017` through 2022, `NAICS2022` from 2023).
- QCEW: whether establishment counts are populated on suppressed rows. The code keeps them only when they are positive.

## 2. Sources investigated but not integrated

| Source | Reason |
|---|---|
| Harvard U.S. Cluster Mapping Project | Crosswalk not bundled: it is not a federal work, its terms must be checked, and its NAICS 2012 definitions need bridging for QCEW 2022+ data. The dashboard says that formal clusters are not shown and labels its quadrants as NAICS industries |
| Michigan Center for Data and Analytics | State-specific projections with no equivalent on the same basis for IL/IN/OH. Context only |
| SEMCOG | Seven-county region (adds Monroe and Washtenaw, omits Lapeer) is not the Detroit MSA |
| CMAP | Seven-county northeastern Illinois region excludes DeKalb, Grundy and the Indiana counties. Useful as a methodological cross-check |
| Ohio LMI | Ohio-specific projections. Not comparable across states |

All of these hosts were also unreachable from the development container.

## 3. Geography and county coverage

| Metro | CBSA | Counties (count) |
|---|---|---|
| Detroit-Warren-Dearborn, MI | 19820 | Lapeer, Livingston, Macomb, Oakland, St. Clair, Wayne (6) |
| Chicago-Naperville-Elgin, IL-IN | 16980 | Cook, DeKalb, DuPage, Grundy, Kane, Kendall, Lake IL, McHenry, Will; Jasper, Lake IN, Newton, Porter (13) |
| Cleveland, OH | 17460 | Ashtabula, Cuyahoga, Geauga, Lake, Lorain, Medina (6) |

Kenosha County, WI is excluded from Chicago, and Ashtabula County is included in Cleveland, for every year. Each build records per year whether BLS's published metro total matches this county set. Published metro cells substitute for suppressed county cells only in matching years. `scripts/verify_geography.py` must be run once the delineation file can be downloaded. The test `test_config_matches_official_delineation_file` is skipped until then.

## 4. Year coverage

No official years are loaded. On the first run, `fetch_sources.py` detects the latest QCEW annual file and fetches from 2014 (configurable). It fetches the newest available CBP and ACS years, BEA's full series, and the five most recent years of QWI. The manifest's `coverage` section and the dashboard's coverage table report the years actually used for each source.

## 5. Calculations and validations

Implemented and tested: employment share, location quotient, absolute and percentage growth (with no percentage from a zero base), three-component shift-share with reconciliation, county-to-metro aggregation with suppression rules, NAICS 2022 subsector comparability, CPI deflation, ACS MOE for sums and proportions, ACS significance testing, CBP size-band aggregation, QWI annual rates, BEA delineation check, and rule-based findings.

Validation checks recorded in every manifest: no duplicate rows; suppressed cells carry no values; totals present; sectors within totals; unclassified gap ≤ 2%; LQ plausible; U.S. LQ = 1; shift-share reconciliation (tolerance 1×10⁻⁶ relative); no growth rate from a zero base; NAICS-revision cells counted.

## 6. Tests run and results

### Research repository — `pytest` (Python 3.13.16, pandas 3.0.6)

Result: **65 passed, 1 skipped** (the skip is the official-delineation test, because the file is absent).

| File | Covers |
|---|---|
| `test_geography.py` (7) | County counts; Chicago spans IL and IN and excludes Kenosha; no double assignment; foreign-state rejection; delineation verification passes on a matching workbook and reports missing/extra counties; official file check (skipped) |
| `test_location_quotients.py` (18) | LQ manual examples (2.5, 1.0, 1/3); missing or zero denominators; growth that is positive, negative, from a zero base, or missing |
| `test_shift_share.py` (7) | Manual decomposition (20/30/100); declining industry; zero base; missing local or national values; 1,000 random reconciliations |
| `test_qcew.py` (10) | Suppressed rows become missing, not zero; ownership and level filtering; duplicate and column checks; county sum versus published-metro fallback versus suppressed; a missing county file never counts as zero; a metro total is not added to its counties |
| `test_sources_parsers.py` (10) | Source inventory complete; ACS MOE formulas and sentinel handling; CBP withheld flags and size-label checks; CBP county completeness; QWI flags; CPI and deflation; NAICS comparability; QCEW trim |
| `test_data_validation.py` (14) | End-to-end build on the synthetic fixture: every check passes; every source reported with a status and reason; suppression outcomes; identical industries and years across geographies; zero base and NAICS break; rounded components reconcile within ±2; LQ equals a manual calculation; units and periods declared; findings generated; the handoff copies exact files, rejects tampered, failed, synthetic or wrong-repository inputs; an empty raw directory reports `no_data` honestly |

### Live acquisition attempt

`python scripts/fetch_sources.py --only delineation,bea,cpi` was run from the container. All four URLs failed with `ProxyError: connection refused by the network proxy (403)`. The failures are recorded in the retrieval log and appear in the manifest's source registry.

### Website — see `docs/CLUSTER_DASHBOARD_INTEGRATION.md` in the website repository

Result: **74/74 browser checks passed** (Playwright 1.56, Chromium, against a local `http-server` of `public/`).

## 7. Known limitations and open issues

1. **No official data has been processed.** This is the main open item.
2. The county lists have not been machine-verified against the official delineation file.
3. The source adapters have not been exercised against live responses (see §1).
4. Formal clusters are not available until a verified crosswalk is supplied and bridged to NAICS 2022.
5. The NAICS 2022 comparability rule withholds Retail trade and Information subsectors across 2021→2022. Other 3-digit changes, if any, should be confirmed against BLS notes.
6. Real wages use the national CPI-U, which does not reflect local price levels.
7. QCEW excludes most self-employment. ACS figures are resident-based and are never combined with job counts.
8. Licence: the repository carries the MIT licence it was created with. The owner should confirm that this is intended.

## 8. Refreshing the data and regenerating the website dataset

```bash
pip install -e ".[dev]"
python scripts/fetch_sources.py --contact you@example.com    # needs normal internet access
python scripts/verify_geography.py                           # must print "verified"
python scripts/build_dataset.py                              # exits 1 on any failed check
pytest                                                       # the delineation test now runs too
python scripts/export_to_website.py --website ../hakimxcom   # checksum-verified copy
```

Then, in the website repository, review `public/data/cluster-dashboard/manifest.json`, run the browser tests (see that repository's integration report), update the X Lab card's `DATA` row from "FIRST OFFICIAL RUN PENDING" to the actual period, and commit on a branch. Nothing here deploys the website.
