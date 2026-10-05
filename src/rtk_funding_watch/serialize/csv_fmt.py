"""CSV serializer: one row per call, list fields joined with ';'."""

from __future__ import annotations

import csv
import io

from rtk_funding_watch.models import Diff, Snapshot

# Leading characters a spreadsheet may treat as a formula (CSV-injection, OWASP).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _neutralize(value: str) -> str:
    """Prefix a cell with an apostrophe if it could be read as a formula."""
    if value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


FIELDS = (
    "id",
    "status",
    "name",
    "application_period",
    "application_start",
    "application_end",
    "deadline_note",
    "target_group",
    "purpose",
    "field_domain",
    "funding_source",
    "detail_url",
    "source_host",
    "regulation_urls",
    "document_links",
    "image_urls",
)


def dumps(snapshot: Snapshot, *, diff: Diff | None = None) -> str:
    """Return the calls as a CSV document with a header row."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for call in snapshot.calls:
        row = call.model_dump(mode="json")
        for key in ("regulation_urls", "document_links", "image_urls"):
            row[key] = ";".join(row[key])
        writer.writerow(
            {field: _neutralize(str(row.get(field, "") or "")) for field in FIELDS}
        )
    return buf.getvalue()
