# FSM Inbound Data Distribution — Build Specification

**For:** Deloitte build team, Apollo programme
**From:** Rajesh Sha, Solution Architecture, Service Stream
**Date:** 6 August 2026
**Status:** Draft for estimation and build planning — pending Design Council confirmation (Friday)

---

## 1. What this document is

This document tells the build team exactly what to build so that data from S/4HANA
reaches every field service system (FSM) automatically. It is written to be built from:
every requirement is numbered, every interface is specified, and every component has
acceptance criteria. Where a decision is still open, it is listed in section 14 with an
owner — nothing else in this document is open.

Words used (the only special terms in this document):

| Term | Meaning |
|---|---|
| FSM | A field service system — JAMS, ServiceNow, Sitetracker, and others |
| CPI | SAP Integration Suite (Cloud Integration) — the middleware. All build in this document happens here |
| Standard message | One common message format for a business record, used for every FSM (the programme's existing "canonical model") |
| Insert-or-update | Create the record if it does not exist, update it if it does. Receiving the same message twice must cause no harm |
| Data set | One kind of business data. There are seven: service orders, projects, customer invoices, supplier invoices/RCTI, project time & equipment, available stock, purchase orders |
| Timed check | A CPI job that runs on a schedule and asks S/4HANA "what changed since I last asked?" |
| Event | A small notice S/4HANA sends out the moment a record changes. It carries the record's ID only, not the data |

## 2. Background in two paragraphs

Today JAMS reads its S/4-related data by running SQL queries against the Jobpac data
warehouse. That warehouse is decommissioned at S/4 go-live. The decided replacement
direction is that field systems consume APIs, not databases. The open design question —
being settled at Friday's Design Council — is *where the work happens*: each FSM building
its own scheduled data-fetching (Option B), or CPI detecting changes once and delivering
to every FSM (Option D). This specification describes Option D.

The principle throughout: **CPI does the work once; each FSM only receives.** S/4HANA
remains the single source of truth. CPI never stores business data. No system ever reads
or writes another system's database.

## 3. What already exists (build on it, do not rebuild it)

| Existing item | State | Used here for |
|---|---|---|
| S/4 read APIs for all seven data sets (the "passthrough" set) | Designed and proven (200 OK test on service orders) | Reading full records (R-B2, R-B4) |
| Standard message format (canonical model) | Designed for the FSM-to-S/4 direction | The message body sent to FSMs (R-B4) |
| Message queue capability (JMS) in CPI | In use by the existing design | Per-FSM delivery queues (R-B6) |
| Error logging flow in CPI | In use by the existing design | Extended, not replaced (R-B9) |
| The "Response Type 2" pull endpoint (registered query per system) | Designed | Kept unchanged, as the fallback for FSMs that cannot receive (R-I5) |
| S/4 event channel `EMIS_COM_0092` | **Active in the tenant today**, with one working topic binding (ServiceEntrySheet) | Receiving change events (R-B1) |

## 4. What to build — component list

All build is inside CPI, using only standard delivered CPI adapters. There are no custom
platform components, no databases, and no AI services anywhere in this design.

| ID | Component | Quantity |
|---|---|---|
| B1 | Event receiver flow | One per event-enabled data set (up to 7) |
| B2 | Timed check flow | One, run with different settings per data set |
| B3 | Last-run-time store | One (CPI's built-in variable store) |
| B4 | Message builder | One |
| B5 | Subscription list + router | One list (configuration), one router flow |
| B6 | Delivery queues | One per FSM |
| B7 | Delivery senders | One per FSM: JAMS, ServiceNow ITSM, ServiceNow Defence, Sitetracker (when confirmed), file |
| B8 | Re-send tool | One |
| B9 | Error logging extension | Extension of the existing flow |

The receiving systems build almost nothing. The full FSM-side list is: JAMS builds six
receiving web services (section 9.1); ServiceNow and Sitetracker are configured by their
own administrators, with zero development (sections 9.2, 9.3).

## 5. How the whole thing works — the one flow to understand

Every delivery, for every data set and every FSM, follows the same seven steps:

1. **A record changes in S/4HANA.** It does not matter how — created by an FSM's message,
   typed in by a user, or posted by another system.
2. **CPI finds out**, in one of two ways: S/4 sends an event naming the record (B1), or
   the timed check asks for records changed since last time (B2).
3. **CPI reads the full record fresh from S/4** using the existing read API. This is done
   even when an event arrives, because events carry only the ID. Result: what CPI sends
   is always the current state, even if events arrive late or out of order.
4. **CPI wraps the record in the standard message** (B4), adding the tracking fields
   listed in section 8.
5. **CPI checks the subscription list** (B5): which FSMs want this data set, for this
   contract? One copy of the message goes onto each matching FSM's queue (B6). An FSM
   that is not subscribed, or whose contracts do not match, never receives the message.
6. **The FSM's delivery sender (B7) sends the message to that FSM** in the way that FSM
   accepts — web service call, or file. If sending fails, CPI retries automatically.
7. **The FSM saves the record itself**: create if new, update if existing, matched on
   the S/4 document number. Saving the same message twice changes nothing.

## 6. Requirements — change detection

- **R-B1.1** Build one event receiver flow per event-enabled data set. It subscribes to
  that data set's topic on the existing channel `EMIS_COM_0092` (topics listed in
  section 13).
- **R-B1.2** On receiving an event, the flow must read the full record from the existing
  S/4 read API and pass it to the message builder. The event's own contents are never
  forwarded to any FSM.
- **R-B2.1** Build one timed check flow. For each data set it must call the existing S/4
  read API with the filter "changed after {last run time}", read all pages of results,
  and pass each record to the message builder.
- **R-B2.2** The last run time (B3) must only move forward after every record from the
  current run has been placed on the delivery queues. If the run fails part-way, the next
  run repeats it. Repeats are safe because saving is insert-or-update.
- **R-B2.3** Run schedule per data set is configuration, not code. Starting values:
  every 5 minutes for service orders and stock; every 15 minutes for projects; every
  60 minutes for invoices and purchase orders. (To be confirmed — see section 14.)
- **R-B2.4** Each data set uses either events or the timed check as its main detection —
  set by configuration. Both paths feed the same message builder, so changing a data set
  from one to the other later requires no rebuild.

## 7. Requirements — subscription list and routing

- **R-B5.1** The subscription list is configuration (not code), changed only through the
  normal transport/change process. One row per FSM per data set:

| Field | Example | Meaning |
|---|---|---|
| FSM name | `SN-DEFENCE` | Which system this row is for |
| Data set | `SERVICE_ORDER` | Which kind of data |
| Contract scope | `DEF-*` | Which contracts this FSM may receive. **This is the security boundary** |
| Delivery method | `WEB_SERVICE` or `FILE` or `PULL` | How this FSM receives |
| Address | credential + URL alias | Where to send, and which login to use |
| Active | `yes` / `no` | Switch a row off without deleting it |

- **R-B5.2** The router must deliver a message only to FSMs with a matching active row
  whose contract scope matches the record's contract. There must be no other path by
  which data reaches an FSM. This single rule is how Defence data separation is enforced,
  and it must be demonstrable in testing (T6).
- **R-B5.3** Starting subscription rows are in section 13.2. Adding an FSM or a data set
  later must require only new rows and (for a new FSM) one new delivery sender — no
  change to any other component.

## 8. Requirements — the message

- **R-B4.1** Every message sent to every FSM has the same two parts: tracking fields and
  the record itself (in the standard message format already designed).

Tracking fields, all mandatory:

| Field | Content |
|---|---|
| Message ID | Unique per message |
| Correlation ID | The S/4 record key + change reference. The same value the FSM received in its acknowledgement if the record originated from its own request — this is how an FSM matches a delivery to what it sent |
| Data set | e.g. `SERVICE_ORDER` |
| Record ID | The S/4 document number — the matching key for insert-or-update |
| Contract ID | The contract this record belongs to |
| Changed at | Date/time of the change in S/4 |
| Sent at | Date/time CPI sent the message |
| Format version | Starts at `1.0`; only additions are allowed within a major version |

- **R-B4.2** Messages for the same record must be delivered in order. If an older change
  somehow arrives after a newer one, the receiving side must keep the newer one (compare
  "changed at"). The JAMS endpoints must implement this rule; ServiceNow and Sitetracker
  handle it through their standard matching-on-ID behaviour plus the delivery order.

## 9. Requirements — delivery, per receiving system

### 9.1 JAMS (web service push)

- **R-J1** CPI sends each message as an HTTPS POST to a JAMS web service. There are six
  services, one per data set JAMS subscribes to. **The JAMS team names the exact paths**;
  CPI treats them as configuration.
- **R-J2** Login: an OAuth 2.0 system user issued by the JAMS team (certificate login is
  the fallback if JAMS's stack cannot issue OAuth).
- **R-J3** Field mapping: one written mapping table per data set — standard message field
  → JAMS field — agreed and signed off by both the CPI team and the JAMS team **before**
  build starts. The mapping tables are part of this specification's appendices once
  agreed.
- **R-J4** JAMS's endpoints save with insert-or-update matched on the S/4 document
  number, and reply "saved" (HTTP 200) or "rejected, with a reason" (HTTP 400). A
  rejection reason must say which field failed and why.
- **R-J5** JAMS builds nothing else: no scheduler, no data fetching, no filtering, no
  retry logic. (JAMS team's own estimate: equal effort to the pull client this replaces.)

### 9.2 ServiceNow — ITSM and Defence (built-in import push)

- **R-S1** CPI sends records to ServiceNow's built-in Import Set API — HTTPS POST to
  `/api/now/import/{staging table}`, one staging table per data set. This is a standard
  ServiceNow feature; **no ServiceNow development is permitted or needed.**
- **R-S2** A ServiceNow administrator configures: the staging tables, the transform maps
  (which match on the S/4 document number, giving insert-or-update automatically), and an
  integration user with OAuth 2.0 login.
- **R-S3** ITSM and Defence are two separate ServiceNow instances: separate subscription
  rows, separate queues, separate logins. Defence rows carry Defence contract scope only.
- **R-S4** The Import Set API reports success or failure per row; row failures must be
  written to the error log (R-B9) with the reason ServiceNow returned.

### 9.3 Sitetracker (standard Salesforce push) — build when the need is confirmed

- **R-T1** CPI sends records using Sitetracker's standard Salesforce interface: an HTTPS
  "save by external ID" call, where the external ID field holds the S/4 document number —
  giving insert-or-update automatically. Bulk interface for first loads.
- **R-T2** A Sitetracker administrator configures: the ID field per data set, an
  integration user, and a connected app for OAuth 2.0 login. No Sitetracker development.

### 9.4 File delivery (for an FSM with an import job but no API)

- **R-F1** CPI writes one file (CSV or JSON — per FSM choice) per data set per interval
  to that FSM's own folder on the SFTP server, named `{data set}_{date-time}`. Tracking
  fields are included as columns. The FSM's existing import job consumes the folder.

### 9.5 Pull (for an FSM that cannot receive at all)

- **R-I5** The existing Response Type 2 pull endpoint remains available unchanged. An FSM
  on "PULL" in the subscription list gets no delivery sender; it fetches on its own
  schedule. This is the documented exception, not the pattern.

### 9.6 What is forbidden

- **R-X1** No component may write to, or read from, any FSM's database directly — even
  though CPI technically can. All delivery goes through the interfaces above.
- **R-X2** No intermediate database or data store holding business data may be created
  anywhere in this design. CPI holds only: configuration, last-run times, and messages
  currently in transit.

## 10. Requirements — failures and recovery

- **R-E1** Each FSM has its own delivery queue. One FSM being down must not delay any
  other FSM.
- **R-E2** Failed sends are retried automatically with increasing gaps (start 2 seconds,
  double each time, stop after about 1 hour of attempts).
- **R-E3** A message that exhausts its retries moves to that FSM's error queue, and an
  alert goes to that FSM's named support contact. Nothing is silently dropped.
- **R-E4** The re-send tool (B8) must be able to: (a) re-send everything on an error
  queue after the FSM recovers, and (b) re-send all records of a data set changed between
  two dates — which is also how first loads and re-syncs are done.
- **R-E5** All errors, with FSM name, data set, record ID and reason, land in the
  existing error log so both directions of integration are monitored in one place.

## 11. S/4HANA configuration tasks (configuration only — no development)

These are done in standard S/4HANA Cloud apps by whoever holds the configuration role —
listed here so the build plan includes them, not because they are build:

1. Communication user and system for CPI (exists for the read APIs — reuse).
2. One communication arrangement per read API (exists — reuse).
3. Eventing communication arrangement `SAP_COM_0092` → the channel. **Already done —
   channel `EMIS_COM_0092` is active in the tenant.**
4. Outbound topic bindings, one per data set, on that channel — pick the object type,
   tick Created and Changed. One (ServiceEntrySheet) is already bound and working; the
   remaining list is in section 13.1.

## 12. Environments, deployment, testing

- **R-D1** Everything (flows and the subscription list) moves DEV → TEST → PROD through
  SAP's standard transport process. No manual production changes.
- **R-D2** Each environment points at its own S/4 tenant and its own FSM test instances,
  through per-environment address aliases.

Minimum test set (each must pass in TEST before any production deployment):

| # | Test | Pass condition |
|---|---|---|
| T1 | Change a service order in S/4 | Every subscribed FSM receives it once, correct fields, within the agreed time |
| T2 | Send the same message twice | Receiving system state is identical to receiving it once |
| T3 | Deliver two changes to one record out of order | The newer change wins on the receiving side |
| T4 | Take one FSM offline during a change, bring it back | That FSM catches up automatically; no other FSM was delayed; nothing lost |
| T5 | Exhaust retries | Message is on the error queue, alert received by the named contact, re-send tool recovers it |
| T6 | Create a record on a non-Defence contract | Demonstrate it cannot reach the Defence queue — by design, not by luck |
| T7 | First load of one data set into one FSM by date range | Counts match between S/4 and the FSM |
| T8 | Switch a data set from timed check to events (or back) | Configuration change only; no rebuild; deliveries continue |

## 13. Reference lists

### 13.1 Event bindings to add (on the existing active channel)

| Data set | Object type to select | Events |
|---|---|---|
| Service Orders | `ServiceOrder` | Created, Changed |
| Enterprise Project | `EnterpriseProject` | Created, Changed |
| Customer Invoice | `BillingDocument` | Created, Changed |
| Supplier Invoice / RCTI | `SupplierInvoice` | Created, Changed |
| Purchase Orders | `PurchaseOrder` | Created, Changed |
| Available Stock | `MaterialDocument` (goods movements change stock) | Created — verify suitability; timed check if not |
| Project Time & Equipment | No event assumed — timed check | — |

The binding dialog's object-type list in the tenant is the final authority on names.
Any data set without a usable event simply stays on the timed check — no data set is at
risk either way.

### 13.2 Starting subscription rows (to be confirmed with system owners)

| Data set | JAMS | SN ITSM | SN Defence | Sitetracker |
|---|---|---|---|---|
| Service Orders | Yes — own contracts | Yes | Yes — Defence contracts only | To confirm |
| Enterprise Project | Yes | — | Yes | To confirm |
| Customer Invoice | Yes | — | — | To confirm |
| Supplier Invoice / RCTI | Yes | — | — | — |
| Project Time & Equipment | Yes | — | Yes | To confirm |
| Available Stock | Yes | — | Yes | — |
| Purchase Orders | Yes | — | — | — |

## 14. Open items — the only undecided things (with owners)

1. Exact event names per data set — lookup in the tenant binding dialog (Rajesh, before
   build).
2. Timed-check schedule per data set — confirm with JAMS operational needs (Trajce).
3. JAMS endpoint paths, login method, and the six field-mapping tables (Trajce + CPI
   team, before build — see R-J3).
4. ServiceNow Import Set approach acceptable under Defence security posture; ITSM data
   need confirmation (Chamila).
5. Sitetracker: whether needed this phase; owner to be named.
6. Message-volume estimate against contract volumes, for Integration Suite metering
   (Rajesh).

## 15. Out of scope

- Any change to the FSM-to-S/4 direction (the existing canonical flow) — unchanged.
- Any intermediate database (forbidden — R-X2).
- Advanced Event Mesh — not required; the included event capability is already active.
- Any AI service — none is used anywhere in this design.

## 16. Definition of done

The build is complete when: all tests T1–T8 pass in TEST; JAMS receives all seven data
sets in production; the error queues are empty after one week of normal running; the
weekly count comparison between S/4 and each FSM matches; and the run book (queues,
alerts, re-send tool) is handed over to the support team.
