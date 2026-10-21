# Cluster dashboard QA report

Date: 21 October 2026. Dataset `2026.10.21+e811e89` (pipeline commit `e811e89`), status **complete**. Website branch: `claude/elegant-lamport-6du6qw` in `hakimxcom/hakimxcom`.

## Summary

| Area | State |
|---|---|
| Official source data | Retrieved 21 October 2026 from BLS, Census and BEA (section 1) |
| Geography | **Verified** against the official delineation file `list1_2023.xlsx` (sha256 `952c4b1e…3629`). Cleveland's CBSA code corrected from 17460 to 17410 (section 3) |
| Validation | All 10 checks pass (section 5) |
| Tests | `pytest`: 74 passed, 0 skipped. Browser: 86/86 (section 6) |
| Dataset on the website | `2026.10.21+e811e89`, exported with checksum verification |

## 1. Sources retrieved and verified

Counts are from `data/raw/retrieval_log.json`, taking the latest attempt for each URL. "Superseded" failures are requests that were later replaced by a corrected or keyed request. They stay in the log as provenance.

| Source | Files used | Not yet published | Superseded failures | Years used |
|---|---|---|---|---|
| QCEW area slices (`data.bls.gov`) | 385 | 2026 (latest-year probe) | 2: `C1746` for 2024 and 2025, replaced by `C1741` | 2014–2025 |
| CBP (Census Data API) | 12 (2017, 2022, 2023 × 4 states) | 2024, 2025 (404) | 5: 2023 requested as `NAICS2022` (400), and 2018–2021 from the first run without a key, which were not needed again | 2023 shown |
| BEA CAGDP2, CAGDP9 zips | 2 | — | — | 2001–2024 |
| ACS 1-year (Census Data API) | 2 (2024 metro, 2024 state) | 2025 (404) | 5: 2019–2023 from the first run without a key; 2024 suffices | 2024 |
| QWI (Census Data API) | 128 | Michigan 2022 Q1–2025 Q4 (HTTP 204, 16 requests) | — | 2017–2024 (Detroit 2017–2020) |
| CPI-U flat file (`download.bls.gov`) | 1 | — | First attempt: 403 without an email contact | base year 2025 |
| Delineation file (`www2.census.gov`) | 1 | — | — | July 2023 |

Access requirements found on this run: the Census Data API now refuses requests without a key (redirect to `missing_key.html`), and `download.bls.gov` refuses a User-Agent without an email address. The fetcher previously followed the Census redirect and would have saved the HTML error page as data; it now records the redirect as a failure.

### What each adapter was checked against

Each check used a real raw file. Small excerpts of those files are in `tests/fixtures/real_excerpts/` and are tested in `tests/test_real_formats.py`.

