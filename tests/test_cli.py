"""Tests for the CLI (commands that do not require network)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from rtk_funding_watch import storage
from rtk_funding_watch.cli import app
from rtk_funding_watch.models import Snapshot
from rtk_funding_watch.scraper import DEFAULT_LISTING_URL
from tests.factories import make_call

runner = CliRunner()


def _seed(data_dir: Path) -> None:
    storage.save_snapshot(
        Snapshot(
            source_url="https://rtk.ee/listing",
            scraped_at=dt.datetime(2026, 10, 5, tzinfo=dt.UTC),
            calls=[make_call("alpha"), make_call("beta")],
        ),
        data_dir,
    )


def test_diff_without_snapshots_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["diff", "--data-dir", str(tmp_path / "none")])
    assert result.exit_code == 1


def test_export_writes_all_formats(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    _seed(data_dir)
    result = runner.invoke(
        app, ["export", "--out", str(out_dir), "--data-dir", str(data_dir)]
    )
    assert result.exit_code == 0, result.output
    for name in ("calls.json", "calls.toon", "calls.csv", "feed.xml"):
        assert (out_dir / "api" / name).exists()


def test_build_site_renders_index(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    _seed(data_dir)
    result = runner.invoke(
        app, ["build-site", "--out", str(out_dir), "--data-dir", str(data_dir)]
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "index.html").exists()
    assert (out_dir / "static" / "styles.css").exists()


def test_scrape_refuses_empty_listing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    empty_html = "<html><body><p>no calls here</p></body></html>"
    with respx.mock(assert_all_called=False) as router:
        router.get(DEFAULT_LISTING_URL).mock(
            return_value=httpx.Response(200, text=empty_html)
        )
        result = runner.invoke(app, ["scrape", "--data-dir", str(data_dir)])
    assert result.exit_code == 2
    assert not data_dir.exists() or not list(data_dir.glob("snapshot-*.json"))
