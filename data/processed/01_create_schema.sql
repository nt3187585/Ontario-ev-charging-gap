-- =====================================================================
-- BSMM.8730 – Charging the Gap | Step 1: create the database and tables
-- Run in MySQL Workbench: File > Open SQL Script > lightning bolt
-- =====================================================================
DROP DATABASE IF EXISTS ev_charging_gap;
CREATE DATABASE ev_charging_gap CHARACTER SET utf8mb4;
USE ev_charging_gap;

-- Postal areas (structured – StatCan population CSV)
CREATE TABLE fsa (
  fsa_code   CHAR(3) PRIMARY KEY,
  region     VARCHAR(40),
  population INT
);

-- EV registrations by postal area and quarter (structured – Ontario CSVs)
CREATE TABLE ev_registrations (
  fsa_code CHAR(3),
  period   VARCHAR(10),
  bev      INT,
  phev     INT,
  total_ev INT,
  PRIMARY KEY (fsa_code, period),
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code)
);

-- Charging stations (semi-structured – NRCan JSON API, flattened)
CREATE TABLE charging_stations (
  station_id      INT PRIMARY KEY,
  fsa_code        CHAR(3),
  station_name    VARCHAR(255),
  city            VARCHAR(100),
  postal_code     VARCHAR(10),
  latitude        DECIMAL(9,6),
  longitude       DECIMAL(9,6),
  network         VARCHAR(100),
  connector_types VARCHAR(255),
  level1_ports    INT,
  level2_ports    INT,
  dc_fast_ports   INT,
  total_ports     INT,
  access          VARCHAR(20),
  status          CHAR(1),
  open_date       DATE,
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code)
);

-- Provincial registrations (structured – StatCan 20-10-0025-01)
CREATE TABLE vehicle_registrations_prov (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  period       VARCHAR(10),
  geography    VARCHAR(150),
  fuel_type    VARCHAR(80),
  vehicle_type VARCHAR(80),
  vehicles     INT
);

-- Funding announcements (unstructured – scraped Government of Canada news releases)
CREATE TABLE funding_announcements (
  announcement_id    INT PRIMARY KEY,
  release_date       VARCHAR(30),
  municipality       VARCHAR(100),
  fsa_code           CHAR(3),
  chargers_announced INT,
  charger_type       VARCHAR(20),
  funding_amount     DECIMAL(15,2),
  source_url         VARCHAR(500),
  raw_text           TEXT,
  FOREIGN KEY (fsa_code) REFERENCES fsa(fsa_code)
);

-- Gap view: EVs per public port and ports per 1,000 residents, by FSA and quarter
CREATE VIEW v_fsa_gap AS
SELECT f.fsa_code, f.region, f.population, e.period, e.total_ev,
       COALESCE(SUM(s.total_ports),0)                     AS public_ports,
       e.total_ev / NULLIF(SUM(s.total_ports),0)          AS evs_per_port,
       COALESCE(SUM(s.total_ports),0) / f.population * 1000 AS ports_per_1000
FROM fsa f
JOIN ev_registrations e ON e.fsa_code = f.fsa_code
LEFT JOIN charging_stations s
       ON s.fsa_code = f.fsa_code AND s.access = 'public' AND s.status = 'E'
GROUP BY f.fsa_code, f.region, f.population, e.period, e.total_ev;
