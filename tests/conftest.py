"""Shared pytest fixtures."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from rtk_funding_watch.models import Snapshot, Status
from tests.factories import make_call

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def listing_html() -> str:
    return (FIXTURES / "listing.html").read_text(encoding="utf-8")


@pytest.fixture
def detail_html() -> str:
    return (FIXTURES / "detail.html").read_text(encoding="utf-8")


@pytest.fixture
def sample_snapshot() -> Snapshot:
    return Snapshot(
        source_url="https://rtk.ee/listing",
        scraped_at=dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC),
        calls=[
            make_call(
                "alpha",
                Status.OPEN,
                purpose="Help alpha",
                regulation_urls=["https://riigiteataja.ee/akt/1"],
                document_links=["https://pilv.rtk.ee/s/x"],
            ),
            make_call("beta", Status.CLOSED),
        ],
    )
