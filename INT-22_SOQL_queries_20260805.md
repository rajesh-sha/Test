# INT-22 WBSCreateUpdate — SiteTracker pull queries (SAP CPI Salesforce adapter)

Companion to `INT-22_Contract_Reference_Mapping_20260805.xlsx`. One delta pull query per
contract, targeting the direct SiteTracker-to-SAP-CPI pattern (no Redshift layer).
`${lastSuccessfulPullTimestamp}` is the CPI variable holding the last successful pull
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
  AND LastModifiedDate >= ${lastSuccessfulPullTimestamp}
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
  AND LastModifiedDate >= ${lastSuccessfulPullTimestamp}
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
  AND LastModifiedDate >= ${lastSuccessfulPullTimestamp}
```

To confirm: parent-to-child relationship name (assumed `sitetracker__Activities__r`), exact
Activity `Name` values for ID66/ID164, `Client__c` value ('nbn' vs 'NBN'), `Job_Type__c`
API name.
