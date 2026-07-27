# Import into client S/4 system

Do this once per system (DEV/A4H first).

## 1) Create function group

1. `SE80` → Function Group → Create **`ZCGX_CFG`**
2. Short text: `Cognixa config deploy RFC`
3. Save to a **workbench** transport (not `$TMP` if you will move to QAS)

## 2) Create function module (RFC API)

1. In function group `ZCGX_CFG` → Create FM **`ZCGX_DEPLOY_ENTERPRISE_CFG`**
2. Attributes:
   - Processing type: **Remote-Enabled Module**
   - Short text: `Cognixa deploy enterprise/config BC Sets`
3. Open **Source code** → paste from `abap/ZCGX_DEPLOY_ENTERPRISE_CFG.abap` (the FORM/function body section — see file header)
4. Define parameters exactly as in that file’s parameter list (Import / Export / Tables / Exceptions)
5. **Activate** function group + FM

### Parameter checklist (SE37)

**Importing**
- `IV_PLAYBOOK` TYPE `CHAR40` (optional)
- `IV_SIMULATION` TYPE `CHAR1` default space
- `IV_RFCDEST` TYPE `RFCDES-RFCDEST` default space (usually blank = local)
- `IV_TASK_CUST` TYPE `TRKORR` default space
- `IV_TRANSPORT_OFF` TYPE `CHAR1` default `N`

**Exporting**
- `EV_RC_ACTIV` TYPE `SCPRACST`
- `EV_TASK_CUST` TYPE `TRKORR`
- `EV_TASK_SYST` TYPE `TRKORR`
- `EV_PROTO` TYPE `SCPR_HANDL`
- `EV_SUBRC` TYPE `SYSUBRC`
- `EV_MESSAGE` TYPE `CHAR255`

**Tables**
- `IT_BCSETS` LIKE `SCPR_PARNT` (fill `BCSET_ID`; other fields optional)
- `ET_MESSAGES` LIKE `BAPIRET2` (optional return log)

**Exceptions**
- `NO_BCSET`
- `NO_AUTHORITY`
- `ACTIVATION_FAILED`
- `WRONG_INPUT`

## 3) Create test report

1. `SE38` → Create **`ZCGX_DEPLOY_ENT_CFG_TEST`**
2. Paste `abap/ZCGX_DEPLOY_ENT_CFG_TEST.abap`
3. Activate → Execute (F8)

## 4) Package content (enterprise structure)

BC Sets must **already exist** in the system (SCPR3), e.g.:

| BC Set | Content example |
|--------|-----------------|
| `ZCGX_FI_ORG` | Company codes CGX1, CGX2 (`V_T001`) |
| `ZCGX_LO_PLANT` | Plants |
| `ZCGX_SD_SALES` | Sales organizations |

See `example-enterprise-bcsets.json`.

## 5) Call via RFC (no GUI logon)

From outside SAP (or another system):

```text
CALL FUNCTION 'ZCGX_DEPLOY_ENTERPRISE_CFG'
  DESTINATION 'A4H_CGX'
  ...
```

Or from Cognixa runtime / middleware using the same FM name over SM59.

## 6) Move to other clients/systems

1. Release workbench TR (FM + report)  
2. STMS import to QAS/PRD  
3. Ensure BC Set **content** is also transported or created in target  
4. Customizing from activation moves via the **customizing** TR returned by the FM  

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CALL_FUNCTION_CONFLICT_TYPE` on SAP FM | Align with SE37 `SCPR_ACTIVATE_BCSETS_REMOTE` on that SP |
| `NO_BCSET` | Create/activate BC Set name in SCPR3 first |
| RFC logon failed | Technical user + SM59 + S_RFC |
| No T001 change | Check BC Set contains the rows; verify OX02 |
