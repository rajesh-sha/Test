# FSM Inbound — Decision Log (queue configuration session, closed 9 Aug 2026)

Decisions made while producing and executing
`docs/fsm-inbound-queue-configuration-runbook.md` (PR #7). Design authority remains the
Option D technical design and build specification §13.1/13.1a (PR #6, branch
`claude/fsm-inbound-orchestration-pifq6f`); this log records what was decided or verified
during execution, and why. Each entry is reflected in the runbook, which is the as-built
record.

## Queue architecture

1. **One DMQ, six intake queues.** `ssm/s4h/dev/dmq` is created first (TTL 604800 s) and
   is the only queue permitted Dead Message Queue = None. All six intake queues are
   Non-Exclusive, TTL 604800 s, Maximum Redelivery Count 5, DMQ set to `ssm/s4h/dev/dmq`.
   Time-equipment and job-financial-summary get no queue — timed check only.
2. **Subscriptions are created before S/4 bindings.** An event published while no
   subscription exists is silently discarded by the broker, so the broker side is
   configured first.
3. **Exact topic strings, not wildcards.** Wildcard subscriptions (`.../serviceorder/>`)
   are permitted only as a mid-session unblock and must be replaced with exact strings —
   exact strings keep each queue's intake auditable.
4. **Topic format confirmed** as `ssm/s4h/{env}/ce/sap/s4/beh/{object}/v1/{Object}/{Event}/v1`.
   The S/4 binding dialog and Event Monitor are ground truth on the `{object}` segment;
   on mismatch, the queue subscription is edited to match the monitor.

## Per-object event decisions (verified in the S/4 binding dialog, dev tenant, 7 Aug 2026)

5. **ServiceOrder:** Created, Changed. (2 subscriptions.)
6. **EnterpriseProject:** Created, Changed, plus element events `EntProjElmntCrted` and
   `EntProjElmntChgd` — a WBS element edit does not fire the header Changed event, and
   element events carry the project ID so downstream processing is the identical
   full-project read. Delete events deliberately excluded — the design has no delete
   handling. (4 subscriptions.)
7. **BillingDocument (customer invoice):** Created, Changed. (2 subscriptions.)
8. **SupplierInvoice has no Changed event** — only Created and Canceled exist. Canceled
   is bound because an RCTI reversal must propagate; the full-record read plus
   insert-or-update stores the current reversal state, and in-place changes (if any) are
   covered by the timed check. The `supplier-invoice-events` queue also takes both
   ServiceEntrySheet topics (Created, Changed), superseding `s4h-dev-ses-events`.
   (4 subscriptions.)
9. **PurchaseOrder:** Created, Changed, Approved, ItemCreated, ItemChanged, ItemDeleted.
   `Approved` is the approval-workflow-complete business trigger; item events are needed
   because item edits do not reliably fire header Changed (same completeness reasoning as
   the project element events). Deliberately not bound: ApprovalRejected, ItemBlocked,
   ItemUnblocked — internal workflow states covered by the full read and timed check.
   (6 subscriptions.)
10. **MaterialDocument verified suitable — stock stays event-driven.** Created and
    Canceled only; no Changed event exists because material documents are immutable
    (corrections are reversal documents). Canceled is bound because a cancelled movement
    reverses stock. This resolves the runbook's conditional: `stock-events` is kept.
    Volume caveat: highest-volume binding on the channel; fallback to the timed check is
    configuration-only (R-B2.4) — remove the two bindings, keep the rest. (2 subscriptions.)

## S/4 channel (as-built)

11. **All bindings completed and verified in DEV, 7 Aug 2026** on `EMIS_COM_0092`
    (my435863, client FLA/100): 18 new bindings added, 21 total on the channel including
    the 3 pre-existing (BusinessPartner/Changed, WarehouseOrder/TaskCreated,
    ServiceEntrySheet/Changed — other teams' PoCs, untouched). All status Ok, API state
    Released, no event filters, channel saved and Active.

## Consumer and lifecycle rules

12. **CPI consumer settings** for the `FSMD_01_NoticeReceiver_{DataSet}` flows (built
    next, handover step 3): concurrency 1, prefetch 5, consume expired messages off, max
    retries 5 → REJECTED. REJECTED is safe *only because* every intake queue has the DMQ
    set — that pairing is the design rule.
13. **Cleanup is deferred.** `s4h-dev-ses-events` is deleted only after the CPI receiver
    flow consumes successfully from `supplier-invoice-events`; `Event_POC` is retired
    whenever `EventMesh_POC` is undeployed. Until then both do no harm.
14. **TST/PRD repeat by substitution.** Same queue names and settings with `dev` → `tst`
    / `prd` in every name and topic string (R-D2); subscription lists, schedules and
    credentials are environment-specific configuration.

## State at session close

- S/4 side: **done and verified** (decision 11).
- Broker side: runbook finalised on PR #7 (draft, mergeable, no review comments); queue
  and subscription creation was in progress against the runbook at close. Target end
  state: seven queues (DMQ + six intake) with subscription counts 2 / 4 / 2 / 4 / 6 / 2.
- Outstanding: runbook §5 end-to-end verification — change one service order in S/4,
  confirm **Messages Queued: 1** on `service-order-events` only, and `ssm/s4h/dev/dmq`
  stays at 0 — then broker-side sign-off.
