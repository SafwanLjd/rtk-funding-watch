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


def test_latest_skips_corrupt_snapshot(tmp_path: Path) -> None:
    storage.save_snapshot(_snap(1), tmp_path)
    storage.save_snapshot(_snap(2), tmp_path)
    newest = storage.list_snapshots(tmp_path)[-1]
    newest.write_text("{ not json", encoding="utf-8")
    latest = storage.latest_snapshot(tmp_path)
    assert latest is not None and latest.scraped_at.day == 1


def test_prune_keeps_newest_n(tmp_path: Path) -> None:
    for day in (1, 2, 3, 4):
        storage.save_snapshot(_snap(day), tmp_path)
    removed = storage.prune_snapshots(tmp_path, keep=2)
    assert len(removed) == 2
    remaining = storage.list_snapshots(tmp_path)
    assert len(remaining) == 2
    assert storage.load_snapshot(remaining[-1]).scraped_at.day == 4


def test_save_is_atomic_no_tmp_left(tmp_path: Path) -> None:
    storage.save_snapshot(_snap(1), tmp_path)
    assert not list(tmp_path.glob(".tmp-*"))
    assert (tmp_path / "latest.json").exists()
