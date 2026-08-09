# Handover — FSM Inbound Data Distribution: state, decisions and next configuration steps

**Purpose:** everything a new session or engineer needs to continue the SAP CPI
configuration for returning S/4HANA business data to the field systems. This captures the
full state of the design work done on branch `claude/fsm-inbound-orchestration-pifq6f`
(PR #6 on `rajesh-sha/Test`), current as of 7 August 2026.

---

## 1. The decision context, in four lines

1. **Decided earlier (not to be re-opened):** field systems consume APIs, not databases
   (Option B beat Option A/JDW-replacement and Option C/Business Data Cloud).
2. **Proposed and designed in this work (for the Friday Design Council):** **Option D** —
   CPI detects each S/4 change once, reads the full record, filters by a central
   subscription list, and delivers to every subscribed field system. Option B's pull
   endpoint stays as the fallback delivery method.
3. **Considered and set aside:** Option E (fully event-driven delivery — field systems
   subscribing to the broker directly). Ruled out as the rule because notices carry IDs
   only, the broker cannot filter by contract, and it cannot convert formats. Kept as a
   per-system variant for later.
4. **Ruled out absolutely:** any direct write to a field system's database (CPI's JDBC
   adapter *can* — SAP's API-first guidance and application-layer reasons say don't), and
   any new intermediate business database.

## 2. Where everything lives

All on branch `claude/fsm-inbound-orchestration-pifq6f`, PR #6 (draft), `rajesh-sha/Test`:

| File | What it is |
|---|---|
| `docs/FSM-Inbound-Data-Distribution-Technical-Design.docx` | **The master technical design** — 15 sections incl. full naming conventions. Start here |
| `docs/fsm-inbound-build-specification.md` | Numbered requirements (R-*), tests T1–T8, definition of done — for the delivery partner |
| `docs/fsm-integration-target-architecture.md` | Component architecture (C1–C14), message design, security, onboarding runbook |
| `docs/fsm-inbound-option-d-research.md` | The research paper answering the four original questions, with sources |
| `docs/JAMS-WriteBack-Callback-S4-Key-Design-Decision-2.pptx` | The ARB deck, 25 slides in presenting order — original 14 untouched, Option D block added |
| `web/fsm-inbound-recommended-architecture.html` | Plain-language web briefing pack (5 sections + appendix) |

## 3. Verified tenant state (all checked by screenshot during this work)

### 3.1 BTP global account (SERVICE STREAM HOLDINGS PTY LTD)
- **SAP Integration Suite, Event Mesh** — plan `message-client`: assigned to 1 subaccount,
  quota assigned, global quota unlimited.
- **SAP S/4HANA Cloud Extensibility** — plans `api-access` and `messaging`: Commercial
  Type **none** (included with the S/4 subscription); resource provider registered for
  tenant my435863; "Not assigned" rows just need an administrator assignment, not a
  purchase.

### 3.2 Non-prod Integration Suite (`ss-integration-suite-non-prod…ap10`)
- Capability **"Manage Business Events"** (Event Mesh, EMIS) active.
- Broker: **Ready** — 2.00 GB spool, 1 MB max message, 200 connections, 600 producers,
  600 consumers.
- Message client: **`emis-s4hdev-client`**, namespace **`ssm/s4h/dev`**,
  client ID `79572eb4-0d46-478a-b9c8-418a6da9046b`.
- Queues (current): **`ssm/s4h/dev/Event_POC`** and **`ssm/s4h/dev/s4h-dev-ses-events`**
  (both non-exclusive, both empty). An earlier unprefixed `Test` queue has been
  removed/replaced by the namespaced `Event_POC`.
- CPI flow **`EventMesh_POC`** exists in the *Proof Of Concepts* package — AMQP consumer
  pattern already exercised (settings observed: concurrency 1, prefetch 5, retries 5 →
  REJECTED).
- ~102 integration artifacts deployed on the tenant (existing programme flows).

### 3.3 S/4HANA dev tenant (my435863, client FLA/100)
- Enterprise Event Enablement channel **`EMIS_COM_0092`** (from scenario `SAP_COM_0092`):
  **Active**.
- Event Monitor — outbound topics live, all **Acknowledged**:
  - `ssm/s4h/dev/ce/sap/s4/beh/serviceentrysheet/v1/ServiceEntrySheet/Changed/v1` (5 events) — relevant to supplier invoice/RCTI flow
  - `ssm/s4h/dev/ce/sap/s4/beh/businesspartner/v1/BusinessPartner/Changed/v1` (1) — another team's POC, leave in place
  - `ssm/s4h/dev/ce/sap/s4/beh/WarehouseOrder/TaskCreated/v1` (2) — another team's POC, leave in place
- **Confirmed production topic format:**
  `ssm/s4h/{env}/ce/sap/s4/beh/{object}/v1/{Object}/{Event}/v1`
- The topic-binding dialog offers **183 object types** — it is the final authority on
  event names.

