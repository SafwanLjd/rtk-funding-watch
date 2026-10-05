"""Tests for the watchdog differ."""

from __future__ import annotations

import datetime as dt

from rtk_funding_watch.models import ChangeType, FundingCall, Snapshot, Status
from rtk_funding_watch.watchdog import diff_snapshots
from tests.factories import make_call


def _snap(calls: list[FundingCall], when: int = 1) -> Snapshot:
    return Snapshot(
        source_url="u",
        scraped_at=dt.datetime(2026, 10, when, tzinfo=dt.UTC),
        calls=calls,
    )


def test_diff_none_old_marks_everything_added() -> None:
    new = _snap([make_call("a"), make_call("b")])
    diff = diff_snapshots(None, new)
    assert {e.type for e in diff.events} == {ChangeType.ADDED}
    assert diff.from_scraped_at is None


def test_diff_detects_added_and_removed() -> None:
    old = _snap([make_call("a")], when=1)
    new = _snap([make_call("b")], when=2)
    diff = diff_snapshots(old, new)
    kinds = {(e.type, e.call_id) for e in diff.events}
    assert (ChangeType.ADDED, "b") in kinds
    assert (ChangeType.REMOVED, "a") in kinds


def test_diff_detects_status_change() -> None:
    old = _snap([make_call("a", Status.OPEN)], when=1)
    new = _snap([make_call("a", Status.CLOSED)], when=2)
    diff = diff_snapshots(old, new)
    event = next(e for e in diff.events if e.call_id == "a")
    assert event.type is ChangeType.STATUS_CHANGED
    assert event.old_status is Status.OPEN
    assert event.new_status is Status.CLOSED


def test_diff_detects_modification() -> None:
    old = _snap([make_call("a", purpose="old")], when=1)
    new = _snap([make_call("a", purpose="new")], when=2)
    diff = diff_snapshots(old, new)
    event = next(e for e in diff.events if e.call_id == "a")
    assert event.type is ChangeType.MODIFIED
    assert any(c.field == "purpose" for c in event.changes)


def test_diff_empty_when_identical() -> None:
    old = _snap([make_call("a")], when=1)
    new = _snap([make_call("a")], when=2)
    assert diff_snapshots(old, new).is_empty()
