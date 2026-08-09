# Decision log — FSM Inbound Data Distribution (Apollo)

Session record, closed 7 August 2026. Branch `claude/fsm-inbound-orchestration-pifq6f`,
PR #6. Full detail behind every entry is in the technical design document and the
handover (`docs/HANDOVER-fsm-inbound-cpi-configuration.md`).

| # | Decision | Status |
|---|---|---|
| D-01 | Field systems consume APIs, not databases (Option B over A and C) | Decided previously — closed, not re-opened |
| D-02 | Option D proposed as the rule: CPI detects each S/4 change once, reads the full record, filters by a central subscription list, and delivers to every subscribed field system. Option B's pull endpoint stays as the fallback delivery method | Proposed — for Friday Design Council |
| D-03 | Option E (field systems subscribing to the event broker directly) is a per-system variant only, not the rule: notices carry IDs only, no contract filtering on the broker, no format conversion | Assessed and set aside |
| D-04 | No direct write to any field system's database, ever — CPI's JDBC adapter can, SAP's API-first guidance and application-layer reasons say don't | Ruled out |
| D-05 | No intermediate business database anywhere; CPI holds configuration, last-run times and in-transit messages only; S/4 remains the single source of truth | Ruled out / rule |
| D-06 | Full-payload read pattern: events carry the record ID; CPI always re-reads the full record from the released S/4 API before distributing. Notice and timed-check paths produce identical downstream processing | Adopted |
| D-07 | Delivery is create-or-update matched on the S/4 document number; newest change wins; duplicates harmless. Per-system queues with automatic retry, error queue and named-owner alert; nothing dropped silently — including a mandatory dead-message queue on every broker intake queue | Adopted |
| D-08 | Contract-scope filtering happens only in the CPI router via the subscription list — the single enforcement point for Defence data separation, provable by test T6 | Adopted |
| D-09 | Field-system impact: configuration only (ServiceNow Import Set, Sitetracker Salesforce interface, file drop, or existing pull), except six small JAMS receiving web services — one path per data set, contract agreed in writing before build | Adopted |
| D-10 | Naming conventions adopted: namespace `ssm/s4h/{env}`; intake queues `ssm/s4h/{env}/{data-set}-events`; dead-message queue `ssm/s4h/{env}/dmq`; CPI flows `FSMD_01…06`; delivery queues `FSMD_{SYSTEM}`(+`_ERR`); credentials `FSMD_{SYSTEM}_{ENV}` | Adopted |
| D-11 | Licensing position verified: EMIS included in the Integration Suite edition and already active; Advanced Event Mesh not required; S/4 extensibility plans at commercial type none; no AI services anywhere. One open commercial check: message-volume sizing | Verified |
| D-12 | Eight data sets in scope, including the derived job financial summary (composed from project + journal entry reads; no event binding of its own) | Adopted |
| D-13 | Response Type 1 (acknowledgement callback) and Response Type 2 (pull endpoint) are unchanged; the business data distribution is additive | Adopted |
| D-14 | Tenant evidence recorded as the build starting point: channel `EMIS_COM_0092` active with three Acknowledged topics; broker Ready with message client `emis-s4hdev-client` on `ssm/s4h/dev`; `EventMesh_POC` consumer flow exists | Recorded |

Open items with owners are in the handover §6. Deliverables index is in the handover §2.
