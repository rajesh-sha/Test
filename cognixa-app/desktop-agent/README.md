# Cognixa Desktop Agents

Bots that run **on your Windows PC** and can perform real SAP writes.  
The Cognixa browser app only **orchestrates / simulates**; it cannot drive SAP GUI from the cloud.

| Package | Purpose | Writes to S/4? |
|---------|---------|----------------|
| [`bcset-cgx1/`](./bcset-cgx1/) | **Preferred:** automate **CGX1** via BC Set `ZCGX_FI_CGX1` + `SCPR_ACTIVATE_BCSETS_REMOTE` + CTS | **Yes** (when activated in SAP) |
| [`cgx1-company-code/`](./cgx1-company-code/) | **Last resort:** SAP GUI Scripting on `OX02` | Yes (local GUI only) |

## Research summary — who creates company codes?

**Public Cloud:** only **CBC** Organizational Structure. No public write API → BPA UI bot if you must automate.

**On-Prem / Private:**
1. **Preferred automation:** BC Sets (`SCPR20` / `SCPR_ACTIVATE_BCSETS_REMOTE`) + CTS/STMS  
2. **Manual:** `OX02` / SPRO Define company code  
3. **Residual bot:** GUI Desktop Agent / BPA  
4. **Not:** Cognixa HTML alone (simulation)

Start with `bcset-cgx1/README.md`.
