# Make BC Set automation work on A4H (CGX1)

The Cognixa **Configuration Bot** in the browser is a **demo**.  
To actually create **CGX1** in S/4, do this on your A4H system.

## Research (what works)

| Step | Tool | Automate? |
|------|------|-----------|
| Package values | BC Set `ZCGX_FI_CGX1` | Create once |
| Activate into tables | `SCPR20` or FM **`SCPR_ACTIVATE_BCSETS_REMOTE`** | **Yes** |
| Move landscape | SE09 release → STMS import | **Yes** (ALM optional) |
| Click OX02 fields | SAP GUI bot | Avoid |

## Prerequisites

- A4H client **800**, customizing allowed (not a locked prod client)
- User with auth for **SCPR20** / BC Sets + **CTS**
- SAP GUI logged on (for UI path) or ABAP workbench access (for FM path)

## Path A — fastest demo (UI)

1. Log on A4H / 800  
2. Follow `Create-BCSet-in-SCPR20.md` → create **`ZCGX_FI_CGX1`** with CGX1 values  
   - Shortcut: create CGX1 in **OX02** once, then capture into the BC Set  
3. `SCPR20` → enter `ZCGX_FI_CGX1` → **Activate** → assign customizing TR  
4. `SE09` → release that TR  
5. `STMS` → import to next system (if landscape)  
6. Verify: `OX02` or `SE16N` `T001` = **CGX1**

## Path B — automate activate (ABAP / RFC)

1. Create BC Set once (same as Path A step 2)  
2. Install report `ZCGX_ACTIVATE_BCSET.abap` (SE38/SE80)  
3. Run with `p_bcset = ZCGX_FI_CGX1`  
4. Note returned customizing transport  
5. Release + STMS as above  

From another system, call the same FM over **SM59** RFC destination into A4H.

> Check SE37 on your release for the exact TABLES parameter name of `SCPR_ACTIVATE_BCSETS_REMOTE` (SP-dependent). Adjust the sample ABAP if the signature differs.

## Path C — Cognixa helper on your PC

```bat
Extract bcset-cgx1.zip
run.cmd
```

Writes `evidence-plan.json` + checklist. Then execute Path A or B inside SAP.

## What will NOT work

- Clicking **Log On** / **Run bot** only inside the Cognixa HTML page — no RFC from the browser to A4H  
- Expecting CGX1 in Company Codes after a browser demo alone  

## Success criteria

- `T001-BUKRS = CGX1`  
- Activation log in `SCPR20`  
- Customizing transport in `SE09`
