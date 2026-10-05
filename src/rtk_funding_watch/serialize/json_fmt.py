"""JSON serializer: Pydantic's canonical JSON for the whole snapshot."""

from __future__ import annotations

from rtk_funding_watch.models import Diff, Snapshot


def dumps(snapshot: Snapshot, *, diff: Diff | None = None) -> str:
    """Return the snapshot as indented UTF-8 JSON (trailing newline)."""
    return snapshot.model_dump_json(indent=2) + "\n"
