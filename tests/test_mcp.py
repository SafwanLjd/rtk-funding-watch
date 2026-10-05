"""Tests for the MCP server's tools and resources (logic, not the stdio loop)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from rtk_funding_watch import mcp_server as m
from rtk_funding_watch import storage
from rtk_funding_watch.models import Snapshot


@pytest.fixture
def served(tmp_path: Path, sample_snapshot: Snapshot) -> Iterator[None]:
    path = storage.save_snapshot(sample_snapshot, tmp_path)
    m._state.loaded = False
    m._state.path = path
    m._state.snapshot = None
    yield
    m._state.loaded = False
    m._state.path = None
    m._state.snapshot = None


@pytest.mark.usefixtures("served")
def test_list_all_and_filtered() -> None:
    assert len(m.list_funding_calls()) == 2
    open_calls = m.list_funding_calls(status="open")
    assert [c["id"] for c in open_calls] == ["alpha"]


@pytest.mark.usefixtures("served")
def test_get_and_missing() -> None:
    got = m.get_funding_call("alpha")
    assert isinstance(got, dict) and got["id"] == "alpha"
    assert isinstance(m.get_funding_call("nope"), str)


@pytest.mark.usefixtures("served")
def test_search_is_case_insensitive() -> None:
    hits = m.search_funding_calls("ALPHA")
    assert any(h["id"] == "alpha" for h in hits)


@pytest.mark.usefixtures("served")
def test_resources_return_json() -> None:
    all_calls = json.loads(m.all_calls_resource())
    assert {c["id"] for c in all_calls} == {"alpha", "beta"}
    one = json.loads(m.call_resource("alpha"))
    assert one["id"] == "alpha"
    missing = json.loads(m.call_resource("nope"))
    assert "error" in missing


def test_no_data_is_graceful(tmp_path: Path) -> None:
    m._state.loaded = False
    m._state.path = tmp_path / "missing.json"
    m._state.snapshot = None
    try:
        assert m.list_funding_calls() == []
        assert isinstance(m.get_funding_call("x"), str)
    finally:
        m._state.loaded = False
        m._state.path = None
