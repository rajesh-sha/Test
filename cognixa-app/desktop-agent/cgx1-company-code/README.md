# Cognixa Desktop Agent — create company code CGX1 on A4H

This package **actually writes** to S/4HANA On-Prem (A4H) via **SAP GUI Scripting**.  
The Cognixa browser demo **cannot** create `CGX1` by itself — run this agent on a Windows PC that has SAP GUI + Logon pad entry to A4H.

## Research: who / what can create a company code?

| Edition | Who can create it | How | Automatable? |
|--------|-------------------|-----|--------------|
| **Public Cloud** | CBC (Central Business Configuration) org structure | CBC → Setup Organizational Structure → Company Code | **No public write API.** UI bot (BPA) on CBC is last resort. |
| **On-Prem / Private** | IMG consultant / config lead | `OX02` or SPRO → Enterprise Structure → Define company code → Save to CTS | Manual |
| **On-Prem / Private** | **BC Sets** (preferred bulk) | `SCPR20` activate BC Set → CTS/STMS | Prefer this for scale |
| **On-Prem / Private** | **Desktop Agent / SAP GUI Scripting / BPA** | Drive `OX02` like a user | **Yes — this package** (residual / last resort) |
| **On-Prem / Private** | Custom ABAP / LSMW / MDG-F | Loaders / master-data governance | Possible; do **not** direct-insert `T001` |
| **Neither** | Cognixa HTML in the browser | Simulation only | **No SAP write** |

**Advise (Cognixa product truth):**
1. Prefer **BC Sets + CTS** for On-Prem bulk config.
2. Prefer **CBC** for Public Cloud org structure (no OX02, no classic BAPI).
3. Use this **Desktop Agent** only for residual IMG nodes (tiny example: CGX1) when no BC Set/API exists.
4. Never treat a browser simulation as proof that `T001` changed — verify in `OX02` / `SE16N` (`T001`).

## Prerequisites (your PC)

1. Windows + **SAP GUI for Windows** with scripting enabled  
   - Client: Options → Accessibility & Scripting → Enable scripting  
   - Server: `RZ11` → `sapgui/user_scripting` = `TRUE`
2. SAP Logon entry matching description **`S4HANA2023 SHARED GUI`**  
   (SID `A4H`, host `115.245.150.98`, instance `18`)
3. User **`Rajesh1`**, client **`800`**, language **EN**, with auth to maintain company codes + customizing transports
4. PowerShell 5+ (Windows)

## Create CGX1 (real write)

```bat
cd desktop-agent\cgx1-company-code
run.cmd
```

Or:

```powershell
.\Run-Create-CGX1.ps1
```

You will be prompted for the SAP password (not stored).  
Optional env overrides:

```powershell
$env:CGX_SAP_USER = "Rajesh1"
$env:CGX_SAP_CLIENT = "800"
$env:CGX_SAP_LANGUAGE = "EN"
$env:CGX_SAP_CONNECTION = "S4HANA2023 SHARED GUI"
$env:CGX_CC = "CGX1"
.\Run-Create-CGX1.ps1
```

## Verify in S/4

1. `OX02` → Position → `CGX1`  
2. or `SE16N` → table `T001` → `BUKRS = CGX1`

Also:

```powershell
.\Run-Create-CGX1.ps1 -VerifyOnly
```

## What gets written

From `payload.json`:

| Field | Value |
|-------|--------|
| Company code | CGX1 |
| Name | Cognixa Demo AU |
| City | Perth |
| Country | AU |
| Currency | AUD |
| Language | EN |

Save assigns a **customizing transport** (popup). Pick/create a request when prompted.

## Field-ID fragility

SAP GUI Scripting IDs depend on screen/theme/patch. If New Entries fields fail:

1. SAP GUI → Customize Local Layout (Alt+F12) → Script Recording and Playback  
2. Record creating CGX1 once in `OX02`  
3. Replace the `NewEntries` block in `Create-CGX1.vbs` with your recorded IDs  
4. Re-run

## Security

- Password is prompted / env-only — **never commit** passwords  
- Agent runs only on your PC under your Windows login  
- Prefer a dedicated config user in real projects
