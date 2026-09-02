"""sapload — turn a legacy extract into a filled SAP upload template.

Point it at an SAP-delivered spreadsheet template and a source extract.  It
reads the template to work out what SAP wants, auto-maps the extract onto it,
validates every row against rules it derived rather than rules anyone wrote,
writes the filled template with SAP's own formatting intact, and produces the
reconciliation pack that makes the load an auditable control.

    from sapload import load

    result = load("fsm_claims.csv", "Supplier Invoice_EN.xlsx",
                  output_path="upload.xlsx", memory_path="mappings.json")
    print(result.plan.summary())
    print(result.validation.summary())
    print(result.recon.as_text())

Zero dependencies beyond the standard library and smartmapper, so it runs on a
locked-down laptop, a scheduled job, or a Cloud Foundry app without change.
"""

from .pipeline import LoadResult, load, read_source
from .recon import ControlTotal, ReconPack, build_recon
from .schema import TargetField, TargetSchema
from .template import read_template
from .validate import Issue, ValidationReport, validate
from .xlsx import Sheet, Workbook

__all__ = [
    "load", "LoadResult", "read_source",
    "read_template", "TargetSchema", "TargetField",
    "validate", "ValidationReport", "Issue",
    "build_recon", "ReconPack", "ControlTotal",
    "Workbook", "Sheet",
]

__version__ = "0.1.0"
