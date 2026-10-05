"""Tests for serializers."""

from __future__ import annotations

import datetime as dt
import json
from xml.dom import minidom

import toon_format

from rtk_funding_watch import serialize
from rtk_funding_watch.models import Snapshot, Status
from rtk_funding_watch.watchdog import diff_snapshots
from tests.factories import make_call


def test_formats_registered() -> None:
    assert set(serialize.FORMATS) == {"json", "toon", "csv", "rss"}


def test_json_roundtrips(sample_snapshot: Snapshot) -> None:
    text = serialize.serialize(sample_snapshot, "json")
    data = json.loads(text)
    assert data["calls"][0]["id"] == "alpha"
    assert data["calls"][0]["status"] == "open"


def test_toon_is_tabular_and_decodes(sample_snapshot: Snapshot) -> None:
    text = serialize.serialize(sample_snapshot, "toon")
    assert "calls[2]{" in text  # tabular header with length marker
    decoded = toon_format.loads(text)
    assert decoded["counts"]["total"] == 2
    assert decoded["calls"][0]["document_links"] == "https://pilv.rtk.ee/s/x"


def test_csv_has_header_and_rows(sample_snapshot: Snapshot) -> None:
    text = serialize.serialize(sample_snapshot, "csv")
    lines = text.strip().splitlines()
    assert lines[0].startswith("id,status,name,")
    assert len(lines) == 3  # header + 2 calls


def test_rss_wellformed_lists_open_calls(sample_snapshot: Snapshot) -> None:
    text = serialize.serialize(sample_snapshot, "rss")
    doc = minidom.parseString(text)
    items = doc.getElementsByTagName("item")
    assert len(items) == 1  # only the single open call, no diff supplied


def test_unknown_format_raises(sample_snapshot: Snapshot) -> None:
    try:
        serialize.serialize(sample_snapshot, "yaml")
    except ValueError as exc:
        assert "unknown format" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_rss_lists_change_events_when_diff_given(sample_snapshot: Snapshot) -> None:
    newer = Snapshot(
        source_url=sample_snapshot.source_url,
        scraped_at=dt.datetime(2026, 10, 7, tzinfo=dt.UTC),
        calls=[make_call("alpha", Status.CLOSED), make_call("gamma", Status.OPEN)],
    )
    diff = diff_snapshots(sample_snapshot, newer)
    text = serialize.serialize(newer, "rss", diff=diff)
    items = minidom.parseString(text).getElementsByTagName("item")
    # alpha status change, gamma added, beta removed -> 3 events
    assert len(items) == len(diff.events) == 3
