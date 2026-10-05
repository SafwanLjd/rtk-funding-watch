"""Tests for snapshot persistence."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from rtk_funding_watch import storage
from rtk_funding_watch.models import Snapshot
from tests.factories import make_call


def _snap(day: int) -> Snapshot:
    return Snapshot(
        source_url="u",
        scraped_at=dt.datetime(2026, 10, day, 12, 0, tzinfo=dt.UTC),
        calls=[make_call("a")],
    )


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    snap = _snap(1)
    path = storage.save_snapshot(snap, tmp_path)
    assert path.exists()
    assert (tmp_path / "latest.json").exists()
    loaded = storage.load_snapshot(path)
    assert loaded.calls[0].id == "a"
    assert loaded.scraped_at == snap.scraped_at


def test_latest_and_previous(tmp_path: Path) -> None:
    storage.save_snapshot(_snap(1), tmp_path)
    storage.save_snapshot(_snap(2), tmp_path)
    storage.save_snapshot(_snap(3), tmp_path)
    assert len(storage.list_snapshots(tmp_path)) == 3
    latest = storage.latest_snapshot(tmp_path)
    previous = storage.previous_snapshot(tmp_path)
    assert latest is not None and latest.scraped_at.day == 3
    assert previous is not None and previous.scraped_at.day == 2


def test_latest_none_when_empty(tmp_path: Path) -> None:
    assert storage.latest_snapshot(tmp_path) is None
    assert storage.previous_snapshot(tmp_path) is None
