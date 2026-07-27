# Cognixa (25 July demo)

Self-contained Claude Design (`.dc.html`) demo of **Cognixa** — Digitori Labs’ AI-powered SAP delivery workspace.

## Test locally

```bash
# from this folder
python3 -m http.server 8765
# open http://localhost:8765/  (or Cognixa.html)
```

> Opening the HTML via `file://` will break `<dc-import>` module loading (browser fetch). Always use a local static server.

## Sign in

1. Enter any name (e.g. `Rajesh Sha`)
2. Pick **Cognixa** (or HCM / RosterIQ)
3. Click **Sign in** or **Enter demo**

## What’s included

| File | Role |
|------|------|
| `Cognixa.dc_25th July.html` / `Cognixa.html` | Main app |
| `support.js` | Claude Design / DC runtime |
| `vendor/react*.js` | React 18 UMD (required by support.js) |
| `desktop-agent/cgx1-company-code/` | **Real** SAP GUI Scripting agent — creates CGX1 on A4H from your Windows PC |
| `desktop-agent/cgx1-company-code.zip` | Downloadable package (also via Cognixa UI button) |
| `ValueROI.dc.html`, `IP Library.dc.html`, `HCM.dc.html`, `RosterIQ.dc.html` | Nav modules |
| `FeedbackToast.dc.html` | Toast host stub |
| `LicentIQ.dc.html`, `TaxIQ.dc.html`, `TreasuryIQ.dc.html`, `Roadmap.dc.html`, `Platform Thesis.dc.html` | Suite redirects |

## Create CGX1 for real (not the browser simulation)

1. In Cognixa (On-Prem): **Download Desktop Agent · creates CGX1 for real**
2. On a Windows PC with SAP GUI + scripting enabled: unzip → `run.cmd`
3. Enter `Rajesh1` password when prompted; confirm customizing transport
4. Verify in S/4: `OX02` or `SE16N` → `T001` = **CGX1**

Prefer **BC Sets (SCPR20)** for bulk company codes. Desktop Agent = residual path only.

## Fixes in this revision

- Bootable offline with `support.js` + sibling modules
- Value & ROI nav label
- Workstream CTAs, header Export, Mark all read, View all activity
- Integrations Manage, Settings AI Connect/Disconnect + Signavio test
- Roster in engagement switcher; TaxIQ/TreasuryIQ proceed labels
- Suite product stub pages so login redirects don’t 404
