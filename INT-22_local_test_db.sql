-- ============================================================================
-- INT-22 — Local test database for all contracts (Telstra, NBN, Optus, ODM)
-- ============================================================================
-- What this does:
--   1. Creates one test table per contract, matching the extract file layout.
--   2. Loads real sample rows taken from the 03-05 Aug 2026 files.
--   3. Ends with the validation checks so you can test them locally.
-- How to run:
--   PostgreSQL : psql -d yourdb -f INT-22_local_test_db.sql
--   SQLite     : sqlite3 test.db < INT-22_local_test_db.sql
-- Standard SQL only — no vendor-specific features.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Telstra
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS tls_ifs_project_load;
CREATE TABLE tls_ifs_project_load (
  header_contract_ref   VARCHAR(20),
  wo_type               VARCHAR(10),
  customer_project_id_b VARCHAR(40),
  site_id_b             VARCHAR(20),
  site_name_a           VARCHAR(80),
  customer_project_id   VARCHAR(40),
  site_id_a             VARCHAR(20),
  site_location         VARCHAR(10),
  project_office        VARCHAR(20),
  client                VARCHAR(10),
  program_id            VARCHAR(10),
  project_director      VARCHAR(50),
  st_project_id         VARCHAR(20)
);

INSERT INTO tls_ifs_project_load VALUES
('CP20004880','SMR','8350155257/1','034456','80 WOOD ROAD, TRUGANINA','8350155257-1','036677','VIC','National','TLS','TE6','BIBEKANANDA.NAG','P-036677'),
('CP20004880','SAED','80005743/813','CTOH','CATOS HILL','VT23524','036293','TAS','VIC','TLS','TE0','BIBEKANANDA.NAG','P-036293');

-- ----------------------------------------------------------------------------
-- 2. NBN
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS nbn_ifs_integration;
CREATE TABLE nbn_ifs_integration (
  program_id            VARCHAR(10),
  program_description   VARCHAR(60),
  project_id            VARCHAR(20),
  project_description   VARCHAR(80),
  project_manager_engineer VARCHAR(50),
  category_1            VARCHAR(10),
  saed_scope            VARCHAR(20),
  build_type            VARCHAR(20),
  customer              VARCHAR(20),
  customer_project      VARCHAR(40),
  state                 VARCHAR(5),
  activity              VARCHAR(10),
  subcat                VARCHAR(5),
  activity_id           VARCHAR(10),
  activity_description  VARCHAR(60),
  activity_category     VARCHAR(20)
);

INSERT INTO nbn_ifs_integration VALUES
('17P012','NBN Fixed Wireless','P-011078','Wedderburn Reef',NULL,'DSC','FULL SAED','RF/MW OTHE','117NBN01','R302-3HRZ-3SOP-5106','3','712','DN','MS7040','Final Acceptance Complete','SAED'),
('17P012','NBN Fixed Wireless','P-011078','Wedderburn Reef',NULL,'DSC','FULL SAED','RF/MW OTHE','117NBN01','R302-3HRZ-3SOP-5106','3','712','CN','MS7040','Final Acceptance Complete','Site Works'),
('17P012','NBN Fixed Wireless','P-011083','Hayters Hill','Leo Orpilla','DSC',NULL,'RF/MW OTHE','117NBN01','R305-2GRZ-2BYB-5108','2','712','DN','MS7040','Final Acceptance Complete','SAED'),
('17P012','NBN Fixed Wireless','P-011083','Hayters Hill','Leo Orpilla','DSC',NULL,'RF/MW OTHE','117NBN01','R305-2GRZ-2BYB-5108','2','712','CN','MS7040','Final Acceptance Complete','Site Works');

-- ----------------------------------------------------------------------------
-- 3. Optus
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS optus_1_meg2_projects;
CREATE TABLE optus_1_meg2_projects (
  program_id            VARCHAR(20),
  program_description   VARCHAR(60),
  project_id            VARCHAR(20),
  project_description   VARCHAR(80),
  project_manager_engineer VARCHAR(50),
  category_1            VARCHAR(20),
  category_2            VARCHAR(20),
  customer              VARCHAR(20),
  customer_project      VARCHAR(40),
  state                 VARCHAR(5),
  activity_description  VARCHAR(80),
  site_id               VARCHAR(20),
  saed_manager          VARCHAR(50)
);

INSERT INTO optus_1_meg2_projects VALUES
('GRN-F-OO','Greenfield (OO)','P-018495','BULLABURRA','Muhammad Kashif','SAED','GRNFIELD_1','OPTUS','614022','1','phase_2_financial_milestones_complete','S0822','JAMES.BOUCHER'),
('GRN-F-OO','Greenfield (OO)','P-015247','MARONG EAST','Muhammad Kashif','SAED','GRNFIELD_1','OPTUS','589330','1','phase_2_financial_milestones_complete','M4050','JAMES.BOUCHER'),
('GRN-F-OO','Greenfield (OO)','P-018590','BELLMERE SOUTH','Brent Devin','SAED','GRNFIELD_1','OPTUS','615291','1','phase_2_financial_milestones_complete','B1958','JAMES.BOUCHER');

