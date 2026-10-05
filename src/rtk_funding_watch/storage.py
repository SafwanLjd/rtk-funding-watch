"""Persist and load :class:`Snapshot` objects as timestamped JSON files.

Writes are atomic (temp file + ``os.replace``) so an interrupted run cannot
leave a torn ``latest.json`` behind, and the latest/previous readers skip any
file that fails to parse rather than crashing the whole command.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

from rtk_funding_watch.models import Snapshot

logger = logging.getLogger(__name__)

__all__ = [
    "latest_snapshot",
    "list_snapshots",
    "load_snapshot",
    "previous_snapshot",
    "prune_snapshots",
    "save_snapshot",
    "snapshot_filename",
]


def snapshot_filename(snapshot: Snapshot) -> str:
    """Return a sortable UTC filename like ``snapshot-20261005T120000Z.json``."""
    ts = snapshot.scraped_at.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"snapshot-{ts}.json"


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file in the same dir + replace)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_snapshot(snapshot: Snapshot, directory: Path | str, *, keep: int = 0) -> Path:
    """Write ``snapshot`` atomically and refresh ``latest.json``.

    ``keep`` > 0 prunes all but the newest ``keep`` timestamped snapshots.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump_json(indent=2) + "\n"
    path = directory / snapshot_filename(snapshot)
    _atomic_write(path, payload)
    _atomic_write(directory / "latest.json", payload)
    if keep > 0:
        prune_snapshots(directory, keep)
    return path


def load_snapshot(path: Path | str) -> Snapshot:
    """Load a snapshot from a JSON file."""
    return Snapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))


def list_snapshots(directory: Path | str) -> list[Path]:
    """Return timestamped snapshot files, oldest first."""
    return sorted(Path(directory).glob("snapshot-*.json"))


def prune_snapshots(directory: Path | str, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` timestamped snapshots; return removed."""
    if keep <= 0:
        return []
    files = list_snapshots(directory)
    removed: list[Path] = []
    for old in files[:-keep]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return removed


def _load_valid_newest_first(directory: Path | str) -> Iterator[Snapshot]:
    """Yield loadable snapshots newest-first, skipping any that fail to parse."""
    for path in reversed(list_snapshots(directory)):
        try:
            yield load_snapshot(path)
        except (OSError, ValueError) as exc:
            logger.warning("skipping unreadable snapshot %s: %s", path, exc)


def latest_snapshot(directory: Path | str) -> Snapshot | None:
    """Load the most recent valid snapshot, or ``None`` if there are none."""
    return next(_load_valid_newest_first(directory), None)


def previous_snapshot(directory: Path | str) -> Snapshot | None:
    """Load the second-most-recent valid snapshot, or ``None``."""
    gen = _load_valid_newest_first(directory)
    next(gen, None)
    return next(gen, None)
