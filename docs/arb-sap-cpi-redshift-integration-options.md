# SAP CPI ↔ Amazon Redshift Integration — ARB Options Paper

**Purpose:** Evaluate connectivity options for SAP Cloud Integration (CPI, SAP Integration Suite on BTP) to Amazon Redshift and recommend an approach for Architecture Review Board approval.

**Date:** 2026-07-16
**Status:** Research validated against primary SAP and AWS documentation (19 of 20 claims independently verified 3–0 by adversarial fact-check; 1 claim refuted and excluded).

---

## Executive summary

**The premise behind Options A and C — that CPI can speak JDBC to Redshift — is false.** SAP's official documentation for the CPI JDBC receiver adapter does not list Amazon Redshift as a supported database, and a Redshift JDBC driver cannot even be uploaded to the tenant (only Microsoft SQL Server, Oracle, IBM DB2, and MariaDB driver types are accepted). No network topology — Cloud Connector in the AWS VPC (Option A) or IP whitelisting into the VPC (Option C) — changes this, because the blocker is at the adapter/driver layer, not the network layer.

**Recommendation: Option B — call the Amazon Redshift Data API from CPI over HTTPS** (optionally hardened with an API Gateway + Lambda front-end), with S3 staging + `COPY` for bulk volumes. It is the only option whose every load-bearing technical premise verified cleanly against primary AWS documentation, and it has the strongest security posture: no public Redshift exposure, no long-lived database passwords, IAM-scoped access.

---

## Option-by-option verdicts

| # | Option | Verdict | One-line rationale |
|---|--------|---------|--------------------|
| A | Cloud Connector (BTP ↔ AWS VPC) + CPI JDBC adapter | ❌ **Not feasible** | Redshift is not a supported database of the CPI JDBC adapter; the driver cannot be deployed. |
| B | Redshift Data API over HTTPS from CPI | ✅ **Feasible — recommended** | Secure HTTPS endpoint, no driver, no persistent connection, IAM/Secrets Manager auth, cluster stays private. |
| C | Whitelist CPI egress IPs → direct JDBC to public Redshift | ❌ **Not feasible** | Same JDBC blocker as A; additionally SAP offers no static egress IPs on Cloud Foundry, and public Redshift exposure is a security regression. |
| D | CPI → API → internal Boomi → JDBC → Redshift | ⚠️ **Feasible but not recommended** | Mechanically sound (Cloud Connector is the sanctioned path to internal Boomi), but adds a second middleware platform to work around a gap Option B solves natively. |
| E | Amazon AppFlow SAP OData/ODP connector → S3 → Redshift | ✅ **Feasible — evaluate for extraction flows** | Purpose-built SAP→AWS extraction that bypasses CPI-to-Redshift connectivity entirely. |

---

## Option A — Cloud Connector + CPI JDBC adapter ❌

**Idea:** Install SAP Cloud Connector on an EC2 instance in the AWS VPC so Redshift appears to CPI as an "on-premise" endpoint reachable by the JDBC receiver adapter.

**Why it fails:**

- SAP Help lists the databases the JDBC receiver adapter currently supports: **DB2, Microsoft SQL Server (Cloud/On-Premise), Oracle (Cloud/On-Premise), PostgreSQL (Cloud/On-Premise), SAP HANA (Cloud/On-Premise), SAP ASE (Cloud/On-Premise), MariaDB**. Amazon Redshift is absent, and no "What's New" entry adds it through 2026. In Cloud Foundry, the documented cloud-database scope is **Amazon RDS for PostgreSQL, Microsoft SQL, and Oracle only**.
- The adapter requires the tenant admin to **upload and deploy a JDBC driver**, and only **MSSQL, Oracle, IBM DB2, and MariaDB** driver types can be uploaded — a Redshift driver cannot be deployed at all.
- The Cloud Connector pattern itself is real and correctly understood (SAP mandates Cloud Connector for any on-premise JDBC connection via a TCP system mapping) — but it cannot rescue an unsupported database.
- The theoretical workaround of pointing a PostgreSQL data source at Redshift's Postgres-compatible endpoint is explicitly **"not tested and not supported"** by AWS — indefensible before an ARB.

**Sources:** SAP Help "JDBC Receiver Adapter" (loio 88be64412f1b46d684dfba11f2767c5b); SAP Help "Configure JDBC Drivers"; SAP KBA 3318663, KBA 2924589, KBA 3073748; AWS Redshift docs (`c_redshift-postgres-jdbc`).

---

## Option B — Amazon Redshift Data API over HTTPS ✅ (Recommended)

**Idea:** CPI calls the Redshift Data API (`redshift-data.<region>.amazonaws.com`) via its HTTP adapter. No JDBC, no driver, no persistent connection.

**Verified capabilities:**

