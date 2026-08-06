# INT-22 WBSCreateUpdate — SiteTracker pull queries (SAP CPI Salesforce adapter)

Companion to `INT-22_Contract_Reference_Mapping_20260805.xlsx`. One delta pull query per
contract, targeting the direct SiteTracker-to-SAP-CPI pattern (no Redshift layer).
`2026-08-01T00:00:00Z` is the CPI variable holding the last successful pull
timestamp; pagination is handled by the Salesforce adapter (validated in POC).

## Optus (Megaladon) — base query validated in POC Test 8

```sql
SELECT Id, Name,
       Site_ID__c,
       sitetracker__Site_Name_Search__c,
       WA_ID_Mirage__c,
       Program__c,
       Program_Type__c,
       Project_Engineer__c,
       Client__c,
       Client_Status__c,
       State__c,
       Phase_1_Financial_Milestones_Complete__c,
       Phase_2_Financial_Milestones_Complete__c,
       Phase_4_Financial_Milestones_Complete__c,
       SAED_Manager__c,
       CreatedDate, LastModifiedDate
FROM sitetracker__Project__c
WHERE Client__c = 'Optus'
  AND Client_Status__c IN ('Current', 'Complete', 'On Hold')
  AND Program__c != '3G Partial Decom'
  AND LastModifiedDate >= 2026-08-01T00:00:00Z
```

To confirm: `State__c` API name (added beyond the Test 8 field list); WBS element fields
(Design Code / SAED Code / Construction Code, CCR) to be added once API names are
confirmed with Jackie.

## Telstra

```sql
SELECT Id, Name,
       Site_ID__c,
       sitetracker__Site_Name_Search__c,
       WA_ID_Mirage__c,
       Program_ID__c,
       Project_Office__c,
       Work_Type__c,
       IFS_Detail_ID__c,
       IFS_Build_ID__c,
       CP_No__c,
       Client__c,
       Client_Status__c,
       CreatedDate, LastModifiedDate
FROM sitetracker__Project__c
WHERE Client__c = 'Telstra'
  AND Client_Status__c IN ('Current', 'Complete', 'On Hold')
  AND LastModifiedDate >= 2026-08-01T00:00:00Z
```

To confirm: API names `Program_ID__c`, `Project_Office__c`, `Work_Type__c`,
`IFS_Detail_ID__c`, `IFS_Build_ID__c`, `CP_No__c` are proposed from field labels — confirm
against the SiteTracker org before build. Confirm `Client__c` value ('Telstra' vs 'TLS').

## NBN — Activity subquery pattern validated in POC Test 9

```sql
SELECT Id, Name,
       Site_ID__c,
       sitetracker__Site_Name_Search__c,
       WA_ID_Mirage__c,
       Job_Type__c,
       State__c,
       Program__c,
       Client__c,
       Client_Status__c,
       CreatedDate, LastModifiedDate,
       (SELECT Id, Name,
               sitetracker__Forecast_Actual__c,
               sitetracker__ActualDate__c,
               sitetracker__NA__c
        FROM sitetracker__Activities__r
        WHERE Name IN ('ID66 Site construction commencement (F)',
                       'ID164 Operational Acceptance (F)'))
FROM sitetracker__Project__c
WHERE Client__c = 'nbn'
  AND Client_Status__c IN ('Current', 'Complete', 'On Hold')
  AND LastModifiedDate >= 2026-08-01T00:00:00Z
```

To confirm: parent-to-child relationship name (assumed `sitetracker__Activities__r`), exact
Activity `Name` values for ID66/ID164, `Client__c` value ('nbn' vs 'NBN'), `Job_Type__c`
API name.

## ODM — CREATE_SO (Service Order / WBS creation)

```sql
SELECT Id, Name,
       Project_Name__c,
       Address__c,
       Description__c,
       Project_Start_A__c,
       sitetracker__Project_Status__c,
       Business_Flow_Type__c,
       Work_Type__c,
       Job_Type__c,
       State__c,
       Region__c,
       CCR__c,
       CreatedDate, LastModifiedDate
FROM sitetracker__Project__c
WHERE CreatedDate >= 2026-08-01T00:00:00Z
```

To confirm: `CCR__c` (Commercial Contract number) does not exist yet — field to be created
in SiteTracker to populate `header.clientContractId`. `Work_Type__c` / `Job_Type__c` /
`State__c` / `Region__c` API names proposed from labels; verify whether the
`header.serviceHierarchy` source is workType or costCode.

## ODM — RCTI (replaces the ODM_SS_STIFS flat-file extract; base query validated in POC Test 3)

```sql
SELECT Id, Name,
       sitetracker__Job__c,
       sitetracker__Job__r.Name,
       sitetracker__Job__r.Project_Name__c,
       sitetracker__Job__r.Date_Job_Invoiced__c,
       sitetracker__Job__r.Total_Job_Amount__c,
       sitetracker__Job__r.Business_Flow_Type__c,
       sitetracker__Job__r.sitetracker__Vendor__r.Vendor_ID__c,
       sitetracker__Job__r.sitetracker__Vendor__r.Name,
       sitetracker__Job__r.Project__r.Project_Name__c,
       sitetracker__Job__r.Project__r.Address__c,
       Item_Name__r.Item_Id__c,
       Item_Name__r.sitetracker__Primary_UoM__c,
       Subie_Rate__c,
       Total_Actual_Amount__c,
       LastModifiedDate
FROM sitetracker__Production_Plan_Line__c
WHERE sitetracker__Job__r.sitetracker__Job_Status__c = 'Invoiced'
  AND (LastModifiedDate >= 2026-08-01T00:00:00Z
       OR sitetracker__Job__r.LastModifiedDate >= 2026-08-01T00:00:00Z)
```

To confirm: `Total_Job_Amount__c` and `Business_Flow_Type__c` are added beyond the Test 3
field list. The business-flow fallback (project → ticket → job) is an iFlow mapping rule,
not SOQL. GL code (73020), tax code (GST10) and quantity (1) — hardcoded in the current
file — move to SAP-side determination. Negative amounts (credit lines) pass through as-is.
