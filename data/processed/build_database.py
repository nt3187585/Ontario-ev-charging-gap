"""
build_database.py – Charging the Gap (BSMM.8730, Team #8)

Purpose
-------
Builds the integrated, cleaned data set for the project and writes it as a
self-contained MySQL dump (schema + data) that can be imported in MySQL
Workbench with Server > Data Import > "Import from Self-Contained File".

Inputs (all downloaded from official open-data sources, see data/README.md)
---------------------------------------------------------------------------
1. ontario_ev_stations_clean.csv   – charging stations (flattened from the NLR/NRCan API JSON)
2. ev_by_fsa_<YEAR>_Q<N>.csv       – Ontario EV registrations by FSA, one file per quarter
3. 9810001901-eng.csv              – StatCan 2021 population by FSA (Table 98-10-0019-01)
4. 2010002501-eng.csv              – StatCan new motor vehicle registrations (Table 20-10-0025-01)
5. lfsa000b21a_e.zip               – StatCan 2021 FSA boundary file (optional, for the spatial join)

Outputs (written to the output folder)
--------------------------------------
- ev_charging_gap_dump.sql         – MySQL dump: CREATE DATABASE, 5 tables, keys, data, v_fsa_gap view
- <table>.csv                      – the cleaned tables, for data/processed in GitHub
- ontario_fsa.geojson              – simplified Ontario FSA boundaries for the Power BI map
- build_log.txt                    – row counts and data-quality checks

Usage
-----
python build_database.py <input_folder> <output_folder>
"""

import glob
import io
import os
import re
import sys
import zipfile

import pandas as pd

IN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
log_lines = []


def log(msg):
    """Print a message and keep it for build_log.txt (evidence of each step)."""
    print(msg)
    log_lines.append(str(msg))


def find(pattern):
    """Return the first input file whose name matches a glob pattern."""
    hits = sorted(glob.glob(os.path.join(IN, pattern)))
    return hits[0] if hits else None


ONTARIO_FSA = r"^[KLMNP]\d[A-Z]$"   # Ontario postal codes start with K, L, M, N or P
REGION = {"K": "Eastern Ontario", "L": "Central Ontario", "M": "Toronto",
          "N": "Southwestern Ontario", "P": "Northern Ontario"}

# ---------------------------------------------------------------------------
# 1. POPULATION BY FSA (structured CSV, StatCan display format)
#    The file has ~9 metadata lines before the header and numbers with commas.
# ---------------------------------------------------------------------------
raw = open(find("*9810001901*"), encoding="utf-8-sig").read().splitlines()
data_lines = [l for l in raw if re.match(r'^"[A-Z]\d[A-Z]",', l)]       # keep only FSA data rows
pop = pd.read_csv(io.StringIO("\n".join(data_lines)), header=None, dtype=str)
pop.columns = ["fsa_code", "population", "dwellings", "occupied_dwellings"]
pop = pop[pop["fsa_code"].str.match(ONTARIO_FSA, na=False)].copy()      # keep Ontario FSAs only
for c in ["population", "dwellings"]:
    pop[c] = pd.to_numeric(pop[c].str.replace(",", ""), errors="coerce").astype("Int64")
fsa = pop[["fsa_code", "population", "dwellings"]].drop_duplicates("fsa_code")
fsa.insert(1, "region", fsa["fsa_code"].str[0].map(REGION))           # derived attribute
log(f"FSA table: {len(fsa)} Ontario FSAs with 2021 population")

