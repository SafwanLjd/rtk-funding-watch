"""Static website generator for rtk-funding-watch.

:func:`build_site` is the entry point the CLI calls: it renders ``index.html``
and copies the bundled CSS/JS into ``out_dir/static/``. The machine-readable
endpoints (``api/calls.json`` etc.) are written separately by the CLI next to
``index.html``; this module only links to them.

Templates are loaded with Jinja2's :class:`~jinja2.PackageLoader` and static
assets with :mod:`importlib.resources`, so everything works when the project is
installed as a wheel.
"""

from __future__ import annotations

import datetime as dt
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from rtk_funding_watch import serialize
from rtk_funding_watch.models import (
    ChangeEvent,
    ChangeType,
    Diff,
    FundingCall,
    Snapshot,
    Status,
)

__all__ = ["build_site", "render_index"]

PROJECT_NAME = "RTK Funding Watch"
TAGLINE = (
    "A watchdog that scrapes funding calls published by Riigi "
    "Tugiteenuste Keskus (rtk.ee) and republishes them in open, "
    "machine-readable formats."
)
MCP_COMMAND = "rtk-funding-mcp"

_STATUS_LABELS: dict[Status, str] = {
    Status.OPEN: "Open",
    Status.UPCOMING: "Upcoming",
    Status.CLOSED: "Closed",
}
_STATUS_ORDER = (Status.OPEN, Status.UPCOMING, Status.CLOSED)

_FORMAT_LABELS: dict[str, str] = {
    "json": "JSON",
    "toon": "TOON",
    "csv": "CSV",
    "rss": "RSS feed",
}

_CHANGE_LABELS: dict[ChangeType, str] = {
    ChangeType.ADDED: "New",
    ChangeType.REMOVED: "Removed",
    ChangeType.MODIFIED: "Updated",
    ChangeType.STATUS_CHANGED: "Status",
}


def _format_date(value: dt.date) -> str:
    """Render a date in the Estonian ``DD.MM.YYYY`` convention."""
    return f"{value.day:02d}.{value.month:02d}.{value.year}"


def _window(call: FundingCall) -> str:
    """Human-readable application window, falling back to the raw period text."""
    start, end = call.application_start, call.application_end
    if start and end:
        return f"{_format_date(start)} \u2013 {_format_date(end)}"
    if start:
        return f"alates {_format_date(start)}"
    if end:
        return f"kuni {_format_date(end)}"
    return call.application_period


def _search_text(call: FundingCall) -> str:
    """Lowercased blob the client-side search matches against."""
    parts = [
        call.name,
        call.purpose,
        call.target_group,
        call.field_domain,
        call.funding_source,
        call.application_period,
        _STATUS_LABELS[call.status],
    ]
    return " ".join(p for p in parts if p).lower()


def _call_view(call: FundingCall) -> dict[str, object]:
    """Flatten a call into template-friendly primitives."""
    return {
        "id": call.id,
        "name": call.name,
        "status": call.status.value,
        "status_label": _STATUS_LABELS[call.status],
        "detail_url": call.detail_url,
        "window": _window(call),
        "deadline_note": call.deadline_note,
        "field_domain": call.field_domain,
        "funding_source": call.funding_source,
        "target_group": call.target_group,
        "purpose": call.purpose,
        "regulations": call.regulation_urls,
        "documents": call.document_links,
        "images": call.image_urls,
        "search_text": _search_text(call),
    }


def _change_detail(event: ChangeEvent) -> str:
    """One-line description of what changed, for the recent-changes list."""
    if event.old_status and event.new_status:
        return f"{event.old_status.value} \u2192 {event.new_status.value}"
    if event.new_status:
        return f"now {event.new_status.value}"
    if event.old_status:
        return f"was {event.old_status.value}"
    if event.changes:
        return "changed: " + ", ".join(c.field for c in event.changes)
    return ""


def _change_view(event: ChangeEvent) -> dict[str, object]:
    return {
        "type": event.type.value,
        "type_label": _CHANGE_LABELS[event.type],
        "name": event.name,
        "detail_url": event.detail_url,
        "detail_text": _change_detail(event),
    }


def _endpoints() -> list[dict[str, str]]:
    """Links to the machine-readable files the CLI writes under ``api/``."""
    return [
        {
            "label": _FORMAT_LABELS.get(fmt, fmt.upper()),
            "href": f"./api/{serialize.file_name(fmt)}",
        }
        for fmt in serialize.FORMATS
    ]


def _environment() -> Environment:
    return Environment(
        loader=PackageLoader("rtk_funding_watch", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _context(snapshot: Snapshot, diff: Diff | None) -> dict[str, object]:
    counts = snapshot.counts()
    scraped_at = snapshot.scraped_at
    statuses = [
        {
            "value": status.value,
            "label": _STATUS_LABELS[status],
            "count": counts.get(status.value, 0),
        }
        for status in _STATUS_ORDER
    ]
    order = {status: index for index, status in enumerate(_STATUS_ORDER)}
    ordered_calls = sorted(
        snapshot.calls, key=lambda c: (order[c.status], c.name.lower())
    )
    changes: list[dict[str, object]] | None = None
    if diff is not None and not diff.is_empty():
        changes = [_change_view(event) for event in diff.events]
    return {
        "project_name": PROJECT_NAME,
        "tagline": TAGLINE,
        "generator": snapshot.generator,
        "source_url": snapshot.source_url,
        "scraped_at_iso": scraped_at.isoformat(),
        "scraped_at_human": scraped_at.strftime("%Y-%m-%d %H:%M %Z").strip(),
        "counts": counts,
        "endpoints": _endpoints(),
        "mcp_command": MCP_COMMAND,
        "changes": changes,
        "statuses": statuses,
        "calls": [_call_view(call) for call in ordered_calls],
        "common_resources": snapshot.common_resources,
    }


def render_index(snapshot: Snapshot, diff: Diff | None = None) -> str:
    """Render the ``index.html`` page to a string without touching disk."""
    env = _environment()
    template = env.get_template("index.html")
    return template.render(**_context(snapshot, diff))


def _copy_static(out_dir: Path) -> list[Path]:
    """Copy the bundled static assets into ``out_dir/static/``."""
    dest = out_dir / "static"
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    static_root = files("rtk_funding_watch") / "static"
    for entry in static_root.iterdir():
        if not entry.is_file():
            continue
        target = dest / entry.name
        target.write_bytes(entry.read_bytes())
        written.append(target)
    return written


def build_site(snapshot: Snapshot, diff: Diff | None, out_dir: Path) -> list[Path]:
    """Render the static site into ``out_dir`` and return the written file paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    index_path = out_dir / "index.html"
    index_path.write_text(render_index(snapshot, diff), encoding="utf-8")

    written = [index_path, *_copy_static(out_dir)]
    return written