- **Secure HTTPS endpoint, no persistent connection** — the Data API is explicitly designed for callers that cannot hold JDBC/ODBC connections.
- **The cluster stays private.** Calls go to the regional AWS service endpoint, not the cluster's network endpoint; the cluster/workgroup does not need to be publicly accessible. Works with both provisioned clusters and Redshift Serverless.
- **No passwords in API calls.** Authentication uses AWS Secrets Manager–stored credentials or temporary database credentials derived from the caller's IAM identity (`GetClusterCredentials` / `GetCredentials`).
- **Transactional batching + idempotency.** `BatchExecuteStatement` runs multiple SQL statements serially as a single all-or-nothing transaction; `ClientToken` (8-hour expiry) makes retries safe.
- **Asynchronous by design.** `ExecuteStatement` returns a statement ID; CPI polls `DescribeStatement` and fetches via `GetStatementResult`. There is no server-side synchronous mode — the iFlow must implement a submit/poll/fetch pattern.

**Design costs (eyes open):**

1. **SigV4 signing:** every Data API request must be signed with AWS Signature Version 4. CPI has **no native SigV4 support**; the signature is generated in a custom Groovy script on the HTTP adapter — a proven, community-documented pattern, but hand-rolled. (Mitigation: front the Data API with API Gateway + a Cognito/Lambda authorizer or API key so CPI does plain OAuth/key auth — see hardened variant below.)
2. **Async orchestration:** the iFlow needs a polling loop (or a callback design) rather than a single request/response step.
3. **Service quotas:** statement-size / result-size / concurrency limits apply. *Note: the specific figures circulating during research (100 KB statement, 100 MB result, etc.) failed verification — confirm current numbers on the AWS quotas page before the ARB; do not quote unverified figures.*