# ---------------------------------------------------------------------------
# 2. EV REGISTRATIONS BY FSA (structured CSV, one file per quarter)
#    Column names change over time ("TotalEV" vs "Total EV"), so they are
#    matched by keyword. Blank BEV/PHEV cells mean zero vehicles.
# ---------------------------------------------------------------------------
frames = []
for path in sorted(glob.glob(os.path.join(IN, "*ev_by_fsa_*.csv"))):
    year, q = re.search(r"(\d{4})_Q([1-4])", path).groups()
    d = pd.read_csv(path)
    d.columns = [c.strip().lower().replace(" ", "") for c in d.columns]
    out = pd.DataFrame({
        "fsa_code": d["fsa"].str.strip().str.upper(),
        "period": f"{year}-Q{q}",
        "bev": pd.to_numeric(d["bev"], errors="coerce").fillna(0).astype(int),
        "phev": pd.to_numeric(d["phev"], errors="coerce").fillna(0).astype(int),
        "total_ev": pd.to_numeric(d["totalev"], errors="coerce").fillna(0).astype(int),
    })
    frames.append(out)
ev = pd.concat(frames, ignore_index=True).drop_duplicates(["fsa_code", "period"])
quarters = sorted(ev["period"].unique())
log(f"EV registrations: {len(ev)} FSA-quarter rows, {len(quarters)} quarters ({quarters[0]} to {quarters[-1]})")
expected = [f"{y}-Q{n}" for y in range(int(quarters[0][:4]), int(quarters[-1][:4]) + 1) for n in range(1, 5)]
expected = [p for p in expected if quarters[0] <= p <= quarters[-1]]
missing_q = [p for p in expected if p not in quarters]
log(f"Quality check – missing quarters: {missing_q or 'none'}")
not_in_census = sorted(set(ev["fsa_code"]) - set(fsa["fsa_code"]))
log(f"Quality check – FSAs in EV data but not in 2021 Census (kept out of joins): {len(not_in_census)} "
    f"(small or new FSAs, e.g. {', '.join(not_in_census[:5])})")
ev = ev[ev["fsa_code"].isin(fsa["fsa_code"])]                          # enforce foreign key

# ---------------------------------------------------------------------------
# 3. CHARGING STATIONS (semi-structured JSON from the API, already flattened)
# ---------------------------------------------------------------------------
st = pd.read_csv(find("*ontario_ev_stations*"), dtype={"postal_code": str, "fsa": str})
st = st.rename(columns={"fsa": "fsa_code"})
st["open_date"] = pd.to_datetime(st["open_date"], format="%d-%m-%Y", errors="coerce").dt.date
st["access"] = st["access"].str.lower()
before = len(st)
st = st.drop_duplicates("station_id")
log(f"Charging stations: {len(st)} ({before - len(st)} duplicates removed)")

invalid = ~st["fsa_code"].fillna("").str.match(ONTARIO_FSA)
log(f"Quality check – stations with an invalid/out-of-province postal code: {invalid.sum()}")

# Spatial join: assign every station to the FSA polygon that contains it.
# This fixes the invalid postal codes and validates the postal-code FSAs.
zip_path = find("lfsa000b21a_e*.zip")
if zip_path:
    import geopandas as gpd
    shp = "zip://" + zip_path + "!" + [n for n in zipfile.ZipFile(zip_path).namelist() if n.endswith(".shp")][0]
    poly = gpd.read_file(shp)
    poly = poly[poly["CFSAUID"].str.match(ONTARIO_FSA)][["CFSAUID", "geometry"]]
    pts = gpd.GeoDataFrame(st[["station_id"]], geometry=gpd.points_from_xy(st["longitude"], st["latitude"]),
                           crs="EPSG:4326").to_crs(poly.crs)
    joined = gpd.sjoin(pts, poly, how="left", predicate="within").drop_duplicates("station_id")
    spatial = joined.set_index("station_id")["CFSAUID"]
    st["fsa_spatial"] = st["station_id"].map(spatial)
    mismatch = (~invalid) & st["fsa_spatial"].notna() & (st["fsa_spatial"] != st["fsa_code"])
    log(f"Spatial join – postal-code FSA differs from boundary FSA for {mismatch.sum()} stations (postal code kept)")
    st.loc[invalid, "fsa_code"] = st.loc[invalid, "fsa_spatial"]
    log(f"Spatial join – fixed {st.loc[invalid, 'fsa_code'].notna().sum()} of {invalid.sum()} invalid postal codes")
    # simplified Ontario boundaries for the Power BI shape/filled map
    poly.to_crs("EPSG:4326").assign(geometry=lambda g: g.geometry.simplify(0.002)) \
        .rename(columns={"CFSAUID": "fsa_code"}).to_file(os.path.join(OUT, "ontario_fsa.geojson"), driver="GeoJSON")
