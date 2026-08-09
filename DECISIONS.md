# INT-22 Contract Reference Mapping — Session Decisions

Session closed 6 Aug 2026. Deliverables live on branch
`claude/contract-reference-mapping-5jq1em`, PR [#5](https://github.com/rajesh-sha/Test/pull/5) (draft).

## Deliverables

| File | Contents |
|---|---|
| `INT-22_Contract_Reference_Mapping_20260805.xlsx` | 13 sheets: README, canonical mapping, per-contract field mappings (Telstra, NBN, Optus), ODM sheets (README, canonical, file mapping, queries), SOQL queries, DB validation queries, local test DB, SQL-vs-SOQL comparison |
| `INT-22_SOQL_queries_20260805.md` | The five SOQL pull queries in copy-paste form |
| `INT-22_local_test_db.sql` | Runnable local test database script, verified end-to-end |

## Decisions

1. **Single source field per contract.** The INT-22 contract reference mapping is revised from
   multiple Site-tracker fields to one source field per canonical field per contract
   (Optus Megaladon, Telstra, TPG, NTA, NBN, ODM), as tabled on the Canonical Mapping sheet.

2. **Direct SiteTracker-to-SAP-CPI pattern, no Redshift.** All five pull queries (Optus, Telstra,
   NBN, ODM project creation, ODM supplier invoices) target the SAP CPI Salesforce adapter
   directly against SiteTracker, per the POC outcome (Tests 3, 8, 9 validated). Redshift is not
   introduced as an integration layer.

3. **Delta pulls.** Every query filters on created/changed since the last successful run; the
   example date `2026-08-01T00:00:00Z` is replaced at runtime by the iFlow. Pagination is
   handled by the Salesforce adapter.

4. **ODM RCTI flat file to be replaced.** The `ODM_SS_STIFS` extract is superseded by the
   Test-3-validated SOQL pull. The file's hardcoded GL code (73020), tax code (GST10) and
   quantity (1) move to SAP-side determination. Credit lines (negative amounts) pass through.
   The business-flow fallback (project → ticket → job) is an iFlow mapping rule, not SOQL.

5. **Message routing.** `header.sourceMessageType` is the constant `CREATE_SO` for the ODM
   WBS/service-order table; RCTI/REQUEST_PO route to procurement, MATERIALS_* to stock
   consumption, CLAIM to billing canonicals.

## Open gaps (yellow in the workbook — must close before build)

1. **CCR (commercial contract number) does not exist in SiteTracker.** Mandatory for
   `header.clientContractId` on ODM — a new field must be created. Biggest blocker.
2. **Telstra**: IFS Detail ID and IFS Build ID (WBS elements) are not in the extract — source
   from SiteTracker once API names are confirmed.
3. **Optus**: Design/SAED/Construction Codes and CCR not in the extract — same treatment.
4. **NBN**: Site ID missing from the extract; numeric state codes (1–4) need a decode table;
   Job Type source (build_type vs category_1) needs a business call.
5. **ODM**: state only exists inside the concatenated address text; region and jobType have no
   discrete column — all to be sourced via the SOQL pull, not parsed from strings.

## To confirm with Jackie (orange in the workbook)

- Proposed API names: `Program_ID__c`, `Project_Office__c`, `Work_Type__c`, `IFS_Detail_ID__c`,
  `IFS_Build_ID__c`, `CP_No__c`, `Job_Type__c`, `State__c`, `Region__c`,
  `Total_Job_Amount__c`, `Business_Flow_Type__c`.
- NBN activity child-relationship name (assumed `sitetracker__Activities__r`) and exact
  ID66/ID164 activity names.
- `Client__c` stored values ('Telstra' vs 'TLS', 'nbn' vs 'NBN').
- Whether `header.serviceHierarchy` (ODM) sources from workType or costCode; meaning of the
  actlink codes 1475PM / 1475RO / 1475SD.

## Validation approach agreed

- **SQL vs SOQL comparison** (workbook sheet): read-only SQL for the SiteTracker reporting
  database paired with the equivalent adapter SOQL — Jackie runs the SQL, results must match
  the adapter output row-for-row (same cut-off date both sides).
- **DB validation queries**: 18 reconciliation checks (counts, duplicates, missing required
  values, credit lines, code lists) to run after each pull.
- **Local test DB**: `INT-22_local_test_db.sql` builds test tables with real sample rows and
  runs the checks; executed end-to-end successfully (all 23 statements, 11 checks as expected).

## Verification done this session

- All 5 SOQL queries passed automated syntax checks (balanced brackets/quotes, no trailing
  commas, valid date literals, no unresolved placeholders).
- All 5 read-SQL comparison queries executed against a test schema.
- All 18 DB validation checks syntax-validated; local test script run end-to-end with expected
  results, including the J-051326 credit line (−126.67).
