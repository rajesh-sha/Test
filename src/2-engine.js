/* ==========================================================================
   TEMPLATE — work out what the SAP template wants, unaided.
   Nothing is configured per object: the header block, the technical-name row,
   the mandatory markers, the field lengths and the dropdowns are all found by
   looking at the file.
   ========================================================================== */
const RE_MARKER = /^[*+kK]{1,3}$/;
const RE_IDENT = /^[A-Za-z][A-Za-z0-9_]{2,}$/;
const RE_INT = /^\d{1,4}$/;
const RE_DATEISH = /date|dat$|_dt$|posting|document date/i;
const RE_NUMISH = /amount|amt|qty|quantity|value|price|rate|percent|total/i;
const RE_NONDATA = /field\s*list|introduction|instructions|help|read\s*me|notes|legend|documentation|cover|about/i;
const MAX_SCAN = 8;

function rowStats(values) {
  const filled = values.map(v => (v || "").trim()).filter(Boolean);
  if (!filled.length) return { fill: 0, marker: 0, ident: 0, integer: 0, avgLen: 0 };
  const n = filled.length;
  return {
    fill: n / Math.max(values.length, 1),
    marker: filled.filter(v => RE_MARKER.test(v)).length / n,
    ident: filled.filter(v => RE_IDENT.test(v) && !v.includes(" ")).length / n,
    integer: filled.filter(v => RE_INT.test(v)).length / n,
    avgLen: filled.reduce((a, v) => a + v.length, 0) / n,
  };
}

function bestRow(stats, key, threshold, exclude, preferLast) {
  const skip = new Set((exclude || []).filter(x => x !== null && x !== undefined));
  let best = null, bestVal = threshold;
  const idx = [...stats.keys()];
  if (preferLast) idx.reverse();
  for (const r of idx) {
    if (skip.has(r) || stats[r].fill < 0.3) continue;
    if (stats[r][key] > bestVal || (preferLast && stats[r][key] >= bestVal && best === null)) {
      best = r; bestVal = stats[r][key];
    }
  }
  return best;
}

function pickDataSheet(wb) {
  const usable = wb.sheets.filter(s => !RE_NONDATA.test(s.name));
  const list = usable.length ? usable : wb.sheets;
  return list.reduce((a, b) => {
    const w = (s) => Math.max(0, ...s.rows.slice(0, MAX_SCAN).map(r => r.length));
    return w(b) > w(a) ? b : a;
  });
}

function inferType(name, samples) {
  const real = samples.map(s => (s || "").trim()).filter(Boolean);
  if (real.length) {
    const num = real.filter(s => /^-?[\d,]+(\.\d+)?$/.test(s)).length;
    const dat = real.filter(s => /^\d{4}-\d{2}-\d{2}|^\d{2}[./]\d{2}[./]\d{4}/.test(s)).length;
    if (dat / real.length > 0.7) return "date";
    if (num / real.length > 0.7) return "number";
  }
  if (RE_DATEISH.test(name)) return "date";
  if (RE_NUMISH.test(name)) return "number";
  return "text";
}

function deriveSchema(wb, sheet) {
  const scan = Math.min(MAX_SCAN, sheet.rows.length);
  const stats = [];
  for (let r = 0; r < scan; r++) stats.push(rowStats(sheet.rows[r]));

  const markerRow = bestRow(stats, "marker", 0.30, [], false);
  const lengthRow = bestRow(stats, "integer", 0.60, [markerRow], false);
  const technicalRow = bestRow(stats, "ident", 0.55, [markerRow, lengthRow], true);

  let labelRow = null, bestLen = 0;
  stats.forEach((st, r) => {
    if ([markerRow, lengthRow, technicalRow].includes(r) || st.fill < 0.3) return;
    if (st.avgLen > bestLen) { bestLen = st.avgLen; labelRow = r; }
  });

  const known = [labelRow, technicalRow, markerRow, lengthRow].filter(r => r !== null);
  let headerRows = known.length ? Math.max(...known) + 1 : 1;
  while (headerRows < sheet.rows.length &&
         !sheet.rows[headerRows].some(v => (v || "").trim())) headerRows++;

  const at = (row, col) => row === null ? "" : ((sheet.rows[row] || [])[col] || "").trim();
  const width = Math.max(0, ...sheet.rows.slice(0, headerRows).map(r => r.length));
  const fields = [];
  for (let col = 0; col < width; col++) {
    const label = at(labelRow, col);
    const technical = at(technicalRow, col);
    const marker = at(markerRow, col);
    const len = at(lengthRow, col);
    const name = (technical || label).trim();
    if (!name) continue;
    const samples = sheet.rows.slice(headerRows).map(r => r[col] || "");
    fields.push({
      name, column: col, label, technical,
      mandatory: marker.includes("*") || marker.includes("+"),
      key: /k/i.test(marker),
      type: inferType(name, samples),
      maxLength: RE_INT.test(len) ? parseInt(len, 10) : null,
      allowed: allowedFor(sheet, col),
      get required() { return this.mandatory || this.key; },
    });
  }

  const notes = [];
  if (technicalRow === null) notes.push(
    "No technical-name row was found, so the mapping is onto the visible labels. " +
    "Check the filled file before uploading.");
  if (markerRow === null) notes.push(
    "No mandatory/key marker row was found, so required-field checks are limited " +
    "to what the data itself reveals.");
  if (!fields.some(f => f.allowed)) notes.push(
    "The template carries no dropdowns, so no value help could be read from it.");

  return { sheetName: sheet.name, fields, headerRows, labelRow, technicalRow, markerRow, notes };
}

