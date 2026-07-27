# One-time: create BC Set `ZCGX_FI_CGX1` on A4H

Do this once in client **800**. After it exists, activation can be automated.

## Option 1 — Capture from OX02 (simplest for tiny demo)

1. Log on A4H client 800  
2. Create CGX1 manually once in **OX02** (or ensure values match `bcset-definition.json`) and save to a customizing request  
3. `SCPR20` → **Create** → ID `ZCGX_FI_CGX1`  
4. Add customizing object / records for company code (`V_T001` / `T001`) for `CGX1`  
5. Save BC Set (workbench or according to your landscape standards)

## Option 2 — From IMG activity

1. `SPRO` → Enterprise Structure → Definition → Financial Accounting → Define company code  
2. Use BC Set tools from the IMG activity (where available) to write selected entries into a BC Set  
3. Name it `ZCGX_FI_CGX1`

## Option 3 — Copy template company code into BC Set

If you have a golden company code, copy its customizing into a BC Set, then adjust key `CGX1`.

## Check

`SCPR20` → enter `ZCGX_FI_CGX1` → Display — should list company code CGX1 values.
