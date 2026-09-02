"""SAP and finance vocabulary, layered onto the matcher's general knowledge.

The base matcher knows that ``dob`` means date of birth.  It has no reason to
know that ``vendor_id`` and ``Supplier`` are the same party, that ``gl_acct``
is a G/L account, or that a work order number is what ends up in the
assignment field.  This module supplies that missing half.

It is deliberately editable and deliberately boring — a list of things that
mean the same thing, in the vocabulary of the systems actually in play.  Adding
a client's own terms here is the cheapest accuracy improvement available, and
it needs no model, no training and no network call.
"""

from __future__ import annotations

from typing import List

from smartmapper.knowledge import register_synonyms

# Each inner list is one concept expressed in SAP terms, common ERP shorthand,
# and the conventions used by upstream systems (ServiceNow, FSM, billing).
SAP_SYNONYM_GROUPS: List[List[str]] = [
    # --- parties -------------------------------------------------------- #
    ["supplier", "vendor", "creditor", "sub contractor", "subcontractor",
     "vendor id", "supplier number", "lifnr"],
    ["customer", "debtor", "payer", "sold to party", "bill to party", "kunnr"],
    ["business partner", "bp", "partner", "partner number"],

    # --- organisational units ------------------------------------------- #
    ["company code", "company", "bukrs", "entity", "legal entity", "co code"],
    ["cost center", "cost centre", "kostl", "cctr"],
    ["profit center", "profit centre", "prctr"],
    ["plant", "werks", "site"],
    ["business area", "segment"],
    ["sales organization", "sales org", "vkorg"],
    ["purchasing organization", "purchasing org", "ekorg"],
    ["wbs element", "wbs", "work breakdown structure", "posid", "project element"],
    ["project", "project definition", "pspid"],
    ["network", "network order", "network activity"],

    # --- accounts and amounts ------------------------------------------- #
    ["gl account", "g l account", "general ledger account", "gl acct", "gl",
     "account number", "hkont", "saknr", "ledger account"],
    ["account assignment", "acct assignment", "assignment category"],
    ["gross amount", "gross", "amount including tax", "invoice gross amount",
     "total amount", "claim amount", "claim value"],
    ["net amount", "net", "amount excluding tax"],
    ["tax amount", "gst amount", "vat amount"],
    ["tax code", "gst code", "vat code", "mwskz", "tax indicator"],
    ["currency", "currency code", "waers", "ccy", "curr", "document currency"],
    ["quantity", "qty", "consumed quantity", "menge", "units"],
    ["unit of measure", "uom", "meins", "unit"],
    ["exchange rate", "fx rate", "conversion rate"],

    # --- documents ------------------------------------------------------- #
    ["document number", "doc number", "belnr", "document id"],
    ["document type", "doc type", "blart"],
    ["document date", "invoice date", "bldat", "doc date", "claim date",
     "invoice dt", "inv dt", "doc dt", "document dt"],
    ["posting date", "budat", "post date", "gl date", "accounting date",
     "post dt", "posting dt", "gl dt"],
    ["baseline date", "due date", "net due date", "payment due"],
    ["fiscal year", "year", "gjahr"],
    ["period", "posting period", "fiscal period", "monat"],
    ["reference", "reference document", "external reference", "xblnr",
     "invoice number", "invoice reference", "claim number", "claim id",
     "rcti number", "supplier invoice id"],
    ["assignment", "assignment reference", "zuonr", "allocation",
     "work order", "work order number", "wo number", "job number"],
    ["header text", "document header text", "bktxt", "narration"],
    ["line item text", "item text", "sgtxt", "description", "descr"],
    ["purchase order", "po", "po number", "ebeln"],
    ["purchase requisition", "pr", "requisition", "banfn"],
    ["sales order", "so", "sales order number", "vbeln"],
    ["service order", "srvo", "service order number"],
    ["billing document", "invoice document", "billing doc"],
    ["material", "product", "material number", "matnr", "item code", "sku"],
    ["storage location", "sloc", "lgort"],
    ["movement type", "mvt type", "bwart"],

    # --- upstream-system conventions ------------------------------------ #
    # Deliberately NOT given a concept: sys_id, row_id and similar surrogate
    # keys belong to the source system and map to nothing in SAP.  Leaving them
    # unknown keeps them from bridging to real SAP id fields on the shared
    # token "id" and stealing a match from the field that genuinely belongs
    # there, such as a claim or invoice reference.
    ["approval status", "approval state", "workflow status"],
    ["created on", "created date", "opened at", "raised on"],
]

_REGISTERED = False


def install() -> None:
    """Register the SAP vocabulary with the matcher.  Safe to call repeatedly."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_synonyms(SAP_SYNONYM_GROUPS)
    _REGISTERED = True


def extend(groups: List[List[str]]) -> None:
    """Add a client's own house vocabulary on top of the SAP defaults."""
    install()
    register_synonyms(groups)
