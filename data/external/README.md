# Optional external inputs

Files placed here are read by the build but are **not committed** (see `.gitignore`), because they may carry their own licence terms.

## cluster_crosswalk.csv (optional)

A NAICS-to-cluster crosswalk from the U.S. Cluster Mapping Project (https://www.clustermapping.us/). Check its terms of use before you add it. Required columns:

| column | example |
|---|---|
| naics6 | 336111 |
| cluster_code | 6 |
| cluster_name | Automotive |
| cluster_type | traded |
| naics_edition | NAICS 2012 |

Each industry may appear only once. Without this file, the dashboard reports NAICS specialization and does not claim formal clusters.