/* ==========================================================================
   MATCHER — the ensemble, plus SAP vocabulary.
   ========================================================================== */
// Injected at build time from sapload/knowledge.json — the single source of
// truth this build shares with the Python toolkit. Never edit it here.
const KNOWLEDGE = /*__KNOWLEDGE__*/{ synonyms: [], thresholds: {} };
const SYNONYMS = KNOWLEDGE.synonyms;
const T = Object.assign(
  { match_minimum: 0.35, review_from: 0.5, confident_from: 0.85, synonym_floor: 0.6 },
  KNOWLEDGE.thresholds || {});
const CONCEPT = new Map();
SYNONYMS.forEach((group, id) => group.forEach(term => CONCEPT.set(term, id)));

function normalize(name) {
  return String(name)
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/[_\-./]+/g, " ")
    .replace(/[^A-Za-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim().toLowerCase();
}
const tokens = (name) => normalize(name).split(" ").filter(Boolean);

function conceptsIn(norm) {
  const found = new Set();
  if (CONCEPT.has(norm)) found.add(CONCEPT.get(norm));
  const tk = norm.split(" ").filter(Boolean);
  for (let size = Math.min(4, tk.length); size >= 1; size--) {
    for (let i = 0; i + size <= tk.length; i++) {
      const phrase = tk.slice(i, i + size).join(" ");
      if (CONCEPT.has(phrase)) found.add(CONCEPT.get(phrase));
    }
  }
  return found;
}

function levenshtein(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}
const editRatio = (a, b) => !a.length && !b.length ? 1
  : 1 - levenshtein(a, b) / Math.max(a.length, b.length);

function jaroWinkler(a, b) {
  if (a === b) return 1;
  if (!a.length || !b.length) return 0;
  const window = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
  const aF = new Array(a.length).fill(false), bF = new Array(b.length).fill(false);
  let matches = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = Math.max(0, i - window); j < Math.min(b.length, i + window + 1); j++) {
      if (bF[j] || a[i] !== b[j]) continue;
      aF[i] = bF[j] = true; matches++; break;
    }
  }
  if (!matches) return 0;
  let k = 0, trans = 0;
  for (let i = 0; i < a.length; i++) {
    if (!aF[i]) continue;
    while (!bF[k]) k++;
    if (a[i] !== b[k]) trans++;
    k++;
  }
  trans /= 2;
  const j = (matches / a.length + matches / b.length + (matches - trans) / matches) / 3;
  let prefix = 0;
  while (prefix < 4 && prefix < a.length && prefix < b.length && a[prefix] === b[prefix]) prefix++;
  return j + prefix * 0.1 * (1 - j);
}

function jaccard(a, b) {
  const A = new Set(a), B = new Set(b);
  if (!A.size || !B.size) return 0;
  let inter = 0;
  for (const x of A) if (B.has(x)) inter++;
  return inter / (A.size + B.size - inter);
}

