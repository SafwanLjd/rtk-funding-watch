"""Tests for the static-site generator."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from rtk_funding_watch import site
from rtk_funding_watch.models import Snapshot, Status
from rtk_funding_watch.watchdog import diff_snapshots
from tests.factories import make_call


def test_render_index_lists_calls_and_links(sample_snapshot: Snapshot) -> None:
    html = site.render_index(sample_snapshot, None)
    assert "Call alpha" in html
    assert "api/calls.json" in html
    assert "api/calls.toon" in html
    assert "api/feed.xml" in html
    assert "rtk-funding-mcp" in html


def test_render_index_escapes_html() -> None:
    snap = Snapshot(
        source_url="u",
        scraped_at=dt.datetime(2026, 10, 5, tzinfo=dt.UTC),
        calls=[make_call("x", purpose="<script>alert(1)</script>")],
    )
    html = site.render_index(snap, None)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_recent_changes_only_with_diff(sample_snapshot: Snapshot) -> None:
    without = site.render_index(sample_snapshot, None)
    assert "Recent changes" not in without

    newer = Snapshot(
        source_url=sample_snapshot.source_url,
        scraped_at=dt.datetime(2026, 10, 6, tzinfo=dt.UTC),
        calls=[make_call("alpha", Status.CLOSED), make_call("beta", Status.CLOSED)],
    )
    diff = diff_snapshots(sample_snapshot, newer)
    assert not diff.is_empty()
    with_changes = site.render_index(newer, diff)
    assert "Recent changes" in with_changes


def test_build_site_writes_files(tmp_path: Path, sample_snapshot: Snapshot) -> None:
    paths = site.build_site(sample_snapshot, None, tmp_path)
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "static" / "styles.css").exists()
    assert (tmp_path / "static" / "app.js").exists()
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
