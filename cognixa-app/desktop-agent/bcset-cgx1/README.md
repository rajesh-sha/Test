# Cognixa — automate company code via BC Sets + CTS (preferred)

**Research verdict:** For On-Prem / Private S/4HANA, automate org customizing with **BC Sets (`SCPR20`) + classic CTS/STMS**, not SAP GUI bots.

Tiny example in this package: company code **CGX1** (Cognixa Demo AU) for SID **A4H** / client **800**.

## Automation ladder (best → last resort)

| Rank | Method | How | When |
|------|--------|-----|------|
| **1 · Preferred** | **BC Set activate + CTS** | Create BC Set → `SCPR20` / `SCPR_ACTIVATE_BCSETS_REMOTE` → customizing TR → STMS | Bulk & repeatable |
| **2 · Orchestrate** | **Cloud ALM Feature Deployment** | Orchestrate CTS create/release/import across landscape | Multi-system gates |
| **3 · Last resort** | **SAP GUI Scripting / BPA** | Drive `OX02` / `SCPR20` UI | Only if no BC Set / API |

**Public Cloud note:** company codes are created in **CBC**, not BC Sets/OX02. Different path.

## Why BC Sets automate well

- Values are packaged (not clicked field-by-field)
- Activation writes customizing tables (e.g. `T001`) under a transport
- Same BC Set can be re-activated / moved with CTS
- Remote FM exists: **`SCPR_ACTIVATE_BCSETS_REMOTE`** (function group `SCPR`)
- Avoids fragile SAP GUI scripting

Constraints:
- Activate in **non-production** clients (SAP rule of thumb: no prod client)
- Needs customizing auth + transportable client
- BC Set must exist in the system (create once, activate many)

## Example: CGX1

| Field | Value |
|-------|--------|
| BC Set ID | `ZCGX_FI_CGX1` |
| Company code | `CGX1` |
| Name | Cognixa Demo AU |
| City | Perth |
| Country | AU |
| Currency | AUD |
| Language | EN |
| Table | `T001` (via view `V_T001` / OX02 data) |

Files:
- `MAKE-IT-WORK.md` — short path to write CGX1 on A4H (start here)
- `payload.json` — Cognixa playbook binding
- `bcset-definition.json` — machine-readable values
- `ZCGX_ACTIVATE_BCSET.abap` — sample ABAP calling `SCPR_ACTIVATE_BCSETS_REMOTE`
- `Create-BCSet-in-SCPR20.md` — one-time create steps in A4H
- `Run-Activate-BCSet.ps1` / `run.cmd` — checklist runner + evidence log

## One-time: create the BC Set on A4H

Follow `Create-BCSet-in-SCPR20.md` (or create from a reference company code with SCPR20 / BC Set from customizing).

## Automate activation (choose one)

### A) ABAP / RFC (recommended automation)

1. Install report `ZCGX_ACTIVATE_BCSET` (from `.abap` file) in DEV/A4H  
2. Maintain RFC destination if calling remote (`SM59`)  
3. Run report with BC Set `ZCGX_FI_CGX1`  
4. Capture returned customizing transport (`TASK_CUST_EXP`)  
5. Release in **SE09** → import via **STMS** (QAS → PRD)

Cognixa agent / CI can wrap this as:
`RFC → SCPR_ACTIVATE_BCSETS_REMOTE → CTS release → STMS import`

### B) Semi-manual (fast for demo)

1. `SCPR20` → `ZCGX_FI_CGX1` → Activate  
2. Assign customizing request  
3. `SE09` release → `STMS` import  

### C) GUI bot (not preferred)

Only if BC Set tooling is blocked — use the residual `cgx1-company-code` Desktop Agent on `OX02`.

## Verify

- `OX02` / `SE16N` → `T001` → `BUKRS = CGX1`  
- Activation log in `SCPR20`  
- Transport in `SE09` / `STMS`

## Cognixa playbook

`CFG-BOT/BCSET/FI/CGX1` — preferred On-Prem path for this tiny example.
