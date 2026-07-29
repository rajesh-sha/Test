# Cognixa IP — Enterprise Structure Configuration Automation

**Asset ID:** `IP-CFG-ENT-001`  
**Edition scope:** On-Prem / Private (IMG). Public Cloud = CBC (separate rail).  
**Problem:** Most Enterprise Structure IMG activities have **no released create API**. Correct automation is not “write T001 from RFC parameters.”

---

## 1. Research verdict (what is correct)

| Approach | Verdict |
|----------|---------|
| Custom ABAP that `INSERT`/`UPDATE` customizing tables (`T001`, `T001W`, `TVKO`, …) | **Reject** — Clean Core Level D, upgrade-unsafe, incomplete |
| One mega RFC “create whole enterprise structure from free fields” | **Reject** — reinvents SPRO; always incomplete |
| **BC Sets from IMG hierarchy + activate (`SCPR_ACTIVATE_BCSETS_REMOTE`) + CTS** | **Preferred** — SAP-supported for customizing |
| **Copy Company Code** (and similar copy tools) then adjust | **Preferred** for FI CC bootstrap |
| Hierarchical BC Sets (bundle FI+LO+SD+MM+Assignment) | **Preferred** for bulk / multi-customer reuse |
| Cloud ALM Feature Deployment | **Orchestrate** transports across landscape |
| Technical user + RFC thin deploy FM (`ZCGX_DEPLOY_ENTERPRISE_CFG`) | **Automate human logon away** |
| SAP GUI Scripting / BPA on SPRO | **Last resort** only |
| Public Cloud CBC / SSCUI | **Only** path for Public Edition |

**Cognixa IP = decision engine + playbook catalog + BC Set templates + thin RFC deploy + evidence — not a second IMG written in ABAP.**

---

## 2. Whole flow (matches SPRO → Enterprise Structure)

```text
Signed design (Cognixa)
        │
        ▼
┌─────────────────── DEFINITION ───────────────────┐
│ FI: Company, Credit ctrl, Company code, BA, …    │
│ CO: Controlling area, Operating concern          │
│ LO: Plant, Division, …                           │
│ SD: Sales org, Dist channel, …                   │
│ MM: Storage loc, Purchasing org                  │
│ LE: Warehouse                                    │
│ HR / PM / Service: as in scope                   │
└───────────────────┬──────────────────────────────┘
                    ▼
┌─────────────────── ASSIGNMENT ───────────────────┐
│ CC↔CO area · Plant↔CC · Sales org↔CC · …         │
│ (dependencies — order matters)                   │
└───────────────────┬──────────────────────────────┘
                    ▼
         Consistency check (IMG)
                    ▼
     BC Set package(s)  →  Activate (RFC)  →  CTS/STMS
                    ▼
              Cognixa evidence pack
```

**Rule:** Definition before Assignment. Never activate assignment BC Sets before definition BC Sets succeed.

---

## 3. Typical requirements (what customers ask for)

1. Multi-country company codes in bulk  
2. Plants + storage locations per CC  
3. Sales orgs / dist channels / sales areas  
4. Purchasing orgs + plant assignments  
5. Controlling area assignment  
6. Same pattern across DEV→QAS→PRD without re-clicking SPRO  
7. Audit: who approved, which playbook, which TR  
8. No dependency on consultant GUI for every refresh / rollout  

---

## 4. IMG → automation method matrix

### 4.1 Definition

| IMG node (Enterprise Structure → Definition) | Typical tcode / view | Table/view (indicative) | Standard create API? | Best automation |
|----------------------------------------------|----------------------|-------------------------|----------------------|-----------------|
| Financial Accounting → Define company | OX15 | T880 / company | No public write API | BC Set / copy |
| → Define Credit Control Area | OB45 | T014 | No | BC Set |
| → **Edit/Copy/Delete/Check Company Code** | **OX02** / copy | **V_T001 / T001** | Partial/legacy only; not Clean Core write | **Copy CC + BC Set** |
| → Business Area | OX03 | TGSB | No | BC Set |
| → Functional Area | OKBD | TFKB | No | BC Set |
| → Segment | — | FAGL_SEGM | No | BC Set |
| Controlling → Controlling Area | OKKP | TKA01 | No | BC Set / copy |
| → Operating Concern | KEA0 | TKEB | No | BC Set (careful) |
| Logistics General → Plant | OX10 | V_T001W / T001W | No | BC Set / copy |
| → Division | OVXB | TSPA | No | BC Set |
| SD → Sales Organization | OVX5 | TVKO | No | BC Set |
| → Distribution Channel | OVXI | TVTW | No | BC Set |
| MM → Storage Location | OX09 | T001L | No | BC Set |
| → Purchasing Organization | OX08 | T024E | No | BC Set |
| LE → Warehouse Number | — | T300… | No | BC Set / copy WH |

