# Methodology

## 1. Scope

| Dimension | Choice | Reason |
|---|---|---|
| Regions | Detroit (CBSA 19820), Chicago (16980), Cleveland (17410), using 2023 OMB delineations | Three large Great Lakes metropolitan economies with manufacturing histories and different degrees of diversification |
| Benchmark | United States | Standard benchmark for location quotients and shift-share |
| Ownership | Private (QCEW `own_code` 5) for local and national values | Public-sector employment reflects how government is organized more than industrial specialization, and private ownership is the usual scope for LQ and shift-share comparisons |
| Industries | NAICS sectors (2-digit) and subsectors (3-digit), excluding 99 (unclassified) | Subsectors show specialization that sectors hide (for example, 336 Transportation equipment manufacturing within Manufacturing) |
| Employment | QCEW annual-average employment | Counts jobs at establishments covered by unemployment insurance (about 95% of U.S. jobs). It excludes most self-employed, proprietors, and some agricultural and railroad workers |

## 2. Geography

### Fixed county lists

Each metro is the **sum of a fixed county list** (`config/geography.json`) in every year. This keeps the geography constant over time:

- **Chicago:** before 2023 the CBSA was Chicago-Naperville-Elgin, IL-IN-WI and included Kenosha County, WI. Kenosha is excluded in every year.
- **Cleveland:** under the 2013–2020 delineations the CBSA was 17460 Cleveland-Elyria, OH and excluded Ashtabula County. OMB Bulletin 23-01 replaced it with 17410 Cleveland, OH, which adds Ashtabula. BLS publishes the metro as QCEW area C1746 through 2023 and C1741 from 2024 (`previous_qcew_areas` in `config/geography.json`). Ashtabula is included in every year.
- **Detroit:** the six-county definition is unchanged across these delineations.

Constant county lists answer the question "how did employment change in today's metro area?" They do not reproduce figures that BLS published under an earlier delineation.

### Safeguards

- `geography.check_internal_consistency` rejects malformed FIPS codes, counties outside a metro's states, and any county assigned to two metros.
- `scripts/verify_geography.py` compares every metro's county set, CBSA title and metropolitan status with the official delineation workbook. It records the result in `data/raw/delineation/verification.json`, which is carried into the manifest. **Until this has run, the manifest reports the geography as unverified.**
- A published metro total is **never added** to its own counties. Metro values come from county sums. BLS's published metro values are used only as a substitute for suppressed cells (see §3).
- City-proper data are never used.

## 3. QCEW aggregation and suppression

QCEW withholds cells that could reveal an individual employer (`disclosure_code = N`) and writes **0** in their value columns. The pipeline:

1. Replaces employment and wages in suppressed rows with **missing**, never zero. A suppressed row's establishment count is kept when it is positive, because BLS normally publishes establishment counts.
2. Treats an industry with **no row** in a county file as zero, because it has no establishments there. This applies only when that county's file for that year was loaded. A missing file makes the metro value missing.
3. Builds a metro cell as the **sum of its counties** when all of them are disclosed (`source = c`).
4. Otherwise uses the **BLS-published metro cell** (`source = m`), but only in years when the published metro *total* matches our county-sum total within 0.1%. A match shows that BLS's delineation for that year equals our county list.
5. Otherwise reports the cell as **suppressed** (`source = s`). No imputation is done.

Every cell carries its source code into `annual.json`, and the dashboard shows it.

## 4. Measures

### Employment share

`share_{i,r,t} = E_{i,r,t} / E_{r,t}`, where `E_{r,t}` is total private employment, including unclassified.

### Location quotient

```
LQ_{i,r,t} = (E_{i,r,t} / E_{r,t}) / (E_{i,US,t} / E_{US,t})
```

All four terms are private ownership in the same year. LQ > 1 means a higher local concentration than the nation. LQ = 1 means the same concentration, and LQ < 1 means a lower one. An LQ describes relative concentration only. It is not evidence of productivity, profitability, competitiveness, resilience or causation. The LQ is undefined (missing) when any term is missing or a denominator is zero.

**Difference from BLS-published LQs.** The `lq_` columns in QCEW files divide an industry's private employment by *all-ownership* total employment, locally and nationally. Here both denominators are private. The two definitions differ by the factor (local private share of all jobs) ÷ (U.S. private share of all jobs). With BLS's base, this pipeline reproduces BLS's 2024 values to the published two decimals (see the QA report, section 7).

### Employment growth

For a start year `s` and an end year `e`:

- absolute change `E_e − E_s`, reported whenever both values exist
- percentage change `(E_e − E_s) / E_s`, reported **only when `E_s > 0`**

Absolute job change and percentage growth are shown separately. A small industry can post a large percentage change with few jobs.

### Shift-share

For each industry and metro, with growth rates `g` from the same years and ownership:

```
National growth   NS = E_s × g_US
Industry mix      IM = E_s × (g_{i,US} − g_US)
Regional effect   RC = E_s × (g_{i,r} − g_{i,US})
NS + IM + RC = E_e − E_s
```

`g_US` is total U.S. private employment growth. Components are **not** calculated when:

- local base or end employment is missing or suppressed (`missing_local`)
- local base employment is zero (`zero_base`): growth rates are undefined, and only the observed change is shown
- U.S. values are missing (`missing_national`)
- the industry's NAICS definition changed between the two years (`not_comparable`, see §5)