| Source | Assumption | Found in the real file | Change |
|---|---|---|---|
| QCEW | Columns `area_fips, own_code, industry_code, agglvl_code, year, qtr, disclosure_code, annual_avg_estabs, annual_avg_emplvl, total_annual_wages` | Present (38 columns, including `lq_*` and `oty_*`). `qtr` is `A`. 2025 files quote every field | None |
| QCEW | Disclosure codes | Only `""` (disclosed) and `N` (suppressed): 32,469 and 7,062 rows | None |
| QCEW | Establishments on suppressed rows | Published on 7,001 of 7,062 suppressed rows; employment and wages are written as 0 on all of them. The 61 suppressed rows with 0 establishments are kept missing | None |
| QCEW | Metro area codes | Cleveland is `C1746` through 2023 and `C1741` from 2024. 2025 metro files contain only the all-ownership total (agglvl 40), so 2025 metro values come from county sums only | Per-year QCEW metro code |
| CBP | NAICS variable `NAICS2017` to 2022, `NAICS2022` from 2023 | **Wrong.** The API names it `NAICS2017` in 2017–2023, and 2023 still uses 2017 codes (452, 454 and 511 exist; 455, 459 and 513 do not). The 2023 request failed with "unknown variable 'NAICS2022'" | `naics_var` returns `NAICS2017` through 2023; the parser accepts exactly one NAICS column |
| CBP | Size class 212 = "less than 5 employees" | **Wrong.** It is 210 (212 is "1 to 4"). The 1–19 band was missing its largest class | Size code 210 |
| CBP | `EMP_N`/`PAYANN_N` flags `D`, `S` mean withheld | API metadata: these are *noise ranges*. Every value in 2017, 2022 and 2023 is `0`; no cell is withheld. `EMP = 0` with payroll > 0 occurs (no employees in the March 12 pay period) and is a reported value | Documentation; `D`/`S` still treated as missing if they appear |
| CBP | Size bands add up to the all-sizes count | Not always: Lapeer County 2022 has 1,771 establishments, but its size classes sum to 1,769. From 2022 the API adds sub-classes 262–273 of class 260; they are not added again | Test pins this; bands are never forced to reconcile |
| BEA | One `*ALL_AREAS*.csv` per zip | `CAGDP2__ALL_AREAS_2001_2024.csv`, `CAGDP9__ALL_AREAS_2001_2024.csv` (release of 5 February 2026) | None |
| BEA | `GeoFIPS` format | Quoted with a leading space (` "26163"`); four footer lines with no `LineCode` are dropped | None |
| BEA | Metro rows present for real GDP | **Wrong.** The county zips contain the nation, states, regions and counties only. BEA's download list has no metro GDP zip, and the BEA API's `CAGDP2`/`CAGDP9` GeoFips list (checked with a key) has no metro codes either. Metro tables exist only for price parities and deflators (`MARPP`, `MAIRPD`) | Metro real GDP reported unavailable (`real_gdp_status: metro_not_in_file`) instead of the previous, false "delineation differs". Nominal metro GDP stays as the county sum. The dashboard now says so |
| ACS | Variable codes `B15003_001/022–025`, `B19013_001`, `B08301_001/021`, each `E` and `M` | All present; geography code is the last column. Cleveland was missing only because 17460 was requested | None (geography fix) |
| QWI | `year` and `quarter` echoed | Yes, along with `ownercode`, `state`, `county` | None |
| QWI | Status flags | Only `1` (published) and `-1` appear; every `-1` comes with a null value. The edge quarter (e.g. 2025 Q4, and Michigan 2021 Q4) has `-1` for measures that need the next quarter, so that year is not complete | Fetch option `--qwi-start`; coverage lists only complete years per metro; dashboard compares the latest common year |
| CPI | `CUUR0000SA0`, period `M13` | Present for every year through 2025 (2025 = 321.943). CRLF line endings and space-padded series IDs are handled | None |

## 2. Sources investigated but not integrated

| Source | Reason |
|---|---|
| Harvard U.S. Cluster Mapping Project | Crosswalk not bundled: not a federal work, its terms must be checked, and its NAICS 2012 definitions need bridging for QCEW 2022+ data. The dashboard says formal clusters are not shown |
| BEA metro real GDP | Not published by BEA in its download files or API (section 1). Chained-dollar county values are not additive, so no substitute is computed |
| Michigan Center for Data and Analytics | State-specific projections with no equivalent for IL/IN/OH. Context only |
| SEMCOG | Seven-county region (adds Monroe and Washtenaw, omits Lapeer) is not the Detroit MSA |
| CMAP | Seven-county region excludes DeKalb, Grundy and the Indiana counties. Methodological cross-check only |
| Ohio LMI | Ohio-specific projections, not comparable across states |

## 3. Geography and county coverage

`scripts/verify_geography.py` first reported `cleveland: CBSA 17460 not found in delineation file`. The official file lists:

| CBSA | Official title | Counties (FIPS) |
|---|---|---|
| 19820 | Detroit-Warren-Dearborn, MI | Lapeer 26087, Livingston 26093, Macomb 26099, Oakland 26125, St. Clair 26147, Wayne 26163 |
| 16980 | Chicago-Naperville-Elgin, IL-IN | Cook 17031, DeKalb 17037, DuPage 17043, Grundy 17063, Kane 17089, Kendall 17093, Lake 17097, McHenry 17111, Will 17197; Jasper 18073, Lake 18089, Newton 18111, Porter 18127 |
| 17410 | Cleveland, OH | Ashtabula 39007, Cuyahoga 39035, Geauga 39055, Lake 39085, Lorain 39093, Medina 39103 |

