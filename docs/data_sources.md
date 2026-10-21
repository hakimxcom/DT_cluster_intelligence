# Data source inventory

Each build decides a source's status from the files actually present and the retrieval log, and records it in `manifest.json`: **integrated**, **not_retrieved** (with the last error) or **not_integrated** (with a reason). The table below describes intended use. It does not claim that any source has been processed.

## Core sources

| Source | Publisher | Access used by the pipeline | Use | Expected latest period* |
|---|---|---|---|---|
| [QCEW](https://www.bls.gov/cew/downloadable-data-files.htm) | BLS | `https://data.bls.gov/cew/data/api/{year}/a/area/{area}.csv` for 25 counties, 3 metros, 3 states and the U.S.; `industry_titles.csv` | Employment, establishments and wages; LQ; growth; shift-share | Annual averages are released each September for the previous year. The fetch script detects the latest available year |
| [County Business Patterns](https://www.census.gov/programs-surveys/cbp.html) | Census Bureau | `https://api.census.gov/data/{year}/cbp` (the variable is `NAICS2017` and carries NAICS 2017 codes through 2023, checked live; requires a free API key) | Establishment size bands, payroll | About two years behind the reference year. The fetch script tries years from newest to oldest |
| [BEA GDP by county and metro](https://www.bea.gov/data/by-place-county-metro-local) | BEA | `https://apps.bea.gov/regional/zip/CAGDP2.zip`, `CAGDP9.zip` (county files) | Nominal GDP for metros (sum of county estimates), states and the U.S.; real GDP for states and the U.S. BEA publishes no metro GDP table in its download files or its API | About one year behind |
| [Delineation files](https://www.census.gov/programs-surveys/metro-micro/about/delineation-files.html) | Census / OMB | `list1_2023.xlsx` | Verifying metro county lists | July 2023 (Bulletin 23-01) |

## Additional analytical layers

| Source | Publisher | Access | Use | Notes |
|---|---|---|---|---|
| [QWI](https://lehd.ces.census.gov/data/) | Census LEHD | `https://api.census.gov/data/timeseries/qwi/sa` (private owners `A05`) | Hire, separation, job-creation and job-destruction rates; stable-job earnings | The pipeline requests the five most recent QCEW years. State coverage lags vary |
| [ACS 1-year](https://www.census.gov/programs-surveys/acs/data/data-tables.html) | Census Bureau | `https://api.census.gov/data/{year}/acs/acs1` | Educational attainment, household income, working from home, each with MOE | Resident-based. 1-year estimates are available for all three CBSAs because each has more than 65,000 people |
| [CPI-U](https://www.bls.gov/cpi/) | BLS | `cu.data.1.AllItems`, series CUUR0000SA0, period M13 | Wage deflator | National index only |
| [U.S. Cluster Mapping Project](https://www.clustermapping.us/) ([framework](https://www.isc.hbs.edu/competitiveness-economic-development/frameworks-and-key-concepts/Pages/clusters.aspx)) | Harvard Business School ISC | Manual download into `data/external/cluster_crosswalk.csv` | Formal traded and local clusters | Not a federal work, so its terms must be checked. Its definitions use NAICS 2012, while QCEW from 2022 uses NAICS 2022, so a bridged crosswalk is needed for recent years. **Not integrated** until a verified file is supplied |

## Local and regional sources (context only)

These sources do not use the same geography or definitions as the standardized comparison. They are documented for context and are not merged into cross-metro figures.

| Source | Geography | Why it is kept separate |
|---|---|---|
| [Michigan Center for Data and Analytics](https://www.michigan.gov/mcda/labor-market-information) | Michigan prosperity regions and MSAs | Projections and occupational data follow state methods with no Illinois/Indiana/Ohio equivalent on the same basis |
| [SEMCOG](https://data.semcog.org/) | Seven-county Southeast Michigan (adds Monroe and Washtenaw, omits Lapeer) | Different county set from the Detroit MSA |
| [CMAP Data Hub](https://datahub.cmap.illinois.gov/) / [regional economy](https://cmap.illinois.gov/focus-areas/regional-economy/) | Seven-county northeastern Illinois | Excludes DeKalb, Grundy and all four Indiana counties. Its cluster analyses are a useful methodological cross-check |
| [Ohio LMI](https://ohiolmi.com/) | Ohio MSAs and workforce areas | Ohio-specific projections. Not comparable across states |

\*Expected periods describe normal release schedules. The periods actually used are written to each manifest's `coverage` section and shown on the dashboard.

## Access (21 October 2026)

| Host | Access from the build environment |
|---|---|
| `data.bls.gov` (QCEW) | Open. QCEW area files need no key |
| `download.bls.gov` (CPI) | Requires a contact **email address** in the User-Agent; returns 403 without one. Pass it with `--contact` |
| `www.bls.gov` | Blocked by the site's CDN for automated clients (403). Documentation pages only; the pipeline does not use it |
| `api.census.gov` (CBP, ACS, QWI) | Requires a free key, set as `CENSUS_API_KEY`. Without one every request redirects to `missing_key.html` |
| `www2.census.gov` (delineation file) | Open |
| `apps.bea.gov/regional/zip` (BEA) | Open |
| `apps.bea.gov/api` | Requires a free BEA key. Used only to confirm that no metro GDP table exists; not used for data |

LEHD has not published Michigan QWI after 2021 Q4 (the API returns no content for 2022 onward), so Detroit's latest complete QWI year is 2020.

## Citation and terms of use

All data used are U.S. federal works in the public domain. Each source entry in `manifest.json` carries a `citation`, and the dashboard shows it in its source registry.

- **BLS** asks users to cite the Bureau of Labor Statistics as the source ([Linking and copyright information](https://www.bls.gov/bls/linksite.htm)).
- **Census Data API** [terms of service](https://www.census.gov/data/developers/about/terms-of-service.html) require this notice, displayed prominently in the dashboard and stored in the manifest's `notices`: *"This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."* The Census Bureau name identifies the source only and does not imply endorsement.
- **BEA**: the data come from BEA's download files, not its API, so the API notice in the [BEA API terms of service](https://apps.bea.gov/API/_pdf/bea_api_tos.pdf) does not apply. Those terms also forbid presenting modified content as BEA's, so metro GDP is labelled as this project's sum of BEA county estimates.
- **Harvard U.S. Cluster Mapping Project** is not used. Its definitions are cited (Delgado, Porter and Stern 2016) only to explain why formal clusters are absent.
- The manifest's notices also state that aggregations, ratios and decompositions are this project's own calculations, not reviewed or endorsed by any agency.

API keys are read from environment variables and are never written to the repository, the retrieval log or the outputs.