function profile(values) {
  const real = values.map(v => String(v ?? "").trim()).filter(Boolean).slice(0, 200);
  if (!real.length) return { kind: "empty", n: 0 };
  const num = real.filter(v => /^-?[\d,]*\.?\d+$/.test(v)).length / real.length;
  const dat = real.filter(v => /^\d{4}-\d{2}-\d{2}|^\d{2}[./]\d{2}[./]\d{4}/.test(v)).length / real.length;
  const kind = dat > 0.7 ? "date" : num > 0.7 ? "number" : "text";
  return { kind, n: real.length,
           avgLen: real.reduce((a, v) => a + v.length, 0) / real.length };
}

function scorePair(sourceName, targetName, sProfile, tType) {
  const sn = normalize(sourceName), tn = normalize(targetName);
  const reasons = [];
  let score = 0;

  if (sn === tn) { score = 0.97; reasons.push("names match exactly"); }
  else {
    const sTok = tokens(sourceName), tTok = tokens(targetName);
    const jw = jaroWinkler(sn, tn);
    const ed = editRatio(sn, tn);
    const jc = jaccard(sTok, tTok);
    const sc = conceptsIn(sn), tc = conceptsIn(tn);
    let shared = 0;
    for (const c of sc) if (tc.has(c)) shared++;
    const syn = shared ? shared / Math.max(sc.size, tc.size) : 0;

    score = 0.30 * jw + 0.18 * ed + 0.24 * jc + 0.28 * syn;
    if (jc > 0.35) reasons.push("overlapping name tokens");
    if (syn > 0) { reasons.push("known synonym / abbreviation"); score = Math.max(score, T.synonym_floor); }
    if (jw > 0.9 && !reasons.length) reasons.push("names are nearly the same");
  }

  if (sProfile && sProfile.kind !== "empty" && tType) {
    if (sProfile.kind === tType) { score = Math.min(1, score + 0.08); reasons.push(tType === "text" ? "values look like text"
                                       : `values look like a ${tType}`); }
    else if (tType !== "text" && sProfile.kind !== "text") score *= 0.75;
  }
  return { score: Math.min(1, score), reasons };
}

function inadmissible(field, values) {
  const real = values.map(v => String(v ?? "").trim()).filter(Boolean).slice(0, 200);
  if (!real.length) return null;
  if (field.type === "number") {
    const num = real.filter(v => /^-?[\d,]*\.?\d+$/.test(v)).length;
    if (num / real.length < 0.5) return "holds text, but this field takes a number";
  }
  if (field.allowed && field.allowed.length) {
    const set = new Set(field.allowed.map(a => a.toLowerCase()));
    if (!real.some(v => set.has(v.toLowerCase())))
      return "no value here appears in the template's list for this field";
  }
  if (field.maxLength) {
    const over = real.filter(v => v.length > field.maxLength).length;
    if (over / real.length > 0.9)
      return `nearly every value exceeds the ${field.maxLength}-character limit`;
  }
  return null;
}

function buildMapping(schema, sourceFields, rows, overrides, memory) {
  const profiles = new Map();
  sourceFields.forEach(f => profiles.set(f, profile(rows.map(r => r[f]))));

  // Score each field against both names the template gives it, keep the better.
  // On a tie the label wins: long compound technical names share generic tokens
  // ("id", "by", "party") with unrelated columns and score spuriously.
  const candidates = [];
  schema.fields.forEach((field, idx) => {
    let best = { source: null, score: 0, reasons: [] };
    for (const alias of [field.technical || field.name, field.label || field.technical || field.name]) {
      for (const src of sourceFields) {
        const r = scorePair(src, alias, profiles.get(src), field.type);
        const remembered = memory && memory[`${src}||${alias}`];
        const score = remembered ? Math.max(r.score, 0.95) : r.score;
        const reasons = remembered ? ["confirmed on an earlier run"] : r.reasons;
        if (score >= best.score && score >= T.match_minimum) best = { source: src, score, reasons };
      }
    }
    candidates.push({ idx, field, ...best });
  });

  // Reject what the data rules out, before confidence decides anything.
  for (const c of candidates) {
    if (!c.source) continue;
    const column = c.source;
    const why = inadmissible(c.field, rows.map(r => r[column]));
    if (why) { c.source = null; c.score = 0; c.reasons = [`${column} ${why}`]; }
  }

  // One source column can only fill one field: the more confident wins.
  const taken = new Map();
  [...candidates].sort((a, b) => b.score - a.score).forEach(c => {
    if (!c.source) return;
    if (taken.has(c.source)) {
      c.source = null; c.score = 0;
      c.reasons = ["another field matched this column more strongly"];
    } else taken.set(c.source, c.idx);
  });

  // The operator's choices override everything.
  for (const c of candidates) {
    if (!(c.field.name in (overrides || {}))) continue;
    const chosen = overrides[c.field.name];
    c.source = chosen || null;
    c.score = chosen ? 1 : 0;
    c.reasons = chosen ? ["chosen by you"] : ["you left this unmapped"];
  }

  const used = new Set(candidates.filter(c => c.source).map(c => c.source));
  return {
    rows: candidates.map(c => ({
      target: c.field.name, source: c.source, confidence: c.score,
      reasons: c.reasons, required: c.field.required,
      status: !c.source ? "unmatched"
        : c.score >= T.confident_from ? "auto"
        : c.score >= T.review_from ? "review" : "low",
    })),
    unusedSources: sourceFields.filter(f => !used.has(f)),
    coverage: candidates.filter(c => c.source).length / (candidates.length || 1),
  };
}

