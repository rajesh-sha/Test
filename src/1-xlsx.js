/* ==========================================================================
   ZIP — read and write, using the browser's own DecompressionStream.
   An .xlsx is a zip of XML. No library needed: browsers inflate for us, and
   we write entries stored (uncompressed), which is valid zip and lets Excel
   and SAP open the result unchanged.
   ========================================================================== */
const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return (buf) => {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < buf.length; i++) c = t[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  };
})();

async function inflateRaw(bytes) {
  const ds = new DecompressionStream("deflate-raw");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function readZip(arrayBuffer) {
  const buf = new Uint8Array(arrayBuffer);
  const dv = new DataView(arrayBuffer);
  // End of central directory: scan back for the signature.
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 66000; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new AppError("That file is not a valid .xlsx workbook.");

  const count = dv.getUint16(eocd + 10, true);
  let ptr = dv.getUint32(eocd + 16, true);
  const entries = new Map();
  const order = [];

  for (let n = 0; n < count; n++) {
    if (dv.getUint32(ptr, true) !== 0x02014b50) break;
    const method = dv.getUint16(ptr + 10, true);
    const csize = dv.getUint32(ptr + 20, true);
    const usize = dv.getUint32(ptr + 24, true);
    const nameLen = dv.getUint16(ptr + 28, true);
    const extraLen = dv.getUint16(ptr + 30, true);
    const commentLen = dv.getUint16(ptr + 32, true);
    const localOff = dv.getUint32(ptr + 42, true);
    const name = new TextDecoder().decode(buf.subarray(ptr + 46, ptr + 46 + nameLen));

    const lNameLen = dv.getUint16(localOff + 26, true);
    const lExtraLen = dv.getUint16(localOff + 28, true);
    const dataOff = localOff + 30 + lNameLen + lExtraLen;
    entries.set(name, { method, raw: buf.subarray(dataOff, dataOff + csize), usize });
    order.push(name);
    ptr += 46 + nameLen + extraLen + commentLen;
  }

  const files = new Map();
  for (const name of order) {
    const e = entries.get(name);
    files.set(name, e.method === 0 ? e.raw : await inflateRaw(e.raw));
  }
  return { files, order };
}

function writeZip(order, files) {
  const enc = new TextEncoder();
  const locals = [];
  const central = [];
  let offset = 0;

  for (const name of order) {
    const data = files.get(name);
    const nameBytes = enc.encode(name);
    const crc = CRC(data);

    const local = new Uint8Array(30 + nameBytes.length + data.length);
    const ldv = new DataView(local.buffer);
    ldv.setUint32(0, 0x04034b50, true);
    ldv.setUint16(4, 20, true);          // version needed
    ldv.setUint16(6, 0, true);           // flags
    ldv.setUint16(8, 0, true);           // stored
    ldv.setUint16(10, 0, true); ldv.setUint16(12, 0x2821, true);   // time/date
    ldv.setUint32(14, crc, true);
    ldv.setUint32(18, data.length, true);
    ldv.setUint32(22, data.length, true);
    ldv.setUint16(26, nameBytes.length, true);
    ldv.setUint16(28, 0, true);
    local.set(nameBytes, 30);
    local.set(data, 30 + nameBytes.length);
    locals.push(local);

    const cen = new Uint8Array(46 + nameBytes.length);
    const cdv = new DataView(cen.buffer);
    cdv.setUint32(0, 0x02014b50, true);
    cdv.setUint16(4, 20, true); cdv.setUint16(6, 20, true);
    cdv.setUint16(8, 0, true); cdv.setUint16(10, 0, true);
    cdv.setUint16(12, 0, true); cdv.setUint16(14, 0x2821, true);
    cdv.setUint32(16, crc, true);
    cdv.setUint32(20, data.length, true);
    cdv.setUint32(24, data.length, true);
    cdv.setUint16(28, nameBytes.length, true);
    cdv.setUint32(42, offset, true);
    cen.set(nameBytes, 46);
    central.push(cen);
    offset += local.length;
  }

  const cenSize = central.reduce((a, c) => a + c.length, 0);
  const end = new Uint8Array(22);
  const edv = new DataView(end.buffer);
  edv.setUint32(0, 0x06054b50, true);
  edv.setUint16(8, order.length, true);
  edv.setUint16(10, order.length, true);
  edv.setUint32(12, cenSize, true);
  edv.setUint32(16, offset, true);

  return new Blob([...locals, ...central, end],
    { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

/* ==========================================================================
   XLSX — parse the parts we need, and refill one sheet without touching
   anything else. Only <sheetData> is replaced, so SAP's styling, dropdowns,
   column widths and help sheets survive exactly as they were.
   ========================================================================== */
const XML = (s) => new DOMParser().parseFromString(s, "application/xml");
const dec = (b) => new TextDecoder().decode(b);
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function colToIndex(ref) {
  let n = 0;
  for (const ch of ref) {
    if (!/[A-Za-z]/.test(ch)) break;
    n = n * 26 + (ch.toUpperCase().charCodeAt(0) - 64);
  }
  return n - 1;
}
function indexToCol(i) {
  let out = "", n = i + 1;
  while (n > 0) { const r = (n - 1) % 26; out = String.fromCharCode(65 + r) + out; n = Math.floor((n - 1) / 26); }
  return out;
}

const RE_SHEETDATA = /<sheetData\b[^>]*\/>|<sheetData\b[^>]*>[\s\S]*?<\/sheetData>/;
const RE_ROW = /<row\b[^>]*\/>|<row\b[^>]*>[\s\S]*?<\/row>/g;
const RE_CELL = /<c\b[^>]*\/>|<c\b[^>]*>[\s\S]*?<\/c>/g;

function attrs(tag) {
  const head = tag.split(">")[0];
  const out = {};
  for (const m of head.matchAll(/(\w+)="([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}
function unesc(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
          .replace(/&apos;/g, "'").replace(/&amp;/g, "&");
}

async function openWorkbook(arrayBuffer) {
  const { files, order } = await readZip(arrayBuffer);

  let shared = [];
  if (files.has("xl/sharedStrings.xml")) {
    const doc = XML(dec(files.get("xl/sharedStrings.xml")));
    shared = [...doc.getElementsByTagName("si")].map(si =>
      [...si.getElementsByTagName("t")].map(t => t.textContent || "").join(""));
  }

  const rels = new Map();
  if (files.has("xl/_rels/workbook.xml.rels")) {
    const doc = XML(dec(files.get("xl/_rels/workbook.xml.rels")));
    for (const r of doc.getElementsByTagName("Relationship")) {
      rels.set(r.getAttribute("Id"), r.getAttribute("Target"));
    }
  }

  const sheets = [];
  if (files.has("xl/workbook.xml")) {
    const doc = XML(dec(files.get("xl/workbook.xml")));
    for (const sh of doc.getElementsByTagName("sheet")) {
      const rid = sh.getAttribute("r:id") ||
        sh.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id");
      const target = rels.get(rid);
      if (!target) continue;
      const path = target.startsWith("xl/") ? target : "xl/" + target.replace(/^\//, "");
      if (!files.has(path)) continue;
      sheets.push({ name: sh.getAttribute("name") || "", path,
                    ...parseSheet(dec(files.get(path)), shared) });
    }
  }
  if (!sheets.length) throw new AppError("That workbook has no readable sheets.");
  return { files, order, sheets };
}

function parseSheet(xml, shared) {
  const body = xml.match(RE_SHEETDATA);
  const rows = [], rowXml = [], styles = new Map();
  if (body) {
    const rowTags = body[0].match(RE_ROW) || [];
    rowTags.forEach((rowTag, r) => {
      rowXml.push(rowTag);
      const values = [], rowStyles = new Map();
      for (const cellTag of rowTag.match(RE_CELL) || []) {
        const a = attrs(cellTag);
        const col = colToIndex(a.r || "");
        if (col < 0) continue;
        while (values.length <= col) values.push("");
        values[col] = cellText(cellTag, a, shared);
        if (a.s) rowStyles.set(col, a.s);
      }
      rows.push(values);
      if (rowStyles.size) styles.set(r, rowStyles);
    });
  }
  return { rows, rowXml, styles, validations: parseValidations(xml), xml };
}

function cellText(tag, a, shared) {
  if (a.t === "inlineStr") {
    const m = tag.match(/<t[^>]*>([\s\S]*?)<\/t>/);
    return m ? unesc(m[1]) : "";
  }
  const m = tag.match(/<v>([\s\S]*?)<\/v>/);
  if (!m) return "";
  const text = unesc(m[1]);
  if (a.t === "s") { const i = parseInt(text, 10); return shared[i] ?? ""; }
  return text;
}

function parseValidations(xml) {
  const out = [];
  const blocks = xml.match(/<dataValidation\b[^>]*>[\s\S]*?<\/dataValidation>|<dataValidation\b[^>]*\/>/g) || [];
  for (const block of blocks) {
    const a = attrs(block);
    if (a.type !== "list" || !a.sqref) continue;
    let first = null, last = null;
    for (const token of a.sqref.replace(/:/g, " ").split(/\s+/)) {
      const i = colToIndex(token);
      if (i < 0) continue;
      first = first === null ? i : Math.min(first, i);
      last = last === null ? i : Math.max(last, i);
    }
    if (first === null) continue;
    const f = block.match(/<formula1[^>]*>([\s\S]*?)<\/formula1>/);
    let values = [];
    if (f) {
      const literal = unesc(f[1]).trim();
      if (literal.startsWith('"') && literal.endsWith('"')) {
        values = literal.slice(1, -1).split(",").map(v => v.trim()).filter(Boolean);
      }
    }
    if (values.length) out.push({ first, last, values });
  }
  return out;
}

function allowedFor(sheet, col) {
  for (const v of sheet.validations) if (col >= v.first && col <= v.last) return v.values;
  return null;
}

function fillWorkbook(wb, sheet, schema, dataRows) {
  const numeric = new Set(schema.fields.filter(f => f.type === "number").map(f => f.column));
  const styleRow = sheet.styles.get(schema.headerRows) || new Map();
  const parts = ["<sheetData>"];
  for (let i = 0; i < schema.headerRows; i++) parts.push(sheet.rowXml[i] || "");
  dataRows.forEach((cells, n) => {
    const rowNo = schema.headerRows + n + 1;
    const out = [];
    cells.forEach((value, col) => {
      if (value === null || value === undefined || value === "") return;
      const s = styleRow.get(col) ? ` s="${styleRow.get(col)}"` : "";
      const text = String(value);
      if (numeric.has(col) && /^-?\d+(\.\d+)?$/.test(text.trim())) {
        out.push(`<c r="${indexToCol(col)}${rowNo}"${s}><v>${text.trim()}</v></c>`);
      } else {
        out.push(`<c r="${indexToCol(col)}${rowNo}"${s} t="inlineStr"><is>` +
                 `<t xml:space="preserve">${esc(text)}</t></is></c>`);
      }
    });
    parts.push(`<row r="${rowNo}">${out.join("")}</row>`);
  });
  parts.push("</sheetData>");

  const patched = sheet.xml.replace(RE_SHEETDATA, parts.join(""));
  const files = new Map(wb.files);
  files.set(sheet.path, new TextEncoder().encode(patched));
  return writeZip(wb.order, files);
}