### 4.2 Assignment (dependencies)

| Assignment | Typical | Depends on | Best automation |
|------------|---------|------------|-----------------|
| Company code → Controlling area | OX19 | CC, CO area | BC Set after both defined |
| Plant → Company code | OX18 | Plant, CC | BC Set |
| Sales org → Company code | OVX3 | Sales org, CC | BC Set |
| Purchasing org → Company code | OX01 | Purch org, CC | BC Set |
| Sales area (SO+DC+Div) | OVXG | SO, DC, Div | BC Set |
| Plant → Sales org / dist channel | OVX6 | Plant, SO, DC | BC Set |

---

## 5. When standard API / program does **not** support automation

Use this **Cognixa fallback ladder** (always in order):

| Rank | Method | Use when |
|------|--------|----------|
| **1** | **BC Set from IMG hierarchy** (SCPR3) + variables for org keys | Default for almost all ENT structure |
| **2** | **Hierarchical BC Set** bundling Definition + Assignment slices | Multi-object rollout / customer template |
| **3** | **Copy** tools (Copy Company Code, Copy Warehouse, …) then BC Set delta | Bootstrap from golden template |
| **4** | **Transport of copies / BC Set file** upload to other landscapes | No CTS path between systems |
| **5** | Thin RFC `ZCGX_DEPLOY_ENTERPRISE_CFG` | Unattended activate (no GUI logon) |
| **6** | Cloud ALM Feature | Landscape gate / multi-TR feature |
| **7** | GUI Scripting / BPA | Only if BC Set cannot capture the activity |
| **8** | Manual SPRO | Exceptions, one-offs, broken BC Set tools |

**Never jump to 7/8 if 1–5 work.**

---

## 6. Cognixa standard playbook IDs (reusable IP)

Pattern: `CFG-BOT/BCSET/ENT/{AREA}/{SEQ}`

| Playbook | BC Set slice (example) | IMG coverage |
|----------|------------------------|--------------|
| `CFG-BOT/BCSET/ENT/FI/0001` | `ZCGX_ENT_FI_DEF` | Company, CC, credit ctrl, BA |
| `CFG-BOT/BCSET/ENT/CO/0001` | `ZCGX_ENT_CO_DEF` | Controlling area |
| `CFG-BOT/BCSET/ENT/LO/0001` | `ZCGX_ENT_LO_DEF` | Plant, division |
| `CFG-BOT/BCSET/ENT/SD/0001` | `ZCGX_ENT_SD_DEF` | Sales org, dist channel |
| `CFG-BOT/BCSET/ENT/MM/0001` | `ZCGX_ENT_MM_DEF` | SLoc, purch org |
| `CFG-BOT/BCSET/ENT/ASN/0001` | `ZCGX_ENT_ASSIGN` | All in-scope assignments |
| `CFG-BOT/BCSET/ENT/ALL/0001` | Hierarchical parent BC Set | Full signed org package |

Deploy order for `ENT/ALL`: FI → CO → LO → SD → MM → ASN.

---

## 7. Executable standard (what Cognixa ships)

1. **Content:** customer/signed BC Sets (or Digitori templates)  
2. **Executor:** `ZCGX_DEPLOY_ENTERPRISE_CFG` (RFC) → `SCPR_ACTIVATE_BCSETS_REMOTE`  
3. **Orchestration:** Cognixa playbooks + Cloud ALM  
4. **Evidence:** playbook → BC Set IDs → TR → OX02/consistency check → hash  

See sibling files:
- `../enterprise-config-rfc/` (importable FM)
- `enterprise-structure-catalog.json` (machine catalog)
- `playbook-ent-all.example.json`

---

## 8. Public Cloud note

Enterprise Structure in **Public Edition** is configured in **CBC**, not this IMG tree. Cognixa must switch edition rail — do not call On-Prem BC Set RFC against Public Cloud.

---

## 9. One-line IP statement

> **When S/4 has no safe create API for Enterprise Structure, Cognixa automates configuration by packaging IMG activities as BC Sets, deploying them via a thin RFC activator, moving them with CTS/ALM, and proving them with evidence — never by custom table writes or GUI-first bots.**