st.loc[~st["fsa_code"].isin(fsa["fsa_code"]), "fsa_code"] = None       # enforce foreign key
log(f"Stations matched to an FSA: {st['fsa_code'].notna().sum()} of {len(st)}")

# ---------------------------------------------------------------------------
# 4. PROVINCIAL / NATIONAL REGISTRATIONS (structured CSV, StatCan display format)
#    Wide table (one column per quarter) -> long table (one row per quarter).
# ---------------------------------------------------------------------------
raw = open(find("*2010002501*"), encoding="utf-8-sig").read().splitlines()
geo = next(l for l in raw if l.startswith('"Geography"')).split(",")[1].strip('"')
vtype = next(l for l in raw if l.startswith('"Vehicle type"')).split(",")[1].strip('"')
hdr = next(i for i, l in enumerate(raw) if l.startswith('"Fuel type"'))
end = next(i for i in range(hdr + 2, len(raw)) if raw[i].strip() == "")
wide = pd.read_csv(io.StringIO("\n".join([raw[hdr]] + raw[hdr + 2:end])), dtype=str)
reg = wide.melt(id_vars="Fuel type", var_name="period", value_name="vehicles")
reg["vehicles"] = pd.to_numeric(reg["vehicles"].str.replace(",", ""), errors="coerce").astype("Int64")
reg["period"] = reg["period"].str.replace(r"Q(\d) (\d{4})", r"\2-Q\1", regex=True)
reg["fuel_type"] = reg["Fuel type"].str.replace(r"\s\d+$", "", regex=True)   # drop footnote numbers
reg["geography"] = geo
reg["vehicle_type"] = re.sub(r"\s\d+$", "", vtype)
reg = reg[["period", "geography", "fuel_type", "vehicle_type", "vehicles"]]
log(f"Vehicle registrations ({geo}): {len(reg)} rows")

# ---------------------------------------------------------------------------
# 5. FUNDING ANNOUNCEMENTS (unstructured, scraped news releases)
#    Loaded by the scraper notebook when available; empty until then.
# ---------------------------------------------------------------------------
fund_path = find("*funding_announcements*.csv")
fund = pd.read_csv(fund_path) if fund_path else pd.DataFrame(
    columns=["announcement_id", "release_date", "municipality", "fsa_code", "chargers_announced",
             "charger_type", "funding_amount", "source_url", "raw_text"])
log(f"Funding announcements: {len(fund)} rows")

# ---------------------------------------------------------------------------
# 6. QUICK RESULT CHECK – top gap FSAs in the latest quarter
# ---------------------------------------------------------------------------
latest = quarters[-1]
ports = st[(st["access"] == "public") & (st["status"] == "E")].groupby("fsa_code")["total_ports"].sum()
chk = fsa.merge(ev[ev["period"] == latest], on="fsa_code")
chk["public_ports"] = chk["fsa_code"].map(ports).fillna(0)
log(f"FSAs with EVs but no public port in {latest}: {((chk['total_ev'] > 0) & (chk['public_ports'] == 0)).sum()}")

# ---------------------------------------------------------------------------
# 7. WRITE CSVs AND THE MYSQL DUMP
# ---------------------------------------------------------------------------
st_cols = ["station_id", "fsa_code", "station_name", "city", "postal_code", "latitude", "longitude", "network",
           "connector_types", "level1_ports", "level2_ports", "dc_fast_ports", "total_ports", "access",
           "status", "facility_type", "open_date"]
