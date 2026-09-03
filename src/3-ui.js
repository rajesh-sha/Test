/* ==========================================================================
   The page: five steps, in order down the screen.
   ========================================================================== */
const $ = (id) => document.getElementById(id);
const state = {
  wb: null, sheet: null, schema: null,
  templateName: "", sourceName: "",
  sourceFields: [], sourceRows: [],
  overrides: {}, memory: loadMemory(), mapping: null, mapped: null, validation: null,
};

function loadMemory() {
  try { return JSON.parse(localStorage.getItem("sapload.memory") || "{}"); }
  catch (e) { return {}; }
}
function saveMemory() {
  try { localStorage.setItem("sapload.memory", JSON.stringify(state.memory)); }
  catch (e) { /* a private window; the tool still works, it just forgets */ }
}
function rememberedCount() { return Object.keys(state.memory).length; }

function showError(msg) { $("topError").innerHTML = `<div class="note err">${esc(msg)}</div>`; }
function clearError() { $("topError").innerHTML = ""; }
function busy(id, on) { $(id).classList.toggle("hidden", !on); }

/* ---------- file intake ---------- */
function wireDrop(dropId, inputId, nameId, kind) {
  const drop = $(dropId), input = $(inputId), nameEl = $(nameId);
  const open = () => input.click();
  drop.addEventListener("click", open);
  drop.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
  });
  ["dragenter", "dragover"].forEach(ev =>
    drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev =>
    drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => {
    if (e.dataTransfer.files.length) take(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", () => { if (input.files.length) take(input.files[0]); });

  async function take(file) {
    try {
      clearError();
      if (kind === "template") await loadTemplate(file);
      else await loadSource(file);
      drop.classList.add("filled");
      nameEl.textContent = file.name;
      nameEl.classList.remove("hidden");
      $("btnAnalyse").disabled = !(state.wb && state.sourceRows.length);
    } catch (err) {
      showError(err instanceof AppError ? err.message
        : `Could not read ${file.name}. If SAP gave you an "XML Spreadsheet 2003" file, ` +
          `re-download it as .xlsx or .csv.`);
    }
  }
}

async function loadTemplate(file) {
  const buf = await file.arrayBuffer();
  state.wb = await openWorkbook(buf);
  state.sheet = pickDataSheet(state.wb);
  state.schema = deriveSchema(state.wb, state.sheet);
  state.templateName = file.name;
  if (!state.schema.fields.length)
    throw new AppError("No columns could be read from that template.");
}

async function loadSource(file) {
  let parsed;
  if (/\.(xlsx|xlsm)$/i.test(file.name)) {
    const wb = await openWorkbook(await file.arrayBuffer());
    const sh = wb.sheets[0];
    const header = (sh.rows[0] || []).map(h => (h || "").trim());
    const body = sh.rows.slice(1).filter(r => r.some(c => (c || "").trim()))
      .map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""]).filter(([h]) => h)));
    parsed = { fields: header.filter(Boolean), rows: body };
  } else {
    parsed = parseCsv(await file.text());
  }
  if (!parsed.rows.length) throw new AppError(`${file.name} has no data rows.`);
  state.sourceFields = parsed.fields;
  state.sourceRows = parsed.rows;
  state.sourceName = file.name;
}

/* ---------- run ---------- */
$("btnAnalyse").addEventListener("click", () => run("busy"));
$("btnRemap").addEventListener("click", () => run("busy2"));

function run(spinner) {
  busy(spinner, true);
  setTimeout(() => {
    try {
      state.mapping = buildMapping(state.schema, state.sourceFields, state.sourceRows,
                                   state.overrides, state.memory);
      state.mapped = applyMapping(state.schema, state.mapping, state.sourceRows);
      state.validation = validateRows(state.schema, state.mapped);
      renderAll();
      clearError();
    } catch (err) {
      showError(err instanceof AppError ? err.message : String(err));
    } finally {
      busy(spinner, false);
    }
  }, 20);
}

function card(v, k, tone) {
  return `<div class="card ${tone || ""}"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`;
}