-- ----------------------------------------------------------------------------
-- 4. ODM (supplier invoice extract)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS odm_ss_stifs;
CREATE TABLE odm_ss_stifs (
  line_no               INTEGER,
  vendor_id             VARCHAR(20),
  job_name              VARCHAR(20),
  date_job_invoiced     VARCHAR(10),
  line_dissector        INTEGER,
  gl_code               VARCHAR(10),
  tax_code              VARCHAR(10),
  quantity              INTEGER,
  total_job_amount      NUMERIC(12,2),
  project_name_address  VARCHAR(200),
  vendor_name           VARCHAR(120),
  map_to_actlink        VARCHAR(10)
);

INSERT INTO odm_ss_stifs VALUES
(1,'S047291','J-021745','2026-08-03',1,'73020','GST10',1,2255.24,'BRQ000000046205 25 Anzac Road Carina Heights QLD 4152','JAY BHAWANI CONSTRUCTION PTY LTD','1475PM'),
(9,'S041047','J-039421','2026-08-03',1,'73020','GST10',1,6270.98,'NBN-03674059 50 HOWLEYS RD NOTTING HILL VIC 3168','AXIAL AIRCON PTY LTD','1475RO'),
(17,'V017247','J-045498','2026-08-03',1,'73020','GST10',1,4708.98,'BRQ000000078821 63 Peel Street Wilton NSW 2571','Marsh Siban Pty Ltd','1475SD'),
(16,'S043771','J-045424','2026-08-03',1,'73020','GST10',1,2100.98,'DFN_3CWO_CW24_3CWO-65 Near 292 Johnson St Abbotsford VIC 3067','THAT TELCO COMPANY PTY LTD','1475RO'),
(107,'S033383','J-051326','2026-08-03',1,'73020','GST10',1,-126.67,'BRQ000000084272 174 Camden Road Douglas Park NSW 2569','J.P. COMMUNICATIONS','1475SD');

-- ============================================================================
-- 5. Validation checks (same logic as the DB Validation Queries sheet)
-- ============================================================================

-- Telstra: duplicate project check — expect no rows
SELECT st_project_id, COUNT(*) AS copies
FROM tls_ifs_project_load
GROUP BY st_project_id
HAVING COUNT(*) > 1;

-- Telstra: missing required values — expect all zeros
SELECT
  COUNT(*)                              AS total_rows,
  COUNT(*) - COUNT(header_contract_ref) AS missing_contract_ref,
  COUNT(*) - COUNT(customer_project_id) AS missing_job_number,
  COUNT(*) - COUNT(site_id_a)           AS missing_site_id,
  COUNT(*) - COUNT(site_name_a)         AS missing_site_name,
  COUNT(*) - COUNT(program_id)          AS missing_program_id,
  COUNT(*) - COUNT(project_director)    AS missing_project_director
FROM tls_ifs_project_load;

-- NBN: design / construction pairing — expect no rows
SELECT project_id,
  SUM(CASE WHEN subcat = 'DN' THEN 1 ELSE 0 END) AS design_rows,
  SUM(CASE WHEN subcat = 'CN' THEN 1 ELSE 0 END) AS construction_rows
FROM nbn_ifs_integration
GROUP BY project_id
HAVING SUM(CASE WHEN subcat = 'DN' THEN 1 ELSE 0 END) <> 1
    OR SUM(CASE WHEN subcat = 'CN' THEN 1 ELSE 0 END) <> 1;

-- NBN: state code list
SELECT state, COUNT(*) AS rows_with_this_code
FROM nbn_ifs_integration
GROUP BY state
ORDER BY state;

-- Optus: missing required values — expect all zeros
SELECT
  COUNT(*)                              AS total_rows,
  COUNT(*) - COUNT(customer_project)    AS missing_waid,
  COUNT(*) - COUNT(site_id)             AS missing_site_id,
  COUNT(*) - COUNT(project_description) AS missing_site_name,
  COUNT(*) - COUNT(program_id)          AS missing_program_group,
  COUNT(*) - COUNT(state)               AS missing_state
FROM optus_1_meg2_projects;

-- ODM: invoice totals by run date
SELECT date_job_invoiced,
       COUNT(*)              AS invoice_lines,
       SUM(total_job_amount) AS total_amount
FROM odm_ss_stifs
GROUP BY date_job_invoiced
ORDER BY date_job_invoiced;

-- ODM: duplicate job check — expect no rows
SELECT job_name, COUNT(*) AS copies
FROM odm_ss_stifs
GROUP BY job_name
HAVING COUNT(*) > 1;

-- ODM: missing supplier — expect no rows
SELECT job_name, total_job_amount
FROM odm_ss_stifs
WHERE vendor_id IS NULL OR vendor_id = '';

-- ODM: credit lines — expect the known credit J-051326 only
SELECT job_name, vendor_id, total_job_amount
FROM odm_ss_stifs
WHERE total_job_amount < 0;

-- ODM: business flow code list
SELECT map_to_actlink, COUNT(*) AS lines
FROM odm_ss_stifs
GROUP BY map_to_actlink
ORDER BY map_to_actlink;

-- All contracts: one-line summary
SELECT 'Telstra' AS contract, COUNT(*) AS rows_loaded FROM tls_ifs_project_load
UNION ALL
SELECT 'NBN', COUNT(DISTINCT project_id) FROM nbn_ifs_integration
UNION ALL
SELECT 'Optus', COUNT(DISTINCT project_id) FROM optus_1_meg2_projects
UNION ALL
SELECT 'ODM', COUNT(*) FROM odm_ss_stifs;