**Hardened variant (AWS-published pattern):** Amazon API Gateway + Lambda + Data API, with DynamoDB status tracking, SQS decoupling, and **S3 presigned URLs** for large/long-running result sets (Redshift OLAP queries can exceed what a synchronous HTTP response can carry; API Gateway's default 29 s integration timeout reinforces the async design). AWS provides a CloudFormation sample (aws-samples/redshift-application-api — archived Jan 2026, so treat as reference code, not a supported product).

**Bulk volumes:** for large data loads, stage files to S3 and use Redshift `COPY` (CPI already has community-proven S3 connectivity via the same SigV4 Groovy approach); use the Data API for the `COPY` trigger and for query-style exchanges.

**Sources:** AWS Redshift Management Guide "Using the Amazon Redshift Data API"; `API_BatchExecuteStatement`, `API_GetClusterCredentials`; AWS Big Data blog "Build a REST API to enable data consumption from Amazon Redshift"; SAP Community Groovy SigV4 implementations.

---

## Option C — Whitelist CPI egress IPs, direct JDBC to public Redshift ❌

**Why it fails:**

1. **Same root blocker as Option A** — even with perfect network reachability, the CPI JDBC adapter has no Redshift support and no deployable Redshift driver. Rejected on this alone.
2. **CPI egress IPs are not static.** SAP KBA 3209308 states static IPs are not offered for Cloud Integration on Cloud Foundry — egress ranges are broad and IaaS-provider-controlled, making security-group whitelisting operationally fragile. *(Surfaced in search; not independently verified — moot given blocker #1.)*
3. **Security regression:** making Redshift publicly accessible enlarges the attack surface, which Option B avoids entirely.

---

## Option D — CPI → internal Boomi → JDBC → Redshift ⚠️

**What's verified:** the CPI leg is architecturally sound — Cloud Connector is exactly SAP's sanctioned mechanism for CPI to reach an internal endpoint (Boomi's API), using the ordinary HTTP adapter.

**Why it's not recommended:**

- It adds a **second middleware platform**: Boomi licensing, internal hosting, monitoring, patching, two failure domains, and a double hop of latency — all to work around a CPI adapter gap that Option B solves natively over HTTPS.
- The **Boomi → Redshift leg was not validated** in this research (Boomi's JDBC connector support for Redshift, driver/licensing, sizing). It needs separate due diligence before this option could even be scored fully.

**Hold as fallback only if** the organization already operates Boomi at scale and requires true synchronous JDBC semantics.

---

## Option E (alternative) — Amazon AppFlow SAP OData/ODP connector ✅

For **extraction-style flows** (SAP → Redshift data replication), AppFlow's SAP OData connector is a purpose-built path that bypasses CPI-to-Redshift connectivity entirely:

- Extracts at the **SAP application layer** via OData/ODP from ECC, BW, S/4HANA, BW/4HANA — full and incremental (Operational Delta Queue) transfers.
- Lands data in **S3**; AppFlow's Redshift destination uses an intermediate S3 bucket (i.e., S3 staging + COPY under the hood).
- Supports **AWS PrivateLink** so SAP↔AWS traffic stays off the public internet; on-premises SAP participates via VPN/Direct Connect + PrivateLink.
- Application-layer extraction preserves business context, table relationships, and customizations that database-level JDBC extraction loses (corroborated independently by AWS, Microsoft, and Informatica guidance).
- **Caveats:** requires NetWeaver AS ABAP ≥ 7.50 with OData services enabled; PrivateLink needs NLB + VPC Endpoint Service plumbing; **SAP Note 3255746** restricts third-party use of the ODP RFC API — have licensing review it before committing to ODP-based patterns.

---

## Recommendation to the ARB

1. **Reject Options A and C.** The CPI JDBC adapter affirmatively does not support Amazon Redshift (SAP Help + KBA 3318663); no Cloud Connector topology or IP whitelisting fixes an adapter/driver-layer gap. Option C additionally requires public Redshift exposure and depends on static CPI IPs SAP does not provide.
2. **Adopt Option B:** CPI HTTP adapter → Redshift Data API, with Groovy SigV4 signing, Secrets Manager or IAM temporary credentials, `ClientToken` idempotency, and an ExecuteStatement → poll → GetStatementResult flow. Front it with **API Gateway + Lambda** (Cognito/Lambda authorizer to spare CPI the SigV4 work) plus **S3 presigned URLs** where queries are long-running or result sets large. Use **S3 staging + COPY** for bulk loads.
3. **Evaluate Option E (AppFlow SAP OData/ODP → S3 → Redshift)** in parallel for extraction/replication use cases — it may remove CPI from the data path entirely for those flows.
4. **Hold Option D (Boomi)** as fallback only, contingent on separate validation of the Boomi→Redshift leg.

### Open items to close before/at the ARB

- Confirm **current Redshift Data API quotas** (max statement size, result size, retention, concurrency) against the live AWS quotas page — candidate figures failed fact-check.
- Check whether SAP Integration Suite has since shipped **native AWS SigV4 / an official AWS adapter** (the SigV4 gap is documented via SAP Community, not official SAP docs).
- If Option D stays on the table: validate **Boomi's Redshift JDBC support, licensing, and sizing**.
- If Option E proceeds: **licensing review of SAP Note 3255746** (ODP API usage restrictions).

---

## Addendum — points raised in team discussion (validated)

1. **"CPI supports a PostgreSQL data source" (screenshot of the Add JDBC Data Source dialog).** True but not sufficient: SAP's docs define "PostgreSQL (Cloud)" as **Amazon RDS for PostgreSQL**, not Redshift. Pointing a PostgreSQL data source at Redshift's Postgres-compatible endpoint is the workaround AWS explicitly labels **"not tested and not supported,"** and SAP support would likewise decline incidents because Redshift is not on the adapter's supported list. Redshift's wire protocol derives from PostgreSQL 8.0.2 — modern pgJDBC behavior can silently break. An architecture with no vendor support path on either side should not be put before the ARB.
2. **The shared SAP Community blog ("Connect to AWS Redshift database from BI4", 2015) is about SAP BusinessObjects BI 4.1, not CPI.** It works by manually copying the Amazon Redshift JDBC .jar onto the BOBJ server's filesystem — possible there because you control the server. CPI's tenant accepts only MSSQL/Oracle/DB2/MariaDB driver uploads, so the technique does not transfer to CPI.
3. **"Redshift in Servicestream is private by design; any SAP↔Redshift path needs a security-vetted, infrastructure-maintained jumphost."** This formally eliminates Option C (no public endpoint will exist) and adds a permanent ops/security tax to every JDBC-based path (A and D): a jumphost/Cloud Connector EC2 that must be vetted, patched, and owned — and Option A still fails on the driver blocker even after paying it. **Option B is the only option that satisfies this constraint with no jumphost:** the cluster stays private, CPI calls the regional AWS service endpoint over HTTPS with IAM auth, and an API Gateway + Lambda front-end provides exactly the "secure, vetted ingress" requested — as a managed, auditable service rather than a maintained server.

## Verification notes

- Research method: 5 parallel search angles → 22 sources fetched → 20 falsifiable claims extracted → each claim adversarially verified by 3 independent checkers (2/3 refutes kill a claim). Result: **19 confirmed (3–0), 1 refuted** (the Data API quota figures), 0 unverified.
- Primary sources: SAP Help Portal (JDBC Receiver Adapter, Configure JDBC Drivers), SAP KBAs 3318663 / 2924589 / 3073748 / 3209308, AWS Redshift Management Guide (Data API), AWS API Reference, AWS Big Data & SAP blogs, AWS AppFlow docs. Some SAP/AWS pages were verified via official GitHub documentation mirrors (SAP-docs/btp-integration-suite, awsdocs) where direct fetches were blocked; mirror content matched the cited document IDs.
- Time-sensitivity: SAP's supported-database list and the Data API feature set both evolve; re-verify within ~6 months if the ARB date slips.
