"""Persist and load :class:`Snapshot` objects as timestamped JSON files."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from rtk_funding_watch.models import Snapshot

__all__ = [
    "latest_snapshot",
    "list_snapshots",
    "load_snapshot",
    "previous_snapshot",
    "save_snapshot",
    "snapshot_filename",
]


def snapshot_filename(snapshot: Snapshot) -> str:
    """Return a sortable UTC filename like ``snapshot-20261005T120000Z.json``."""
    ts = snapshot.scraped_at.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"snapshot-{ts}.json"


def save_snapshot(snapshot: Snapshot, directory: Path | str) -> Path:
    """Write ``snapshot`` into ``directory`` and refresh the ``latest.json`` copy."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump_json(indent=2) + "\n"
    path = directory / snapshot_filename(snapshot)
    path.write_text(payload, encoding="utf-8")
    (directory / "latest.json").write_text(payload, encoding="utf-8")
    return path


def load_snapshot(path: Path | str) -> Snapshot:
    """Load a snapshot from a JSON file."""
    return Snapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))


def list_snapshots(directory: Path | str) -> list[Path]:
    """Return timestamped snapshot files, oldest first."""
    return sorted(Path(directory).glob("snapshot-*.json"))


def latest_snapshot(directory: Path | str) -> Snapshot | None:
    """Load the most recent snapshot, or ``None`` if there are none."""
    files = list_snapshots(directory)
    return load_snapshot(files[-1]) if files else None


def previous_snapshot(directory: Path | str) -> Snapshot | None:
    """Load the second-most-recent snapshot, or ``None``."""
    files = list_snapshots(directory)
    return load_snapshot(files[-2]) if len(files) >= 2 else None
