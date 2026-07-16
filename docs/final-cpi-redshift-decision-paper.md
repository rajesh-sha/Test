# SAP CPI ↔ Amazon Redshift Integration — Final Architecture Decision Paper

**Date:** 2026-07-16 | **Audience:** Architecture Review Board
**Basis:** claims fact-checked against primary SAP and AWS documentation (19 of 20 confirmed by 3 independent verifications each; 1 refuted and excluded).

## 1. Executive summary

**Direct JDBC from SAP CPI to Amazon Redshift is not possible in any network topology.** SAP's official documentation does not list Redshift among the JDBC receiver adapter's supported databases, and a Redshift JDBC driver cannot be uploaded to the CPI tenant (only MSSQL, Oracle, IBM DB2, MariaDB). This invalidates Option A (Cloud Connector into the AWS VPC) and Option C (whitelisting CPI egress IPs) — the blocker is the adapter/driver layer, not the network. Redshift in Servicestream is additionally private by design, so no public endpoint will exist.

**Recommendation:** integrate via the **Amazon Redshift Data API over HTTPS, fronted by API Gateway + Lambda**, with S3 staging + `COPY` for bulk volumes. The cluster stays private, no driver or jumphost is needed, no database passwords leave Secrets Manager/IAM, and API Gateway provides the security-vetted managed ingress required. The only evaluated option fully supported by both vendors.

## 2. Options evaluated — verdicts

| # | Option | Verdict | Rationale |
|---|--------|---------|-----------|
| A | Cloud Connector + CPI JDBC adapter | ❌ Not feasible | Redshift unsupported by CPI JDBC adapter; driver cannot be uploaded; would also need an infra-maintained EC2 jumphost. |
| B | Redshift Data API over HTTPS (fronted by API Gateway + Lambda) | ✅ **Recommended** | HTTPS service endpoint; no driver, no persistent connection; cluster stays private; Secrets Manager/IAM auth; transactional batching + idempotent retries. |
| C | Whitelist CPI egress IPs → public Redshift JDBC | ❌ Not feasible | Same adapter blocker; no static CPI egress IPs (KBA 3209308); private-by-design policy forbids a public endpoint. |
| D | CPI → internal Boomi → JDBC → Redshift | ⚠️ Fallback only | Adds a second middleware platform; Boomi→Redshift leg unvalidated; still needs Cloud Connector + vetted ingress. |
| E | AppFlow SAP OData/ODP → S3 → Redshift | ✅ Evaluate (extraction flows) | Purpose-built SAP→AWS extraction with PrivateLink; bypasses CPI; check SAP Note 3255746 ODP licensing. |

## 3. Key evidence (validated)

- **CPI JDBC adapter supported databases:** DB2, MSSQL, Oracle, PostgreSQL, SAP HANA, SAP ASE, MariaDB — Redshift absent through 2026 (SAP Help; KBA 3318663). Cloud Foundry cloud scope = Amazon RDS for PostgreSQL/MSSQL/Oracle only.
- **Driver uploads:** only MSSQL/Oracle/DB2/MariaDB driver types deployable — no Redshift driver (SAP Help "Configure JDBC Drivers").
- **PostgreSQL-driver workaround:** "not tested and not supported" by AWS; Redshift wire protocol derives from PostgreSQL 8.0.2; no vendor support at incident time.
- **Redshift Data API:** HTTPS, async (ExecuteStatement → DescribeStatement → GetStatementResult), reaches private clusters and Serverless, Secrets Manager/IAM temporary credentials, BatchExecuteStatement transactions, ClientToken idempotency (8 h).
- **CPI signing:** no native SigV4 in CPI — custom Groovy or (preferred) API Gateway front-end with API key/Cognito so CPI makes a plain REST call.

## 4. Team discussion points — resolved

1. **"CPI supports PostgreSQL data source":** true, but SAP defines "PostgreSQL (Cloud)" as Amazon RDS for PostgreSQL, not Redshift. Using it against Redshift is the unsupported workaround.
2. **Shared blog "Connect to AWS Redshift database from BI4" (2015):** about SAP BusinessObjects BI 4.1, not CPI — works by copying the Redshift .jar onto a server you control, which CPI does not allow.
3. **"Redshift is private by design; jumphost required":** eliminates Option C permanently; adds jumphost tax to A/D. The Data API needs no jumphost — API Gateway + Lambda is the vetted managed ingress.
4. **Draft slide deck (DB → S/4HANA via CPI JDBC/Cloud Connector):** valid for on-prem Oracle/MSSQL only; the flow diagram's Redshift substitution is not possible. Keep timer/mapping/S4 API stages; replace the JDBC leg with CPI —HTTPS→ API Gateway + Lambda → Data API → private Redshift.

## 5. Recommended architecture & approach

**Query/request-response:** SAP CPI (HTTP adapter) → HTTPS → API Gateway (API key/Cognito, WAF, throttling) → Lambda → Redshift Data API → Redshift (private, in VPC).
**Bulk load:** CPI → S3 (presigned URL/SigV4 PUT) → `COPY` into Redshift via the same API.

**iFlow pattern:** submit (ClientToken = message ID) → poll with backoff → fetch (inline for small results, S3 presigned URL for large) → map → continue (e.g., post to S/4HANA APIs). Retries reuse the ClientToken (idempotent); SQL errors route to exception subprocess; all statements CloudTrail-audited.

**Security posture:** no public Redshift endpoint; managed auditable ingress replaces a jumphost; least-privilege IAM; no long-lived DB credentials outside Secrets Manager; TLS 1.2+ end-to-end.

**Plan:** Phase 0 approvals + quota verification (1–2 wks) → Phase 1 AWS foundation (2–3 wks) → Phase 2 CPI build (2–3 wks) → Phase 3 test incl. pen-test (2 wks) → Phase 4 cutover/operate (1 wk).

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Data API quotas may not fit payload profile (candidate figures failed fact-check) | Verify in Phase 0; S3 presigned URLs for large results; S3 + COPY for bulk. |
| Async latency vs. synchronous JDBC | Acceptable for integration/ELT; tune polling; Redshift is OLAP in every option. |
| AWS sample repo archived (Jan 2026) | Reference only; own IaC on current runtimes. |
| SAP later ships native AWS/SigV4 adapter | Layered design — swapping the ingress is non-breaking. |
| Boomi fallback unvalidated | If activated: validate Boomi Redshift JDBC support, licensing, sizing first. |

## 7. Decision requested from the ARB

1. **Approve Option B** (Redshift Data API via API Gateway + Lambda) as the standard CPI ↔ Redshift pattern.
2. **Reject Options A and C** and the PostgreSQL-driver workaround as unsupported architectures.
3. **Note Option E** (AppFlow) for evaluation on extraction/replication use cases, subject to ODP licensing review (SAP Note 3255746).
4. **Hold Option D** (Boomi) as fallback only, contingent on separate validation.

---
*Sources: SAP Help Portal (JDBC Receiver Adapter; Configure JDBC Drivers), SAP KBAs 3318663 / 2924589 / 3073748 / 3209308, AWS Redshift Management Guide (Data API) & API References, AWS Big Data blog (REST API for Redshift), AWS AppFlow docs, SAP Community (Groovy SigV4; BI4 blog reviewed and ruled out for CPI). Companion detail: `arb-sap-cpi-redshift-integration-options.md`.*
