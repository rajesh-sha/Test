"""Post documents to S/4HANA from mapped rows, one profile at a time.

The profile in ``knowledge.json`` is deliberately thin — a service path, an
entity, where the items hang, and which field is the document key. It does not
list field names, because the field names come from your own mapping. That way
a profile does not quietly go stale when SAP renames something, and adding
sales order or purchase requisition is a config entry rather than a build.

Three things make this safe enough to point at a production ledger:

**Check before you post.** ``check()`` reads the tenant's own ``$metadata`` and
tells you which of your mapped fields the entity does not actually have. A
typo becomes a message rather than 800 rejected documents.

**Skip what is already there.** Before posting, the references you are about to
send are read back. Anything already posted is skipped. That makes a re-run
after a partial failure safe, which matters because what an upload does with a
mid-file failure is not documented.

**One document per request.** Not a batch. A batch that half-applies is a
reconciliation problem; a document that fails on its own is a line in a report.
Writes are never retried — a timeout on a POST may mean it posted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .sapclient import NotPermitted, S4Client, SapError
from .vocabulary import knowledge


class ProfileError(Exception):
    """The profile or the request does not make sense. Safe to show a user."""


def profiles() -> Dict[str, dict]:
    return {k: v for k, v in knowledge().get("documents", {}).items()
            if not k.startswith("_")}


def load_profile(key: str) -> dict:
    found = profiles().get(key)
    if not found:
        known = ", ".join(sorted(profiles())) or "none"
        raise ProfileError(f"No profile named {key!r}. Available: {known}")
    return {**found, "key": key}


# --------------------------------------------------------------------------- #
# Checking a mapping against the tenant's own metadata
# --------------------------------------------------------------------------- #
@dataclass
class FieldCheck:
    entity: str
    known: Set[str]
    unknown: List[str] = field(default_factory=list)
    checked: bool = True
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.unknown

    def as_text(self) -> str:
        if not self.checked:
            return f"  Could not check {self.entity}: {self.note}"
        if self.ok:
            return f"  {self.entity}: all mapped fields exist ({len(self.known)} available)"
        lines = [f"  {self.entity}: {len(self.unknown)} mapped field(s) do not exist:"]
        for name in self.unknown:
            near = _closest(name, self.known)
            lines.append(f"      - {name}" + (f"   did you mean {near!r}?" if near else ""))
        return "\n".join(lines)


def entity_properties(edmx: str, entity_type: str) -> Set[str]:
    """Property names of one EntityType, read straight from $metadata.

    Parsed with a regex rather than a DOM because $metadata differs between
    OData V2 and V4 in namespace and shape, and all we need is the property
    names inside one named EntityType.
    """
    pattern = re.compile(
        r'<EntityType\b[^>]*\bName="' + re.escape(entity_type) + r'"[^>]*>(.*?)</EntityType>',
        re.DOTALL)
    match = pattern.search(edmx)
    if not match:
        return set()
    return set(re.findall(r'<Property\b[^>]*\bName="([^"]+)"', match.group(1)))


def check(client: S4Client, profile: dict, header_fields: Sequence[str],
          item_fields: Optional[Sequence[str]] = None) -> List[FieldCheck]:
    """Verify mapped field names against the tenant. Read-only."""
    try:
        edmx = client.metadata(profile["service"])
    except SapError as exc:
        return [FieldCheck(entity=profile.get("entity_type", profile["entity"]),
                           known=set(), checked=False, note=str(exc))]

    out: List[FieldCheck] = []
    targets = [(profile.get("entity_type") or profile["entity"], list(header_fields))]
    items = profile.get("items") or {}
    if item_fields and items.get("entity_type"):
        targets.append((items["entity_type"], list(item_fields)))

    for entity_type, fields in targets:
        known = entity_properties(edmx, entity_type)
        if not known:
            out.append(FieldCheck(entity=entity_type, known=set(), checked=False,
                                  note="that entity type is not in this service's "
                                       "$metadata — check the profile"))
            continue
        out.append(FieldCheck(entity=entity_type, known=known,
                              unknown=[f for f in fields if f not in known]))
    return out


def _closest(name: str, options: Set[str]) -> Optional[str]:
    import difflib
    near = difflib.get_close_matches(name, sorted(options), n=1, cutoff=0.75)
    return near[0] if near else None


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #
@dataclass
class Posted:
    reference: str
    status: str            # posted | skipped | failed | would-post
    document: Optional[str] = None
    message: str = ""


@dataclass
class PostReport:
    profile: str
    dry_run: bool
    results: List[Posted] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def ok(self) -> bool:
        return self.count("failed") == 0

    def as_text(self) -> str:
        w = 74
        head = "DRY RUN — nothing was sent" if self.dry_run else "POSTING RESULT"
        out = ["=" * w, f"  {head}", "=" * w,
               f"  Profile      {self.profile}",
               f"  Documents    {len(self.results)}", "",
               "-" * w, "  OUTCOME", "-" * w]
        for status, label in (("would-post", "Would be posted"), ("posted", "Posted"),
                              ("skipped", "Already in SAP, skipped"),
                              ("failed", "Failed")):
            n = self.count(status)
            if n or status == "failed":
                out.append(f"  {label:<36}{n:>10,}")

        failures = [r for r in self.results if r.status == "failed"]
        if failures:
            out += ["", "-" * w, "  FAILURES", "-" * w]
            for r in failures[:40]:
                out.append(f"  {r.reference[:24]:<24} {r.message[:44]}")
            if len(failures) > 40:
                out.append(f"  … {len(failures) - 40} more")

        posted = [r for r in self.results if r.status == "posted"]
        if posted:
            out += ["", "-" * w, "  DOCUMENTS CREATED", "-" * w]
            for r in posted[:40]:
                out.append(f"  {r.reference[:24]:<24} -> {r.document}")
            if len(posted) > 40:
                out.append(f"  … {len(posted) - 40} more")

        if self.notes:
            out += ["", "-" * w, "  NOTES", "-" * w] + [f"  - {n}" for n in self.notes]
        out += ["", "=" * w,
                "  Sign-off:  prepared by ______________   reviewed by ______________",
                "=" * w]
        return "\n".join(out)


def already_posted(client: S4Client, profile: dict, reference_field: str,
                   references: Sequence[str]) -> Tuple[Set[str], List[str]]:
    """Which of these references already exist in SAP.

    Returns ``(found, notes)``. A reference we could not check is NOT reported
    as absent — it is left out of ``found`` and a note explains why, so the
    caller can decide rather than posting a duplicate on a failed lookup.
    """
    found: Set[str] = set()
    notes: List[str] = []
    entity = f"{profile['service'].rstrip('/')}/{profile['entity']}"
    unique = sorted({r for r in references if r})
    for i in range(0, len(unique), 40):
        batch = unique[i:i + 40]
        clause = " or ".join(f"{reference_field} eq '{r.replace(chr(39), chr(39) * 2)}'"
                             for r in batch)
        try:
            rows = client.get_all(entity, {"$filter": clause}, page=200, cap=2000)
        except SapError as exc:
            notes.append(f"Could not check {len(batch)} reference(s) for duplicates: {exc}")
            continue
        for row in rows:
            value = str(row.get(reference_field, "")).strip()
            if value:
                found.add(value)
    return found, notes


def post(
    client: S4Client,
    profile: dict,
    rows: Sequence[dict],
    reference_field: str,
    item_rows: Optional[Dict[str, List[dict]]] = None,
    dry_run: bool = False,
    skip_existing: bool = True,
) -> PostReport:
    """Post one document per row, skipping references already in SAP."""
    report = PostReport(profile=profile.get("key", "?"), dry_run=dry_run)
    for warning in profile.get("verify", []):
        report.notes.append(f"Verify: {warning}")

    if not rows:
        report.notes.append("No rows to post.")
        return report

    missing_ref = sum(1 for r in rows if not str(r.get(reference_field, "")).strip())
    if missing_ref:
        raise ProfileError(
            f"{missing_ref} row(s) have no value in {reference_field!r}. Every "
            f"document needs a unique reference, or duplicates cannot be "
            f"prevented and the load cannot be reconciled afterwards."
        )

    references = [str(r[reference_field]).strip() for r in rows]
    duplicates = {r for r in references if references.count(r) > 1}
    if duplicates:
        raise ProfileError(
            f"{len(duplicates)} reference(s) appear more than once in the source, "
            f"for example {sorted(duplicates)[:3]}. Each document needs its own."
        )

    existing: Set[str] = set()
    if skip_existing and not dry_run:
        existing, notes = already_posted(client, profile, reference_field, references)
        report.notes.extend(notes)
        if existing:
            report.notes.append(
                f"{len(existing)} reference(s) were already in SAP and were skipped. "
                f"Re-running after a partial failure is safe.")

    entity = f"{profile['service'].rstrip('/')}/{profile['entity']}"
    navigation = (profile.get("items") or {}).get("navigation")

    for row in rows:
        reference = str(row[reference_field]).strip()
        if reference in existing:
            report.results.append(Posted(reference, "skipped"))
            continue

        payload = {k: v for k, v in row.items()
                   if v is not None and str(v).strip() != ""}
        children = (item_rows or {}).get(reference)
        if children and navigation:
            payload[navigation] = [
                {k: v for k, v in child.items()
                 if v is not None and str(v).strip() != ""}
                for child in children
            ]

        if dry_run:
            report.results.append(Posted(reference, "would-post"))
            continue

        try:
            created = client.post(entity, payload)
        except NotPermitted as exc:
            raise
        except SapError as exc:
            report.results.append(Posted(reference, "failed", message=str(exc)))
            continue

        report.results.append(Posted(
            reference, "posted",
            document=_document_key(created, profile.get("document_key", ""))))

    return report


def _document_key(created: Dict[str, Any], key: str) -> Optional[str]:
    node = created.get("d", created)
    if isinstance(node, dict):
        value = node.get(key)
        if value:
            return str(value)
    return None