Each decomposition is checked to reconcile with the observed change, with a relative residual of at most 1×10⁻⁶ of base employment before rounding. Failures are reported as `reconciliation_failed` and are counted in the manifest's validation section. They are never hidden.

Metro-level totals sum the sector-level components over sectors with complete data and report the **coverage**: the share of base-year metro employment in those sectors.

The regional effect measures **relative employment growth** within an industry. It does not show that local policy, productivity, costs or any other factor caused the difference.

### Wages

The average weekly wage is total annual wages / annual-average employment / 52. Wages are **nominal** unless they are labelled as inflation-adjusted. Adjusted wages use the CPI-U U.S. city average annual index (series CUUR0000SA0) and are expressed in dollars of the latest QCEW year. A single national price index does not capture differences in living costs between metros. An average wage is a mean per job, including part-time jobs, and is not the earnings of a typical worker.

## 5. NAICS revisions

QCEW publishes each year under the NAICS edition in force at the time: 2012 for 2012–2016, 2017 for 2017–2021 and 2022 from 2022 onward. It does not reconvert earlier years. Sector definitions are stable across these editions. NAICS 2022 restructured **Retail trade (44-45)** and **Information (51)** at the 3-digit level. Subsectors in those two sectors are therefore marked `not_comparable` for any period that spans 2021→2022. Other subsectors are compared across editions. The changes outside 44-45 and 51 are at the 5- and 6-digit level, but this should be rechecked against BLS's NAICS 2022 notes when the data are refreshed.

## 6. Context sources

| Source | What is used | How it is combined |
|---|---|---|
| CBP | Establishments by size band (1–19, 20–99, 100–499, 500+ employees), employment, annual payroll | Summed from our county list. Since 2017 CBP uses noise infusion rather than withholding; `EMP_N`/`PAYANN_N` are noise ranges (all `0` in the files used). Any value flagged D (withheld) or S (below standard) would be missing. Establishment counts are never withheld. Size classes: 210 (<5), 220, 230; 241, 242; 251, 252; 254, 260 (1,000+; its 2022+ sub-classes are not added again). Size bands can sum to slightly less than the all-sizes count |
| BEA CAGDP2/CAGDP9 | All-industry GDP, current dollars and chained 2017 dollars | Current-dollar GDP is summed from our counties. Chained dollars are not additive, so metro real GDP could only come from a BEA metro row. BEA's current county files, and its API's CAGDP2/CAGDP9 tables, contain no metro rows, so metro real GDP is not shown (`real_gdp_status: metro_not_in_file`). Real GDP is shown for states and the U.S. |
| ACS 1-year | Bachelor's degree or higher (25+), median household income, working from home, each with a 90% MOE | CBSA and state rows straight from the API. Derived proportions use Census MOE formulas. Comparisons are tested at the 90% level |
| QWI | Hires, separations, firm job gains and losses (as rates per beginning-of-quarter job), stable-job monthly earnings | Summed from counties across all four quarters. Any county-quarter whose status flag is not `1` (fully published) makes the year missing; the files used contain only `1` and `-1` (value not computable, null). The dashboard compares the latest year complete for all three metros |
| CPI-U | Annual average index | Wage deflator only |

**Residents versus jobs.** ACS describes people who *live* in an area, wherever they work. QCEW, CBP and QWI describe jobs at establishments *located* in the area. The pipeline never divides one by the other.

**Output per job.** The pipeline does not compute GDP per job. BEA GDP covers all industries and all ownerships, while QCEW employment here is private and covered jobs. Dividing one by the other would produce a ratio with mismatched numerator and denominator.

## 7. Formal clusters

Formal clusters require the U.S. Cluster Mapping Project's NAICS-to-cluster crosswalk (Delgado, Porter and Stern 2016), which defines clusters on NAICS 2012 6-digit industries. The crosswalk is not bundled. `clusters.py` validates and aggregates it when it is supplied. Aggregation is enabled only for QCEW years whose NAICS edition matches the crosswalk, and a cluster value is reported only when every member industry is disclosed. **Until then, every result is labelled NAICS sector or subsector specialization, not clusters.** The dashboard's quadrant view (specialized/growing and so on) applies to NAICS industries.

## 8. Findings

`findings.py` produces each finding from a named rule with explicit thresholds (minimum 1,000 jobs; distinctive means Detroit LQ ≥ 1.25 while both comparison metros are below 1; shared means LQ ≥ 1.10 in all three metros; and so on). The output records the rule text and the evidence values. When no industry meets a rule, the finding says so. Findings about regional effects whose sign differs are labelled **hypotheses for investigation**, not explanations.

## 9. Validation (recorded in every manifest)

- no duplicate area/industry/level/year rows
- suppressed or missing cells carry no employment value
- every area-year has total private employment
- sector employment never exceeds the total, and the unclassified gap is at most 2%
- LQ values are in a plausible range, and the U.S. benchmark LQ is exactly 1
- every shift-share decomposition reconciles within tolerance
- no growth rate is computed from a zero or missing base
- the number of cells withheld because of NAICS revisions is reported
- the source inventory is reported in full, with a reason for every source that was not retrieved or not integrated
