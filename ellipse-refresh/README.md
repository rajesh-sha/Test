# Ellipse Refresh — SF EC → Ellipse (ACUTE-014 / 015 / 001)

Tooling to re-align an Ellipse **test environment** (SIT / UAT) to SuccessFactors EC
when the two drift out of sync, using the existing delta interfaces — **without** a
blind full replay (which would fail on duplicate creates, modify-where-missing, and
the missing employee-delete path).

## Contents

| File | What it is |
|------|------------|
| `ellipse-refresh-cockpit.html` | Standalone, zero-dependency web tool. Paste EC and Ellipse current-state extracts → it diffs, classifies drift (Missing / Stale / Orphaned / Event-history), routes each record to the correct Ellipse verb with guardrails, computes phase gates + effort/lock-window, and emits the per-verb interface payloads. |
| `ACUTE_Ellipse_Refresh_Runsheet_v0.2.xlsx` | Governance workbook: scope & assumptions, per-file capability assessment, the sequenced gated runsheet, and the risk register. |

## Cockpit — how it works

`diff → classify → route → gate → estimate → emit`

1. **Diff** — join EC vs Ellipse current-state on the natural key (per object).
2. **Classify** — Missing · Stale · Orphaned · Event-history (positionId drift is caught
   as event-history, not a plain modify).
3. **Route** — each class → the correct verb, guardrails inline: no duplicate-create,
   no modify-on-missing, position orphans via `#09 + #04` (CI-46, not `#10`),
   employee orphans have no delete path.
4. **Gate** — Org → Position → Employee, hard-gated on zero unexplained drift.
5. **Estimate** — human effort (person-days) and the Ellipse run / lock window (hours),
   per environment (Dev / SIT / UAT / Production).
6. **Emit** — generates the messages SAP IS posts to the Ellipse web services, sequenced
   and throttled; exportable as JSON.

### Connection
Set the EC base URL, SAP IS endpoint and delta `since` at the **top of Section 1**
(Interface connection row). Values persist to the browser and feed the Section 5
templates and exports. The example URLs are placeholders — replace with your real
SIT/UAT endpoints.

### Boundary
The page is a **pre-flight and emitter**, not the executor. It produces and sequences
the payloads; SAP IS (the iFlow) performs the actual writes, retry and monitoring.
Open the HTML file in any browser — no install, no network required for the offline
(paste) workflow.

## Reference registers
`OI-n` = Open Items tab · `CI-n` = Clarification Items tab of the Ellipse–SF Mapping
Specification. Exclusions in scope: rehire (OI-5, held), suspension (CI-6, out — LWOP),
physical location (out — defaulted), contested position fields (CI-18/19/21/22).
