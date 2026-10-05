"""Tests for the data model."""

from __future__ import annotations

import datetime as dt

from rtk_funding_watch.models import Snapshot, Status
from tests.factories import make_call


def test_status_values() -> None:
    assert [s.value for s in Status] == ["open", "upcoming", "closed"]


def test_content_hash_is_stable_and_order_independent() -> None:
    a = make_call(document_links=["https://a", "https://b"])
    b = make_call(document_links=["https://b", "https://a"])
    assert a.content_hash() == b.content_hash()


def test_content_hash_changes_with_meaningful_field() -> None:
    a = make_call(purpose="x")
    b = make_call(purpose="y")
    assert a.content_hash() != b.content_hash()


def test_snapshot_counts(sample_snapshot: Snapshot) -> None:
    counts = sample_snapshot.counts()
    assert counts == {"open": 1, "upcoming": 0, "closed": 1, "total": 2}


def test_snapshot_by_id(sample_snapshot: Snapshot) -> None:
    assert set(sample_snapshot.by_id()) == {"alpha", "beta"}


def test_content_hash_ignores_link_lists() -> None:
    a = make_call(
        document_links=["https://pilv.rtk.ee/s/a"], regulation_urls=[], image_urls=[]
    )
    b = make_call(
        document_links=["https://pilv.rtk.ee/s/a", "https://pilv.rtk.ee/s/b"],
        regulation_urls=["https://riigiteataja.ee/akt/1"],
        image_urls=["https://rtk.ee/x.png"],
    )
    assert a.content_hash() == b.content_hash()


def test_content_hash_tracks_status_and_period() -> None:
    a = make_call(status=Status.OPEN, application_period="alates 01.01.2026")
    b = make_call(status=Status.CLOSED, application_period="alates 01.01.2026")
    assert a.content_hash() != b.content_hash()


def test_snapshot_scraped_at_normalized_to_utc() -> None:
    naive = Snapshot(
        source_url="u", scraped_at=dt.datetime(2026, 1, 1, 12, 0), calls=[]
    )
    assert naive.scraped_at.tzinfo is not None
    assert naive.scraped_at.utcoffset() == dt.timedelta(0)