tables = {
    "fsa": (fsa, ["fsa_code", "region", "population", "dwellings"]),
    "ev_registrations": (ev, ["fsa_code", "period", "bev", "phev", "total_ev"]),
    "charging_stations": (st, st_cols),
    "vehicle_registrations_prov": (reg, ["period", "geography", "fuel_type", "vehicle_type", "vehicles"]),
    "funding_announcements": (fund, list(fund.columns)),
}


def sql_value(v):
    """Convert a Python/pandas value into a safe SQL literal."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "NULL"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return repr(v) if isinstance(v, float) else str(v)
    if hasattr(v, "item"):                      # numpy / pandas scalar
        return str(v.item())
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


DDL = """-- Charging the Gap – MySQL dump generated by build_database.py
DROP DATABASE IF EXISTS ev_charging_gap;
CREATE DATABASE ev_charging_gap CHARACTER SET utf8mb4;
USE ev_charging_gap;

CREATE TABLE fsa (
  fsa_code CHAR(3) PRIMARY KEY, region VARCHAR(40), population INT, dwellings INT);

CREATE TABLE ev_registrations (
  fsa_code CHAR(3), period VARCHAR(10), bev INT, phev INT, total_ev INT,
  PRIMARY KEY (fsa_code, period),
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code));

CREATE TABLE charging_stations (
  station_id INT PRIMARY KEY, fsa_code CHAR(3), station_name VARCHAR(255), city VARCHAR(100),
  postal_code VARCHAR(10), latitude DECIMAL(9,6), longitude DECIMAL(9,6), network VARCHAR(100),
  connector_types VARCHAR(255), level1_ports INT, level2_ports INT, dc_fast_ports INT, total_ports INT,
  access VARCHAR(20), status CHAR(1), facility_type VARCHAR(60), open_date DATE,
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code));

CREATE TABLE vehicle_registrations_prov (
  id INT AUTO_INCREMENT PRIMARY KEY, period VARCHAR(10), geography VARCHAR(150),
  fuel_type VARCHAR(80), vehicle_type VARCHAR(80), vehicles INT);

CREATE TABLE funding_announcements (
  announcement_id INT PRIMARY KEY, release_date VARCHAR(30), municipality VARCHAR(100), fsa_code CHAR(3),
  chargers_announced INT, charger_type VARCHAR(20), funding_amount DECIMAL(15,2),
  source_url VARCHAR(500), raw_text TEXT,
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code));
"""

VIEW = """
-- EVs per public port and ports per 1,000 residents, by FSA and quarter
CREATE VIEW v_fsa_gap AS
SELECT f.fsa_code, f.region, f.population, e.period, e.total_ev,
       COALESCE(p.public_ports, 0)                       AS public_ports,
       e.total_ev / NULLIF(p.public_ports, 0)            AS evs_per_port,
       COALESCE(p.public_ports, 0) / f.population * 1000 AS ports_per_1000
FROM fsa f
JOIN ev_registrations e ON e.fsa_code = f.fsa_code
LEFT JOIN (SELECT fsa_code, SUM(total_ports) AS public_ports
           FROM charging_stations
           WHERE access = 'public' AND status = 'E'
           GROUP BY fsa_code) p ON p.fsa_code = f.fsa_code;
"""

parts = [DDL]
for name, (df, cols) in tables.items():
    df[cols].to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    rows = df[cols].astype(object).values.tolist()
    for i in range(0, len(rows), 500):           # batches of 500 rows keep each INSERT small
        values = ",\n".join("(" + ",".join(sql_value(v) for v in r) + ")" for r in rows[i:i + 500])
        parts.append(f"INSERT INTO {name} ({','.join(cols)}) VALUES\n{values};")
    log(f"Dump: {name} -> {len(rows)} rows")
parts.append(VIEW)
open(os.path.join(OUT, "ev_charging_gap_dump.sql"), "w", encoding="utf-8").write("\n".join(parts))
open(os.path.join(OUT, "build_log.txt"), "w").write("\n".join(log_lines))
log("Done.")
