# Cognixa → Claude Code handoff pack

Use this folder/zip as context when continuing Cognixa work in **Claude Code**.

## What Cognixa is
Digitori Labs AI SAP S/4HANA delivery demo (Claude Design single-file app).
Twins must stay in sync: `Cognixa.html` ≡ `Cognixa.dc_25th July.html`.

## Repo / branch
- Repo: `rajesh-sha/Test`
- Branch: `cursor/cognixa-july-features-7d34`
- Base: `claude/smart-field-mapper-xlfx1h`
- PR: https://github.com/rajesh-sha/Test/pull/3

## How to run locally (important)
Do **not** open `Cognixa.html` alone via `file://` — you will see raw `{{ placeholders }}`.

```bash
# preferred: full runnable zip
unzip Cognixa-runnable.zip -d cognixa-run && cd cognixa-run
python3 -m http.server 8765
# open http://localhost:8765/Cognixa.html
```

Required next to HTML: `support.js`, `vendor/react*.js`, `FeedbackToast.dc.html`.

## Product truth (research — do not regress)

### Config deploy
| Edition | Path |
|---------|------|
| On-Prem / Private | **BC Sets + CTS** preferred; thin RFC `ZCGX_DEPLOY_ENTERPRISE_CFG` → `SCPR_ACTIVATE_BCSETS_REMOTE` |
| Public Cloud | **CBC** only (no OX02 / BC Set write path) |
| Reject | Custom INSERT into `T001`/`T001W`/`TVKO`; mega “create whole ENT” API; GUI bot as primary |

### Live proof already done on A4H
- BC Set `ZCGX_FI_CGX1` created (SCPR3) and activated
- Company code **CGX1** / Cognixa Demo AU visible in **OX02**
- Report `ZCGX_ACTIVATE_BCSET` fixed for `CALL_FUNCTION_CONFLICT_TYPE` (use `BCSET_IDS` / `SCPR_PARNT`, `RC_ACTIV` type `SCPRACST`)
- Customizing TR example: `A4HK900589`
- Cognixa UI: **Confirm live A4H: CGX1** records IP playbook `CFG-BOT/BCSET/FI/CGX1`

### IP asset
`IP-CFG-ENT-001` — Enterprise Structure automation when no safe create API exists.
- Doc: `desktop-agent/enterprise-config-rfc/IP-CFG-ENT-001-Enterprise-Structure-Automation.md`
- Catalog: `enterprise-structure-catalog.json`
- Importable FM: `abap/ZCGX_DEPLOY_ENTERPRISE_CFG.abap`
- Test report: `abap/ZCGX_DEPLOY_ENT_CFG_TEST.abap`

### Code deploy (ABAP into client)
Prefer **abapGit / CTS / gCTS** — not browser paste forever; no unsupported “upload .abap via public API”.

### Conduct AI (competitor research)
Public story = connect + **read** SAP + AI agents (fit-gap, specs, change lifecycle) + Cloud ALM.
They do **not** publicly claim free-field Enterprise Structure create API.
Cognixa differentiator = playbooks + BC Set deploy + evidence ladder.

## Key paths
```
cognixa-app/
  Cognixa.html                          # main app
  Cognixa.dc_25th July.html             # twin (keep identical)
  Cognixa-runnable.zip                  # shareable runnable pack
  support.js + vendor/ + FeedbackToast.dc.html
  desktop-agent/
    bcset-cgx1/                         # CGX1 BC Set package
    bcset-cgx1.zip
    enterprise-config-rfc/              # RFC IP + ENT catalog
    enterprise-config-rfc.zip
    cgx1-company-code/                  # residual GUI agent (last resort)
```

## A4H profile (non-secret)
- Logon: S4HANA2023 SHARED GUI · SID A4H · host 115.245.150.98 · inst 18 · client 800 · user Rajesh1
- Never commit passwords

## Open / next work ideas
1. Technical user + SM59 → Cognixa triggers `ZCGX_DEPLOY_ENTERPRISE_CFG` without SE38
2. abapGit layout for `ZCGX_*` objects
3. CGX2 bulk demo (two company codes in one BC Set)
4. Finish edition-aware UI cleanup (hardcoded CBC strings on On-Prem)

## Claude Code instructions
- Keep Cognixa.html twins identical when editing UI/JS
- Prefer surgical diffs; do not rewrite whole Cognixa.html
- Do not invent customizing table-write APIs
- Before claiming “browser creates company code”: false — browser demos + evidence only