/* ==========================================================================
   VALIDATION and RECONCILIATION
   ========================================================================== */
function applyMapping(schema, mapping, rows) {
  const bySource = new Map(mapping.rows.map(m => [m.target, m.source]));
  return rows.map(row => {
    const out = {};
    for (const f of schema.fields) {
      const src = bySource.get(f.name);
      let v = src ? row[src] : "";
      if (v != null && f.type === "date") v = toIsoDate(v);
      out[f.name] = v == null ? "" : v;
    }
    return out;
  });
}

function toIsoDate(v) {
  const s = String(v).trim();
  let m = s.match(/^(\d{2})[./](\d{2})[./](\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  m = s.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  return s;
}

function validateRows(schema, rows) {
  const issues = [];
  rows.forEach((row, i) => {
    const n = i + 1;
    for (const f of schema.fields) {
      const text = String(row[f.name] ?? "").trim();
      if (!text) { if (f.required) issues.push({ row: n, field: f.name, severity: "error",
        message: "required by the template but empty", value: "" }); continue; }
      if (f.maxLength && text.length > f.maxLength) issues.push({ row: n, field: f.name,
        severity: "error", message: `longer than the template allows (${text.length} > ${f.maxLength})`,
        value: text.slice(0, 40) });
      if (f.type === "number" && !/^-?[\d,]*\.?\d+$/.test(text.replace(/ /g, "")))
        issues.push({ row: n, field: f.name, severity: "error", message: "expected a number",
                      value: text.slice(0, 40) });
      if (f.type === "date" && !/^\d{4}-\d{2}-\d{2}$|^\d{2}[./]\d{2}[./]\d{4}$|^\d{8}$/.test(text))
        issues.push({ row: n, field: f.name, severity: "warning",
                      message: "does not look like a date SAP will accept", value: text.slice(0, 40) });
      if (f.allowed && f.allowed.length && !f.allowed.includes(text)) {
        const near = closest(text, f.allowed);
        issues.push({ row: n, field: f.name, severity: "error",
          message: near ? `not an allowed value — did you mean "${near}"?`
                        : `not one of the template's allowed values (${f.allowed.slice(0, 5).join(", ")})`,
          value: text.slice(0, 40) });
      }
    }
  });

  const errors = issues.filter(i => i.severity === "error");
  const badRows = new Set(errors.map(i => i.row));
  const grouped = new Map();
  issues.forEach(i => {
    const k = `${i.field}: ${i.message}`;
    if (!grouped.has(k)) grouped.set(k, []);
    grouped.get(k).push(i);
  });
  const top = [...grouped.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 12)
    .map(([text, group]) => ({
      count: group.length, text,
      rows: group.slice(0, 3).map(i => i.row).join(", ") +
            (group.length > 3 ? ` +${group.length - 3} more` : ""),
    }));

  return {
    issues, errors, badRows, top,
    rowCount: rows.length,
    cleanRows: rows.length - badRows.size,
    warnings: issues.filter(i => i.severity === "warning").length,
    ok: errors.length === 0,
    summary: `${rows.length} rows | ${rows.length - badRows.size} clean, ${badRows.size} with errors` +
             ` | ${errors.length} errors, ${issues.length - errors.length} warnings`,
  };
}

function closest(text, options) {
  let best = null, bestScore = 0.5;
  for (const o of options) {
    const s = jaroWinkler(text.toLowerCase(), o.toLowerCase());
    if (s > bestScore) { bestScore = s; best = o; }
  }
  return best;
}

function reconText(ctx) {
  const w = 74, L = (s) => "  " + s;
  const out = ["=".repeat(w), "  LOAD RECONCILIATION PACK", "=".repeat(w),
    L(`Run ID        ${ctx.runId}`), L(`Generated     ${ctx.generated}`),
    L(`Source        ${ctx.sourceName}`), L(`Template      ${ctx.templateName}`), "",
    "-".repeat(w), "  RECORD COUNTS", "-".repeat(w),
    L(`Extracted from source                ${String(ctx.sourceRows).padStart(10)}`),
    L(`Mapped to the template schema        ${String(ctx.sourceRows).padStart(10)}`),
    L(`Written to the upload file           ${String(ctx.written).padStart(10)}`)];
  const gap = ctx.sourceRows - ctx.written;
  out.push(L(`Difference                           ${String(gap).padStart(10)}` +
    (gap ? "   <-- INVESTIGATE" : "   (nil — reconciles)")));

  if (ctx.totals.length) {
    out.push("", "-".repeat(w), "  CONTROL TOTALS  (agree these to SAP after posting)", "-".repeat(w),
      L(`${"Field".padEnd(28)} ${"Count".padStart(8)}  ${"Total".padStart(18)}`));
    ctx.totals.forEach(t => out.push(L(`${t.field.padEnd(28)} ${String(t.count).padStart(8)}  ` +
      `${t.total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).padStart(18)}`)));
  }

  out.push("", "-".repeat(w), "  MAPPING COVERAGE", "-".repeat(w),
    L(`Template fields matched              ${(Math.round(ctx.coverage * 100) + "%").padStart(10)}`));
  if (ctx.unmapped.length) {
    out.push(L(`Template fields with no source (${ctx.unmapped.length}):`));
    ctx.unmapped.slice(0, 15).forEach(n => out.push(L(`    - ${n}`)));
  }
  if (ctx.unused.length) {
    out.push(L(`Source columns not used (${ctx.unused.length}):`));
    ctx.unused.slice(0, 15).forEach(n => out.push(L(`    - ${n}`)));
  }

  out.push("", "-".repeat(w), "  MAPPING APPLIED", "-".repeat(w));
  ctx.mapping.forEach(m => out.push(L(`${m.target.padEnd(32)} <- ` +
    `${(m.source || "(none)").padEnd(22)} ${m.source ? Math.round(m.confidence * 100) + "%" : ""}`)));

  out.push("", "-".repeat(w), "  VALIDATION", "-".repeat(w), L(ctx.validation.summary));
  if (ctx.validation.top.length) {
    out.push("");
    ctx.validation.top.forEach(t => out.push(L(
      `[${String(t.count).padStart(4)}x] ${t.text}  (rows ${t.rows})`)));
  }
  if (ctx.notes.length) {
    out.push("", "-".repeat(w), "  NOTES", "-".repeat(w));
    ctx.notes.forEach(n => out.push(L(`- ${n}`)));
  }
  out.push("", "=".repeat(w),
    "  Sign-off:  prepared by ______________   reviewed by ______________", "=".repeat(w));
  return out.join("\n");
}

function controlTotals(schema, rows) {
  const out = [];
  for (const f of schema.fields) {
    if (f.type !== "number") continue;
    let count = 0, total = 0;
    for (const r of rows) {
      const raw = String(r[f.name] ?? "").replace(/,/g, "").trim();
      if (!raw) continue;
      const n = Number(raw);
      if (Number.isFinite(n)) { total += n; count++; }
    }
    if (count) out.push({ field: f.name, count, total });
  }
  return out;
}

function parseCsv(text) {
  const rows = [];
  let field = "", row = [], inQuotes = false;
  const clean = text.replace(/^﻿/, "");
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    if (inQuotes) {
      if (ch === '"') { if (clean[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
      else field += ch;
    } else if (ch === '"') inQuotes = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (ch !== "\r") field += ch;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  if (!rows.length) return { fields: [], rows: [] };
  const header = rows[0].map(h => h.trim());
  const body = rows.slice(1).filter(r => r.some(c => (c || "").trim()))
    .map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""]).filter(([h]) => h)));
  return { fields: header.filter(Boolean), rows: body };
}

class AppError extends Error {}