17460 was the former Cleveland-Elyria CBSA, which excluded Ashtabula. The only edits to `config/geography.json` were Cleveland's `cbsa_code` (17460 → 17410), its `qcew_area` (`C1746` → `C1741`), and a `previous_qcew_areas` entry for `C1746` through 2023. No county changed. The check now prints `verified`, and `test_config_matches_official_delineation_file` runs and passes.

BLS's published metro total matches our county set in these years: Detroit 2014–2024; Chicago 2024 only (before 2024 BLS's C1698 included Kenosha County, WI); Cleveland 2024 only (C1746 excluded Ashtabula). In 2025 no private metro total is published. Published metro cells stand in for suppressed county cells only in matching years.

## 4. Year coverage

| Source | Years in this dataset |
|---|---|
| QCEW (employment, establishments, wages, LQ, shift-share) | 2014–2025 annual averages |
| CBP | 2023 shown (2017 and 2022 also loaded) |
| BEA GDP | 2001–2024: nominal for metros (county sums), states and the U.S.; real for states and the U.S. |
| ACS 1-year | 2024 |
| QWI | Chicago and Cleveland 2017–2024; Detroit 2017–2020. The dashboard shows 2020, the latest year common to all three |
| CPI-U | Annual averages through 2025; real wages in 2025 dollars |
| NAICS editions | 2012 (2014–2016), 2017 (2017–2021), 2022 (2022–2025) |

## 5. Calculations and validations

`python scripts/build_dataset.py` (exit 0):

| Check | Result |
|---|---|
| no_duplicate_area_industry_year | pass: 0 duplicate rows |
| suppressed_not_zero | pass: 1,972 suppressed/missing metro cells; 0 carry an employment value |
| totals_present | pass: 0 area-years without total private employment |
| sectors_within_total | pass: largest unclassified gap 0.40% |
| unclassified_gap_small | pass: 0.40% (limit 2%) |
| lq_plausible | pass: LQ range 0.000–5.079 |
| us_lq_equals_one | pass |
| shift_share_reconciles | pass: 0 failed decompositions; largest relative residual 9.47×10⁻¹⁶ |
| no_pct_from_zero_base | pass |
| naics_revision_flagged | pass: 2,496 industry-period cells withheld because NAICS definitions changed |

**NAICS comparability.** The rule (Retail 44-45 and Information 51 subsectors are not compared across 2021→2022) was checked against BLS's QCEW revision tables (`data.bls.gov/cew/apps/bls_naics/naics2022.zip`, sheet "NAICS Comparison Table"). Of the 232 NAICS 2017→2022 code mappings, the 145 that cross a 3-digit boundary are all inside 44-45 (125) or 51 (20), and none crosses a sector. Because the series starts in 2014, the 2012→2017 table (`naics2017.zip`) was checked as well: none of its 32 mappings crosses a 3-digit boundary. No change to the rule.

## 6. Tests

**Research repository:** `pytest`, 74 passed and 0 skipped (Python 3.13.16). New since the previous report:
- `test_real_formats.py` (7 tests on real excerpts)
- a test that the required notices and citations are present
- `test_config_matches_official_delineation_file`, which now runs instead of skipping

The synthetic fixture now follows the real CBP size codes and BEA layout (no metro rows), and Cleveland's 2024 code change; it runs 2019–2024.

**Website:** `tests/cluster-dashboard.ui.mjs`, 86/86 checks (Playwright 1.56.1, Chromium, local `http-server` of `public/`). Section A now tests the committed official dataset. Its expectations are read from the manifest:
- status, version and period
- verified geography
- six integrated sources
- the Census notice and the citations
- the CBP and ACS reference years
- the explanation of missing metro real GDP
- the common QWI year
- that findings render with no JS errors

