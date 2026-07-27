# Cognixa — Enterprise Structure Config Deploy (RFC / API)

**Purpose:** Importable ABAP that lets Cognixa (or any orchestrator) deploy **enterprise structure / customizing** into a client system **without interactive SAP GUI logon**, via **RFC**.

**Important design (Clean Core / scalable IP):**
- This does **not** invent enterprise structure by writing `T001`/`T001W`/… directly from free parameters.
- It deploys **packaged BC Sets** (company codes, plants, sales orgs, …) using SAP FM `SCPR_ACTIVATE_BCSETS_REMOTE`.
- Cognixa passes **playbook + BC Set IDs**; content stays in BC Sets; executor is thin and reusable across customers.

## What you import

| Object | Name | Role |
|--------|------|------|
| Function group | `ZCGX_CFG` | Container |
| Function module | `ZCGX_DEPLOY_ENTERPRISE_CFG` | **Remote-enabled** RFC/API entry |
| Executable report | `ZCGX_DEPLOY_ENT_CFG_TEST` | Local test from SE38 |
| Example catalog | `example-enterprise-bcsets.json` | Sample BC Set packing for org structure |

## Flow

```text
Cognixa / script
   --RFC-->  ZCGX_DEPLOY_ENTERPRISE_CFG  (technical user)
                |
                +--> SCPR_ACTIVATE_BCSETS_REMOTE (1..N BC Sets)
                |
                +--> customizing TR + activation RC + message log
```

## Install

See **`IMPORT.md`** (SE80 / SE37 / SE38 steps).

## Auth

Create technical user (e.g. `CGX_CFG_BOT`) with:
- BC Set activate (`S_BCSETS` / SCPR auth as per your security concept)
- Customizing + transport
- RFC (`S_RFC` for function group `ZCGX_CFG` and `SCPR`)

SM59 destination from Cognixa runtime → A4H points at that user (password or SNC).

## Public Cloud

**Do not use this** for Public Edition company codes — use **CBC**. This package is **On-Prem / Private** only.
