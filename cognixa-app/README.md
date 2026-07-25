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
| `ValueROI.dc.html`, `IP Library.dc.html`, `HCM.dc.html`, `RosterIQ.dc.html` | Nav modules |
| `FeedbackToast.dc.html` | Toast host stub |
| `LicentIQ.dc.html`, `TaxIQ.dc.html`, `TreasuryIQ.dc.html`, `Roadmap.dc.html`, `Platform Thesis.dc.html` | Suite redirects |

## Fixes in this revision

- Bootable offline with `support.js` + sibling modules
- Value & ROI nav label
- Workstream CTAs, header Export, Mark all read, View all activity
- Integrations Manage, Settings AI Connect/Disconnect + Signavio test
- Roster in engagement switcher; TaxIQ/TreasuryIQ proceed labels
- Suite product stub pages so login redirects don’t 404
