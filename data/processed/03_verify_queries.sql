-- Run in MySQL Workbench after importing ev_charging_gap_dump.sql
USE ev_charging_gap;

-- 1. Row counts per table (screenshot this for the report)
SELECT 'fsa' AS table_name, COUNT(*) AS row_count FROM fsa
UNION ALL SELECT 'ev_registrations', COUNT(*) FROM ev_registrations
UNION ALL SELECT 'charging_stations', COUNT(*) FROM charging_stations
UNION ALL SELECT 'vehicle_registrations_prov', COUNT(*) FROM vehicle_registrations_prov
UNION ALL SELECT 'funding_announcements', COUNT(*) FROM funding_announcements;

-- 2. Top 15 underserved FSAs in the latest quarter
SELECT * FROM v_fsa_gap
WHERE period = (SELECT MAX(period) FROM ev_registrations)
ORDER BY evs_per_port DESC
LIMIT 15;

-- 3. Public ports by charger level and region
SELECT f.region, SUM(s.level2_ports) AS level2_ports, SUM(s.dc_fast_ports) AS dc_fast_ports
FROM charging_stations s JOIN fsa f ON f.fsa_code = s.fsa_code
WHERE s.access = 'public' AND s.status = 'E'
GROUP BY f.region ORDER BY dc_fast_ports DESC;

-- 4. Scraped funding announcements matched to FSAs
SELECT release_date, municipality, fsa_code, chargers_announced, charger_type, funding_amount
FROM funding_announcements ORDER BY release_date DESC;