function renderAll() {
  const s = state.schema;
  $("secSchema").classList.remove("hidden");
  $("schemaLayout").textContent =
    `${s.sheetName} · labels row ${s.labelRow === null ? "?" : s.labelRow + 1}` +
    ` · names row ${s.technicalRow === null ? "?" : s.technicalRow + 1}` +
    ` · data from row ${s.headerRows + 1}`;
  const req = s.fields.filter(f => f.required).length;
  const helped = s.fields.filter(f => f.allowed && f.allowed.length).length;
  $("schemaCards").innerHTML =
    card(s.fields.length, "fields in the template") +
    card(req, "SAP requires", req ? "warn" : "") +
    card(helped, "with a dropdown", helped ? "good" : "") +
    card(state.sourceRows.length.toLocaleString(), "rows in your extract");
  $("schemaNotes").innerHTML = s.notes.map(n => `<div class="note">${esc(n)}</div>`).join("");
  $("schemaBody").innerHTML = s.fields.map(f => `<tr>
      <td>${f.required ? '<span class="req" title="required">*</span>' : ""}</td>
      <td class="mono">${esc(f.name)}</td><td>${esc(f.label || "")}</td>
      <td>${esc(f.type)}${f.key ? " · key" : ""}</td>
      <td class="num">${f.maxLength ?? ""}</td>
      <td class="mono" style="font-size:12px">${
        f.allowed && f.allowed.length ? esc(f.allowed.join(", ")) : "—"}</td></tr>`).join("");

  const m = state.mapping;
  $("secMapping").classList.remove("hidden");
  const tally = { auto: 0, review: 0, low: 0, unmatched: 0 };
  m.rows.forEach(r => tally[r.status]++);
  $("mapCards").innerHTML =
    card(Math.round(m.coverage * 100) + "%", "template fields matched", m.coverage === 1 ? "good" : "warn") +
    card(tally.auto, "confident", "good") +
    card(tally.review, "worth a glance", tally.review ? "warn" : "") +
    card(tally.unmatched + tally.low, "need you", (tally.unmatched + tally.low) ? "bad" : "good");

  $("mapBody").innerHTML = m.rows.map(r => {
    const opts = ['<option value="">— not mapped —</option>'].concat(
      state.sourceFields.map(f =>
        `<option value="${esc(f)}"${f === r.source ? " selected" : ""}>${esc(f)}</option>`)).join("");
    return `<tr>
      <td>${r.required ? '<span class="req">*</span>' : ""}</td>
      <td class="mono">${esc(r.target)}</td>
      <td><select data-target="${esc(r.target)}">${opts}</select></td>
      <td><span class="chip ${r.status}">${esc(r.status)}</span>
          <span class="num" style="margin-left:6px">${r.source ? Math.round(r.confidence * 100) + "%" : "—"}</span></td>
      <td style="color:var(--ink-3);font-size:12.5px">${esc((r.reasons || []).join("; "))}</td></tr>`;
  }).join("");
  $("mapBody").querySelectorAll("select").forEach(sel => {
    sel.addEventListener("change", () => {
      state.overrides[sel.dataset.target] = sel.value;
      sel.classList.add("changed");
    });
  });

  const v = state.validation;
  $("secValidation").classList.remove("hidden");
  $("valSummary").textContent = v.summary;
  $("valBanner").innerHTML = v.ok
    ? `<div class="note ok">Every row passes the checks the template describes.</div>`
    : `<div class="note err">${v.badRows.size.toLocaleString()} of ${v.rowCount.toLocaleString()}
       rows would be rejected. Fix them at source, or leave them out at step 5.</div>`;
  $("valPanel").innerHTML = v.top.length
    ? v.top.map(t => `<div class="issue"><span class="n">${t.count}×</span>&nbsp;${esc(t.text)}
        <span style="color:var(--ink-3)">(rows ${esc(t.rows)})</span></div>`).join("")
    : `<div class="issue" style="color:var(--ink-3)">Nothing to fix.</div>`;

  $("prevHead").innerHTML = s.fields.map(f => `<th>${esc(f.name)}</th>`).join("");
  $("prevBody").innerHTML = state.mapped.slice(0, 20).map(r =>
    `<tr>${s.fields.map(f => `<td class="mono" style="font-size:12px">${esc(r[f.name])}</td>`).join("")}</tr>`
  ).join("");

  $("secBuild").classList.remove("hidden");
  $("buildOut").innerHTML = "";
  $("secSchema").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- build ---------- */
$("btnBuild").addEventListener("click", async () => {
  busy("busy3", true);
  try {
    const s = state.schema, v = state.validation;
    let rows = state.mapped;
    const notes = [...s.notes];
    if ($("optClean").checked && v.badRows.size) {
      rows = state.mapped.filter((_r, i) => !v.badRows.has(i + 1));
      notes.push(`${v.badRows.size} row(s) with errors were left out at your request.`);
    }

    const limit = parseInt($("optMax").value, 10);
    const size = Number.isFinite(limit) && limit > 0 ? limit : rows.length || 1;
    const batches = [];
    for (let i = 0; i < rows.length; i += size) batches.push(rows.slice(i, i + size));
    if (!batches.length) batches.push([]);
    if (batches.length > 1) notes.push(`Split into ${batches.length} files of at most ${size} rows.`);

    const stem = state.templateName.replace(/\.(xlsx|xlsm)$/i, "");
    const links = [];
    for (let i = 0; i < batches.length; i++) {
      const cells = batches[i].map(row => {
        const width = Math.max(...s.fields.map(f => f.column)) + 1;
        const line = new Array(width).fill("");
        s.fields.forEach(f => { line[f.column] = row[f.name] ?? ""; });
        return line;
      });
      const blob = fillWorkbook(state.wb, state.sheet, s, cells);
      const suffix = batches.length === 1 ? "" : `_${String(i + 1).padStart(2, "0")}`;
      links.push({ name: `${stem}_filled${suffix}.xlsx`, rows: batches[i].length,
                   url: URL.createObjectURL(blob) });
    }

    const recon = reconText({
      runId: Math.abs(hash(`${state.sourceName}|${state.sourceRows.length}|${rows.length}`))
             .toString(16).padStart(8, "0"),
      generated: new Date().toISOString().slice(0, 19).replace("T", " "),
      sourceName: state.sourceName, templateName: state.templateName,
      sourceRows: state.sourceRows.length, written: rows.length,
      totals: controlTotals(s, rows), coverage: state.mapping.coverage,
      unmapped: state.mapping.rows.filter(r => !r.source).map(r => r.target),
      unused: state.mapping.unusedSources, mapping: state.mapping.rows,
      validation: v, notes,
    });
    const reconUrl = URL.createObjectURL(new Blob([recon], { type: "text/plain" }));

    // Remember only what you chose, and matches already strong enough to apply
    // without review. A guess nobody looked at must not become a prior.
    state.mapping.rows.forEach(r => {
      if (!r.source) return;
      const confirmed = r.target in state.overrides;
      if (!confirmed && r.confidence < (T.learn_from || 0.85)) return;
      const f = state.schema.fields.find(x => x.name === r.target);
      [f.technical || f.name, f.label || f.name].filter(Boolean).forEach(alias => {
        state.memory[`${r.source}||${alias}`] = 1;
      });
    });
    saveMemory();
    $("memory").textContent = rememberedCount()
      ? `${rememberedCount()} mapping${rememberedCount() === 1 ? "" : "s"} remembered · nothing leaves this computer`
      : "nothing leaves this computer";

    const held = state.mapped.length - rows.length;
    $("buildOut").innerHTML =
      (held ? `<div class="note">${held.toLocaleString()} row(s) with errors were left out.
               They are listed in the reconciliation pack.</div>` : "") +
      `<div class="panel">` +
      links.map(l => `<a class="dl" href="${l.url}" download="${esc(l.name)}">
          <span class="name">${esc(l.name)}</span>
          <span class="go">${l.rows.toLocaleString()} rows · Download</span></a>`).join("") +
      `<a class="dl" href="${reconUrl}" download="${esc(stem)}_reconciliation.txt">
          <span class="name">${esc(stem)}_reconciliation.txt</span>
          <span class="go">Reconciliation · Download</span></a></div>
       <details class="panel" style="margin-top:12px" open>
         <summary>The reconciliation pack</summary><pre class="recon">${esc(recon)}</pre></details>`;
  } catch (err) {
    showError(err instanceof AppError ? err.message : String(err));
  } finally {
    busy("busy3", false);
  }
});

function hash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return h;
}

/* ---------- start ---------- */
wireDrop("dropTemplate", "fileTemplate", "nameTemplate", "template");
wireDrop("dropSource", "fileSource", "nameSource", "source");
if (rememberedCount()) {
  $("memory").textContent =
    `${rememberedCount()} mappings remembered · nothing leaves this computer`;
}
if (!window.DecompressionStream) {
  showError("This browser is too old to open .xlsx files here. " +
            "Use a current Chrome, Edge, Firefox or Safari.");
  $("btnAnalyse").disabled = true;
}
