# Cognixa Desktop Agents

Bots that run **on your Windows PC** and can perform real SAP writes.  
The Cognixa browser app only **orchestrates / simulates**; it cannot drive SAP GUI from the cloud.

| Agent | Purpose | Writes to S/4? |
|-------|---------|----------------|
| [`cgx1-company-code/`](./cgx1-company-code/) | Create company code **CGX1** on A4H via `OX02` + SAP GUI Scripting | **Yes** (when run locally) |

## Research summary — who creates company codes?

**Public Cloud:** only **CBC** Organizational Structure. No public write API → BPA UI bot if you must automate.

**On-Prem / Private:**
1. **Preferred:** BC Sets (`SCPR20`) + CTS/STMS  
2. **Manual:** `OX02` / SPRO Define company code  
3. **Residual bot:** this Desktop Agent (SAP GUI Scripting) or SAP Build Process Automation  
4. **Not:** Cognixa HTML alone (simulation)

See `cgx1-company-code/README.md` for run steps.
