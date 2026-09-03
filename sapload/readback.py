"""Read what SAP actually posted, and agree it to what we sent.

SAP delivers no source-to-target reconciliation, and on the Service Stream
integration slide three of the four flows end with "SAP report to reconcile
load to FSM". This closes that: after the upload, read the posted documents
back by the reference the load stamped on them, and produce sent / posted /
missing with the value variance.

That artefact — not the upload file — is what makes a recurring batch load an
auditable control rather than a spreadsheet someone ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .sapclient import S4Client, SapError

# Where a source reference conventionally lives on a posted document.
# Lengths are the standard DDIC ones; confirm against your tenant's $metadata
# before fixing a token format, because a silent truncation breaks the join.
REFERENCE_FIELDS = {
    "header_reference": ("XBLNR", 16),
    "header_text": ("BKTXT", 25),
    "item_assignment": ("ZUONR", 18),
}

JOURNAL_ITEMS = "/sap/opu/odata/sap/API_JOURNALENTRYITEMBASIC_SRV/A_JournalEntryItemBasic"
SUPPLIER_INVOICES = "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice"


@dataclass
class Match:
    reference: str
    sent_amount: Optional[float]
    posted_amount: Optional[float]
    document: Optional[str]
    status: str            # posted | missing | variance | unexpected

    @property
    def variance(self) -> Optional[float]:
        if self.sent_amount is None or self.posted_amount is None:
            return None
        return round(self.posted_amount - self.sent_amount, 2)


@dataclass
class ReadbackReport:
    entity: str
    matches: List[Match] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(1 for m in self.matches if m.status == status)

    @property
    def ok(self) -> bool:
        return not (self._count("missing") or self._count("variance")
                    or self._count("unexpected"))

    def as_text(self) -> str:
        w = 74
        sent_total = sum(m.sent_amount or 0 for m in self.matches)
        posted_total = sum(m.posted_amount or 0 for m in self.matches)
        out = ["=" * w, "  POST-LOAD RECONCILIATION — SENT vs POSTED", "=" * w,
               f"  Read from    {self.entity.rsplit('/', 1)[-1]}", "",
               "-" * w, "  AGREEMENT", "-" * w,
               f"  Sent to SAP                          {len(self.matches):>10,}",
               f"  Found posted                         {self._count('posted'):>10,}",
               f"  Not found                            {self._count('missing'):>10,}",
               f"  Posted with a different value        {self._count('variance'):>10,}",
               f"  Posted but not sent by this run      {self._count('unexpected'):>10,}",
               "",
               f"  Value sent                     {sent_total:>16,.2f}",
               f"  Value posted                   {posted_total:>16,.2f}",
               f"  Difference                     {posted_total - sent_total:>16,.2f}"
               + ("   (nil — agrees)" if abs(posted_total - sent_total) < 0.005
                  else "   <-- INVESTIGATE")]

        exceptions = [m for m in self.matches if m.status != "posted"]
        if exceptions:
            out += ["", "-" * w, "  EXCEPTIONS", "-" * w,
                    f"  {'Reference':<22} {'Status':<12} {'Sent':>14} {'Posted':>14}"]
            for m in exceptions[:60]:
                sent = f"{m.sent_amount:,.2f}" if m.sent_amount is not None else "—"
                post = f"{m.posted_amount:,.2f}" if m.posted_amount is not None else "—"
                out.append(f"  {m.reference[:22]:<22} {m.status:<12} {sent:>14} {post:>14}")
            if len(exceptions) > 60:
                out.append(f"  … {len(exceptions) - 60} more")

        if self.notes:
            out += ["", "-" * w, "  NOTES", "-" * w] + [f"  - {n}" for n in self.notes]
        out += ["", "=" * w,
                "  Sign-off:  prepared by ______________   reviewed by ______________",
                "=" * w]
        return "\n".join(out)


def reconcile(
    client: S4Client,
    sent: Sequence[dict],
    reference_field: str,
    amount_field: Optional[str] = None,
    entity: str = SUPPLIER_INVOICES,
    posted_reference_property: str = "SupplierInvoiceIDByInvcgParty",
    posted_amount_property: Optional[str] = "InvoiceGrossAmount",
    posted_key_property: str = "SupplierInvoice",
    extra_filter: Optional[str] = None,
) -> ReadbackReport:
    """Compare rows we sent against what the tenant now holds.

    Reads only the documents whose reference we stamped, so the query stays
    small and the result is unambiguous — no date windows, no guessing.
    """
    report = ReadbackReport(entity=entity)
    references = [str(r.get(reference_field, "")).strip() for r in sent]
    references = [r for r in references if r]
    if not references:
        report.notes.append(
            f"No values in {reference_field!r} to reconcile on. Stamp a unique "
            f"reference on every row before loading, or there is nothing to join to."
        )
        return report

    sent_amounts: Dict[str, Optional[float]] = {}
    for row in sent:
        ref = str(row.get(reference_field, "")).strip()
        if not ref:
            continue
        sent_amounts[ref] = _number(row.get(amount_field)) if amount_field else None

    posted: Dict[str, dict] = {}
    unread: List[str] = []
    for batch in _chunks(sorted(set(references)), 40):
        clause = " or ".join(
            f"{posted_reference_property} eq '{_escape(r)}'" for r in batch)
        if extra_filter:
            clause = f"({clause}) and ({extra_filter})"
        try:
            rows = client.get_all(entity, {"$filter": clause}, page=200, cap=2000)
        except SapError as exc:
            unread.extend(batch)
            report.notes.append(f"Could not read one batch: {exc}")
            continue
        for row in rows:
            ref = str(row.get(posted_reference_property, "")).strip()
            if ref:
                posted[ref] = row

    for ref in sorted(sent_amounts):
        if ref in unread:
            continue
        row = posted.get(ref)
        sent_amount = sent_amounts[ref]
        if row is None:
            report.matches.append(Match(ref, sent_amount, None, None, "missing"))
            continue
        posted_amount = (_number(row.get(posted_amount_property))
                         if posted_amount_property else None)
        document = str(row.get(posted_key_property, "")) or None
        differs = (sent_amount is not None and posted_amount is not None
                   and abs(posted_amount - sent_amount) >= 0.005)
        report.matches.append(Match(ref, sent_amount, posted_amount, document,
                                    "variance" if differs else "posted"))

    for ref, row in posted.items():
        if ref not in sent_amounts:
            report.matches.append(Match(
                ref, None, _number(row.get(posted_amount_property)),
                str(row.get(posted_key_property, "")) or None, "unexpected"))

    if unread:
        report.notes.append(f"{len(unread)} reference(s) could not be read and are "
                            f"neither confirmed nor denied.")
    return report


def _chunks(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


def _escape(value: str) -> str:
    """OData string literals escape a single quote by doubling it."""
    return value.replace("'", "''")


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None
