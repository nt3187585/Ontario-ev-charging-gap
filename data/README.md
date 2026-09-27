# Data Sources

All datasets are free, public and published by official government sources.

| # | Dataset | Publisher | Format | File(s) in `data/raw/` | Link | Downloaded |
|---|---|---|---|---|---|---|
| 1 | Electric Vehicles in Ontario – by Forward Sortation Area | Government of Ontario (Ontario Data Catalogue) | CSV, quarterly | `ev_by_fsa_<year>_<quarter>.csv` | https://data.ontario.ca/dataset/electric-vehicles-in-ontario-by-forward-sortation-area | 2026-09-27 |
| 2 | Electric Charging and Alternative Fuelling Stations (Ontario, electric) | Natural Resources Canada, via NLR Alternative Fuel Stations API | JSON | `ontario_ev_stations.json` | https://developer.nlr.gov/docs/transportation/alt-fuel-stations-v1/all/ | 2026-09-26 |
| 3 | New motor vehicle registrations, quarterly (Table 20-10-0025-01) | Statistics Canada | CSV | `statcan_20100025_ev_registrations.csv` | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010002501 | 2026-09-27 |
| 4 | Population and dwelling counts: Canada and FSAs, 2021 Census (Table 98-10-0019-01) | Statistics Canada | CSV | `statcan_fsa_population_2021.csv` | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810001901 | 2026-09-27 |
| 5 | Census FSA Boundary File, 2021 (92-179-X) | Statistics Canada | Shapefile (zip) | not stored – see note | https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21 | 2026-09-27 |

**Note on large files:** GitHub's web uploader accepts files up to 25 MB. Files larger than that (for example the boundary shapefile) are not stored here; download them from the link above.

## Dataset 1 – quarters included
Quarterly snapshots of total BEV and PHEV registrations by FSA, one file per quarter (latest: Q2 2026).

## Dataset 3 – selection used
Geography: Ontario, Quebec, British Columbia (plus selected Ontario CMAs) · Fuel type: all fuel types, battery electric, plug-in hybrid electric · Vehicle type: total · Period: Q1 2017 – Q2 2026 · Downloaded "as displayed (for database loading)".

## API query used for dataset 2
`https://developer.nlr.gov/api/alt-fuel-stations/v1.json?api_key=YOUR_KEY&country=CA&state=ON&fuel_type=ELEC&status=all&access=all&limit=all`

The API key is personal and is **not** stored in this repository. The query returned 4,608 Ontario stations.

## Processed files (`data/processed/`)
| File | Created by | Description |
|---|---|---|
| `ontario_ev_stations_clean.csv` | `notebooks/01_stations_json_to_csv.ipynb` | One row per station; port counts by level, total ports, FSA join key |