Sections B–D exercise every control on the synthetic fixture.

## 7. Comparison with published BLS figures

**Total private employment, our county sum against BLS's published metro row (agglvl 41).**

| Metro | 2023 | 2024 | 2025 |
|---|---|---|---|
| Detroit (C1982) | 1,735,419 vs 1,735,419 (0) | 1,730,209 vs 1,730,208 (+1) | 1,716,672; no private metro row published |
| Chicago (C1698) | 3,935,066 vs 3,999,374 (−64,308, −1.61%: BLS still included Kenosha) | 3,931,488 vs 3,931,489 (−1) | 3,960,779; not published |
| Cleveland (C1746, then C1741) | 897,360 vs 871,729 (+25,631, +2.94%: C1746 excluded Ashtabula) | 899,335 vs 899,334 (+1) | 889,156; not published |

The ±1 differences in 2024 are consistent with BLS rounding each published annual average, though that has not been confirmed.

**Location quotients against BLS's `lq_annual_avg_emplvl`, 2024.**

| Metro, industry | Ours | BLS | Ours recomputed on BLS's base |
|---|---|---|---|
| Detroit, Manufacturing (31-33) | 1.463 | 1.55 | 1.546 |
| Chicago, Finance and insurance (52) | 1.177 | 1.22 | 1.216 |
| Cleveland, Health care and social assistance (62) | 1.194 | 1.22 | 1.218 |
| Detroit, Transportation equipment (336) | 4.834 | 5.11 | 5.108 |

Employment numerators match BLS exactly (to within 1 job). The difference is the denominator. BLS divides by total employment in **all ownerships**, government included, locally and nationally. This pipeline uses private totals, as `docs/methodology.md` specifies. Recomputed on BLS's base, all four values round to BLS's published figures. The dashboard's methodology section states this difference.

## 8. Citation and terms of use

- **BLS** asks to be cited as the source.
- **Census Data API** terms require the notice *"This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."* It is stored in the manifest's `notices` and shown prominently in the dashboard's methodology section.
- **BEA** data come from its download files, so the BEA API notice does not apply. Metro GDP is labelled as this project's sum of BEA county estimates.

Every non-local source in the manifest carries a `citation`, which the dashboard shows. API keys are read from environment variables and are not stored anywhere in either repository. See `docs/data_sources.md`.

## 9. Known limitations and open issues

1. Metro real GDP is not available from BEA (section 1).
2. QWI for Detroit ends in 2020, because Michigan is not published after 2021 Q4.
3. In 2025, and in Chicago and Cleveland before 2024, suppressed county cells cannot be filled from BLS's published metro cells, so those metros have fewer industries with values in those years. For example, the dashboard shows 3 Chicago sectors with an LQ in 2025. For the same reason the 2014–2025 Chicago shift-share sum covers 27% of base-year employment, which the finding itself reports.
4. Formal clusters are not available until a verified crosswalk is supplied and bridged to NAICS 2022.
5. LQs use a private-employment base and differ from BLS's published LQs (section 7).
6. Real wages use the national CPI-U, which does not reflect local price levels.
7. QCEW excludes most self-employment. ACS figures are resident-based and are never combined with job counts.
8. Licence: the repository carries the MIT licence it was created with. The owner should confirm that this is intended.

## 10. Refreshing the data

```bash
pip install -e ".[dev]"
export CENSUS_API_KEY=...                                    # required by the Census Data API
python scripts/fetch_sources.py --contact you@example.com --qwi-start 2017   # --contact must be an email
python scripts/verify_geography.py                           # must print "verified"
python scripts/build_dataset.py                              # exits 1 on any failed check
pytest
python scripts/export_to_website.py --website ../hakimxcom   # checksum-verified copy
```

Then, in the website repository, run the browser tests (see `docs/CLUSTER_DASHBOARD_INTEGRATION.md`), update the X Lab card's `DATA` row and note to the new period and version, and commit on a branch. Nothing here deploys the website.