**Licensing conclusion (verified):** nothing new to buy. EMIS is included in the
Integration Suite edition and already active; Advanced Event Mesh is NOT required; no AI
services are used anywhere. The one commercial check remaining is message-volume sizing
under existing Integration Suite metering.

## 4. Naming conventions (agreed in the design — use these when creating anything)

- Namespace: `ssm/s4h/{env}` (env = dev, tst, prd) — observed pattern.
- Intake queues (broker, S/4→CPI): `ssm/s4h/{env}/{data-set-code}-events`
  e.g. `ssm/s4h/dev/service-order-events`.
- Dead-message queue: `ssm/s4h/{env}/dmq` — one per environment, **mandatory** (the
  queue dialog default "None" silently discards failed notices — never use it).
- Data-set codes: `service-order`, `enterprise-project`, `customer-invoice`,
  `supplier-invoice`, `time-equipment`, `stock`, `purchase-order`,
  `job-financial-summary` (list-form: `SERVICE_ORDER`, … `JOB_FIN_SUMMARY`).
- CPI package: *SS S4H FSM Distribution*. Flows: `FSMD_01_NoticeReceiver_{DataSet}`,
  `FSMD_02_TimedCheck`, `FSMD_03_MessageBuilder`, `FSMD_04_Router`,
  `FSMD_05_Sender_{System}`, `FSMD_06_Resend`.
- CPI delivery queues (JMS, CPI→FSM): `FSMD_{SYSTEM}` + `FSMD_{SYSTEM}_ERR`
  (JAMS, SN_ITSM, SN_DEF, SITETRACKER).
- Credentials: `FSMD_{SYSTEM}_{ENV}`. Last-run variables: `FSMD_LASTRUN_{DATASET}`.
- JAMS endpoints (JAMS's final choice): `/api/s4/{data-set-code}`.
- File drops: `/inbound/{data-set-code}/{data-set-code}_{yyyymmdd-hhmmss}.csv`.

## 5. Next configuration steps, in order

1. **S/4 (config only, ~2 min each):** in "Configure Channel Binding" on `EMIS_COM_0092`,
   add outbound bindings — `ServiceOrder`, `EnterpriseProject`, `BillingDocument`,
   `SupplierInvoice`, `PurchaseOrder` (Created+Changed each), `MaterialDocument`
   (Created; verify suitability for stock, else timed check). No binding for
   time-equipment or job-financial-summary (timed-check data sets; the latter is derived
   from project + journal entry reads).
2. **Broker:** create intake queues per naming above (non-exclusive, 1 MB, max
   redelivery 5, dead-message queue `ssm/s4h/dev/dmq` — create the DMQ first, TTL
   604800 s). Subscribe each queue to its data set's topics. Replace
   `s4h-dev-ses-events` with `supplier-invoice-events` (subscribing to both
   SupplierInvoice and ServiceEntrySheet topics) when build starts.
3. **CPI:** create package and flows per naming; consumer settings: concurrency 1,
   prefetch 5, consume-expired off, retries 5 → REJECTED. Every notice triggers a full
   read of the record from the released S/4 API (never forward notice content). Then
   builder → router (subscription list) → JMS delivery queues → senders.
4. **Subscription list** (configuration under transport): rows per system × data set ×
   contract scope × delivery method × address alias × active. Starting matrix is in the
   design doc §7; Defence scope = Defence contracts only — this is the security boundary
   and must pass test T6.
5. **Receiving systems:** JAMS six endpoints (contract in design doc §11.1 — field lists
   and paths to be signed off with Trajce before build); ServiceNow staging tables +
   transform maps (admin config); Sitetracker external-ID fields + connected app (when
   confirmed).
6. **Tests:** T1–T8 in the build specification §14 must pass in TEST before production.

## 6. Open items (owners)

1. Exact event names per data set — lookup in the binding dialog (Rajesh).
2. Timed-check schedule per data set — JAMS operational needs (Trajce). Starting values:
   5 min service orders/stock, 15 min projects, 60 min invoices/POs.
3. JAMS paths, login method, six field lists — written sign-off before build
   (Trajce + CPI team).
4. ServiceNow Import Set approach under Defence security posture; ITSM need (Chamila).
5. Sitetracker: needed this phase? Owner to be named.
6. Message-volume estimate vs Integration Suite metering (Rajesh).

## 7. Key design rules a new session must not break

- CPI never stores business data — configuration, last-run times and in-transit messages only.
- No component reads or writes any field system's database. No intermediate database.
- Every delivery is create-or-update on the S/4 document number; newest change wins;
  duplicates are harmless by design.
- Events carry the record ID only; CPI always re-reads the full record before sending —
  the full-payload read pattern. Notice and timed-check paths produce identical
  downstream processing.
- Contract filtering happens only in the router via the subscription list — no other
  path to a field system may exist.
- Every failure surfaces: delivery error queues and the broker dead-message queue both
  alert a named owner; nothing is silently dropped.
- Response Type 1 (acknowledgement callback) and Response Type 2 (pull endpoint) from the
  original design are unchanged; the business data distribution is additive.
