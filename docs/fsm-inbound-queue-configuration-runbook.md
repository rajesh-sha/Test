# FSM Inbound — Event Mesh Queue Configuration Runbook (DEV)

**Purpose:** the exact click-by-click values to configure every queue, subscription and
channel binding needed for the FSM Inbound Data Distribution design (Option D). Execute
top to bottom — the order matters. Everything here follows the naming conventions and
settings agreed in `docs/FSM-Inbound-Data-Distribution-Technical-Design.docx` and
`docs/fsm-inbound-build-specification.md` (§13.1/13.1a) on branch
`claude/fsm-inbound-orchestration-pifq6f` (PR #6).

**Where:** SAP Integration Suite non-prod →
`https://ss-integration-suite-non-prod.integrationsuite.cfapps.ap10.hana.ondemand.com`
→ **Configure → Event Mesh → Queues** tab (the screen showing `ssm/s4h/dev/Event_POC`
and `ssm/s4h/dev/s4h-dev-ses-events` today).

**Time needed:** ~30 minutes for all queues and subscriptions; ~15 minutes for the S/4
channel bindings (separate system, Fiori).

---

## 0. Rules before you start

1. **Create the dead-message queue first** (step 1). Every intake queue references it;
   the queue dialog's default of *None* silently discards failed notices and must never
   be accepted.
2. **Do not touch** `ssm/s4h/dev/Event_POC` (this programme's PoC — retire later, step 7)
   or the `BusinessPartner` / `WarehouseOrder` topic bindings on the S/4 channel (other
   teams' PoCs).
3. Everything is created inside the message client's namespace `ssm/s4h/dev` — type the
   full name including the prefix.
4. The topic strings in step 3 follow the confirmed format
   `ssm/s4h/{env}/ce/sap/s4/beh/{object}/v1/{Object}/{Event}/v1`. The S/4 binding dialog
   is the final authority on the `{object}` segment — step 5 verifies each one against
   the Event Monitor and tells you what to do on a mismatch.
   **Verified 7 Aug 2026 in the binding dialog (dev tenant):** `ServiceOrder` and
   `EnterpriseProject` topic names match this runbook exactly as written (closing part
   of open item 1). Dialog tip: the SAP Object Type search is exact-match by default —
   search with wildcards, e.g. `*Service*`, in CamelCase.

## 1. Dead-message queue — create this one first

**Queues tab → Create.**

| Field | Value |
|---|---|
| Queue Name | `ssm/s4h/dev/dmq` |
| Access Type | Non-Exclusive |
| Time to Live (s) | `604800` (7 days — covers a long-weekend outage) |
| Respect Time to Live | On |
| Maximum Redelivery Count | leave default |
| Dead Message Queue | **None** (this *is* the DMQ — the only queue allowed to say None) |
| All other fields | dialog defaults |

No topic subscriptions on this queue — the broker routes rejected messages here itself.

## 2. Intake queues — create six

**Queues tab → Create**, once per row of the table below. Every queue uses the same
settings; only the name differs.

Common settings for all six:

| Field | Value |
|---|---|
| Access Type | Non-Exclusive |
| Time to Live (s) | `604800` |
| Respect Time to Live | On |
| Maximum Redelivery Count | `5` |
| Dead Message Queue | `ssm/s4h/dev/dmq` |
| All other fields | dialog defaults |

Queue names (data sets with events; time-equipment and job-financial-summary have no
queue — they run on the timed check only):

| # | Queue name | Data set |
|---|---|---|
| 1 | `ssm/s4h/dev/service-order-events` | Service Orders |
| 2 | `ssm/s4h/dev/enterprise-project-events` | Enterprise Project |
| 3 | `ssm/s4h/dev/customer-invoice-events` | Customer Invoice |
| 4 | `ssm/s4h/dev/supplier-invoice-events` | Supplier Invoice / RCTI (also takes the ServiceEntrySheet topic — replaces `s4h-dev-ses-events`, see step 7) |
| 5 | `ssm/s4h/dev/purchase-order-events` | Purchase Orders |
| 6 | `ssm/s4h/dev/stock-events` | Available Stock (conditional — only if the `MaterialDocument` binding proves suitable in step 4; otherwise delete this queue and the data set stays on the timed check) |

## 3. Topic subscriptions — per queue

Open each queue (the `>` chevron on its row) → **Subscriptions → Add**, and add these
exact strings. Create the subscriptions *before* the S/4 bindings in step 4 — an event
published while no subscription exists is discarded by the broker.

**`ssm/s4h/dev/service-order-events`**
```
ssm/s4h/dev/ce/sap/s4/beh/serviceorder/v1/ServiceOrder/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/serviceorder/v1/ServiceOrder/Changed/v1
```

**`ssm/s4h/dev/enterprise-project-events`** (four subscriptions — the element-level
events are needed because editing a WBS element does not fire the project-header
`Changed` event; without them an element edit would wait for the timed check. Element
events carry the project ID, so downstream processing is identical: same full-project
read. Delete events deliberately excluded — the design has no delete handling.)
```
ssm/s4h/dev/ce/sap/s4/beh/enterpriseproject/v1/EnterpriseProject/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/enterpriseproject/v1/EnterpriseProject/Changed/v1
ssm/s4h/dev/ce/sap/s4/beh/enterpriseproject/v1/EnterpriseProject/EntProjElmntCrted/v1
ssm/s4h/dev/ce/sap/s4/beh/enterpriseproject/v1/EnterpriseProject/EntProjElmntChgd/v1
```

**`ssm/s4h/dev/customer-invoice-events`**
```
ssm/s4h/dev/ce/sap/s4/beh/billingdocument/v1/BillingDocument/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/billingdocument/v1/BillingDocument/Changed/v1
```

**`ssm/s4h/dev/supplier-invoice-events`** (four subscriptions — the entry-sheet step of
the RCTI flow lands here too; the ServiceEntrySheet/Changed topic is the one already
proven live in the Event Monitor. **Verified in the binding dialog: SupplierInvoice has
no `Changed` event** — only Created and Canceled exist. Canceled is bound because an
RCTI reversal must propagate; the full-record read returns the invoice with its reversal
status and the receiver's insert-or-update stores that current state. In-place changes,
if any, are covered by the timed check.)
```
ssm/s4h/dev/ce/sap/s4/beh/supplierinvoice/v1/SupplierInvoice/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/supplierinvoice/v1/SupplierInvoice/Canceled/v1
ssm/s4h/dev/ce/sap/s4/beh/serviceentrysheet/v1/ServiceEntrySheet/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/serviceentrysheet/v1/ServiceEntrySheet/Changed/v1
```

**`ssm/s4h/dev/purchase-order-events`** (six subscriptions — verified against the
binding dialog. `Approved/v1` is the business trigger for a PO completing its approval
workflow. The item-level events are needed because item edits do not reliably fire the
header `Changed` event — same completeness reasoning as the project element events; all
carry the PO number, so processing is the identical full-PO read. Deliberately not
bound: `ApprovalRejected`, `ItemBlocked`, `ItemUnblocked` — internal workflow states,
covered by the full read and the timed check.)
```
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/Changed/v1
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/Approved/v1
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/ItemCreated/v1
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/ItemChanged/v1
ssm/s4h/dev/ce/sap/s4/beh/purchaseorder/v1/PurchaseOrder/ItemDeleted/v1
```

**`ssm/s4h/dev/stock-events`** (two subscriptions — verified in the binding dialog:
MaterialDocument offers Created and Canceled only, no Changed — correct, material
documents are immutable; corrections are reversal documents. Canceled is bound because
a cancelled movement reverses stock. Volume note: this is the highest-volume event on
the channel — every goods movement fires one. If too chatty in DEV, switching stock to
the timed check is configuration only (R-B2.4): remove the two bindings, keep the rest.)
```
ssm/s4h/dev/ce/sap/s4/beh/materialdocument/v1/MaterialDocument/Created/v1
ssm/s4h/dev/ce/sap/s4/beh/materialdocument/v1/MaterialDocument/Canceled/v1
```

**Wildcard alternative (not recommended as the default):** a subscription like
`ssm/s4h/dev/ce/sap/s4/beh/serviceorder/>` catches every event version for the object.
Use it only if a topic-string mismatch blocks you mid-session; replace it with the exact
strings once verified. Exact strings keep each queue's intake auditable.

## 4. S/4HANA — outbound channel bindings (separate system)

> **✅ COMPLETED in DEV, 7 Aug 2026.** All 18 new bindings below were added to
> `EMIS_COM_0092` and verified: 21 total on the channel (18 new + 3 pre-existing:
> BusinessPartner/Changed, WarehouseOrder/TaskCreated, ServiceEntrySheet/Changed),
> all status Ok, API state Released, no event filters, channel saved and Active.
> The table below is the as-built record — repeat it as written for TST/PRD.

In the S/4 dev tenant (my435863, client FLA/100), Fiori app **Enterprise Event
Enablement — Configure Channel Binding**, channel **`EMIS_COM_0092`** → add one outbound
topic binding per row. This is configuration only, ~2 minutes each.

| Object type to select | Events to tick | Note |
|---|---|---|
| `ServiceOrder` | Created, Changed | |
| `EnterpriseProject` | Created, Changed, EntProjElmntCrted, EntProjElmntChgd | Element events included — WBS element edits do not fire the header Changed event |
| `BillingDocument` | Created, Changed | Customer invoice |
| `SupplierInvoice` | Created, Canceled | **No `Changed` event exists** (verified in dialog). Canceled propagates RCTI reversals; `ServiceEntrySheet/Changed` already live covers the entry-sheet step |
| `PurchaseOrder` | Created, Changed, Approved, ItemCreated, ItemChanged, ItemDeleted | Approved = the approval-complete trigger; item events because item edits don't fire header Changed |
| `MaterialDocument` | Created, Canceled | Verified suitable — no Changed event exists (immutable object); Canceled reverses stock. Watch volume in DEV — highest-volume binding on the channel |

The dialog offers 183 object types; if a name above doesn't appear verbatim, search the
list — the dialog is the final authority (open item 1, Rajesh). Do not remove the
existing `ServiceEntrySheet`, `BusinessPartner` or `WarehouseOrder` bindings.

## 5. Verify end to end — one data set at a time

For each data set, after its binding and queue exist:

1. In S/4, change one record of that type (e.g. edit a service order).
2. S/4 **Event Monitor** for `EMIS_COM_0092`: the topic appears with status
   **Acknowledged**. Copy the exact topic string shown.
3. If the string differs from the subscription you created in step 3 (usually the
   lowercase `{object}` segment), edit the queue's subscription to match the Event
   Monitor string — the monitor is ground truth.
4. Event Mesh **Queues** tab → Refresh: the data set's queue shows **Messages Queued: 1**
   (nothing consumes it yet — that's the CPI flows, built next per the handover step 3).
5. Confirm `ssm/s4h/dev/dmq` stays at 0.

A quick negative check once any one data set works: the count appears **only** on that
data set's queue — proves subscriptions don't overlap.

## 6. Result — the Queues tab when you're done

| Queue | Subscriptions | State |
|---|---|---|
| `ssm/s4h/dev/dmq` | none | new |
| `ssm/s4h/dev/service-order-events` | 2 | new |
| `ssm/s4h/dev/enterprise-project-events` | 4 | new |
| `ssm/s4h/dev/customer-invoice-events` | 2 | new |
| `ssm/s4h/dev/supplier-invoice-events` | 4 | new |
| `ssm/s4h/dev/purchase-order-events` | 6 | new |
| `ssm/s4h/dev/stock-events` | 2 | new (verified suitable — no longer conditional) |
| `ssm/s4h/dev/Event_POC` | (as is) | untouched |
| `ssm/s4h/dev/s4h-dev-ses-events` | (as is) | untouched until step 7 |

## 7. Cleanup — only after CPI build starts

`ssm/s4h/dev/s4h-dev-ses-events` is superseded by `supplier-invoice-events` (which now
holds the ServiceEntrySheet topics). Delete it **only after** the CPI receiver flow
consumes from the new queue successfully — until then it does no harm. `Event_POC` can
be retired whenever the PoC flow `EventMesh_POC` is undeployed.

## 8. CPI consumer settings (for the flows that attach next — reference)

When the `FSMD_01_NoticeReceiver_{DataSet}` flows are built (handover step 3), each AMQP
consumer uses: **concurrency 1, prefetch 5, consume expired messages off, max retries 5
→ REJECTED** — matching the proven `EventMesh_POC` settings. REJECTED is safe *because*
every intake queue has the DMQ set (step 2) — that pairing is the design rule.

## 9. TST and PRD

Repeat steps 1–5 per environment with `dev` → `tst` / `prd` in every queue name and
topic string, against that environment's Integration Suite tenant and S/4 channel. The
subscription list, schedules and credentials are environment-specific configuration;
queue names and settings are identical by design (R-D2).
