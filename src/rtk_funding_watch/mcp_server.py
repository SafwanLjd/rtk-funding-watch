"""MCP server exposing RTK funding calls as tools and resources.

Built on the official ``mcp`` SDK (v2 line), whose high-level server class is
``MCPServer``: note ``mcp.server.fastmcp.FastMCP`` was removed in mcp 2.x.
The server serves a single :class:`~rtk_funding_watch.models.Snapshot`,
resolved (in precedence order) from an explicit path, the ``RTK_SNAPSHOT``
environment variable, or ``data/snapshots/latest.json`` relative to the current
working directory. Loading is lazy and cached so importing this module never
fails when no snapshot exists yet; tools degrade to a clear error string.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from rtk_funding_watch import storage
from rtk_funding_watch.models import Snapshot

__all__ = ["main", "mcp"]

# A JSON-serializable funding-call dict, as produced by ``model_dump(mode="json")``.
JsonDict = dict[str, Any]

_ENV_VAR = "RTK_SNAPSHOT"
_DEFAULT_SNAPSHOT = Path("data/snapshots/latest.json")
_NO_DATA_MSG = (
    "No snapshot available. Set the RTK_SNAPSHOT environment variable or run "
    "'rtk-watch scrape' to create data/snapshots/latest.json."
)

mcp = MCPServer("rtk-funding-watch")


class _State:
    """Mutable holder for the lazily loaded, cached snapshot and its source."""

    path: Path | None = None
    snapshot: Snapshot | None = None
    loaded: bool = False


_state = _State()


def _resolve_path(snapshot_path: Path | None = None) -> Path:
    """Resolve which snapshot file to serve, honoring the documented precedence."""
    if snapshot_path is not None:
        return Path(snapshot_path)
    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        return Path(env_value)
    return _DEFAULT_SNAPSHOT


def _get_snapshot() -> Snapshot | None:
    """Return the served snapshot, loading and caching it on first use.

    Returns ``None`` (never raises) when the resolved file is missing or
    unreadable, so tools can surface a friendly message instead of crashing.
    """
    if _state.loaded:
        return _state.snapshot
    path = _resolve_path(_state.path)
    try:
        _state.snapshot = storage.load_snapshot(path)
    except (OSError, ValueError):
        _state.snapshot = None
    _state.loaded = True
    return _state.snapshot


@mcp.tool()
def list_funding_calls(status: str | None = None) -> list[JsonDict]:
    """List all RTK funding calls, optionally filtered by status.

    Pass ``status`` as one of ``open``, ``upcoming`` or ``closed`` to filter;
    omit it to return every call. Returns an empty list when no data is loaded.
    """
    snapshot = _get_snapshot()
    if snapshot is None:
        return []
    calls = snapshot.calls
    if status is not None:
        wanted = status.lower()
        calls = [call for call in calls if call.status.value == wanted]
    return [call.model_dump(mode="json") for call in calls]


@mcp.tool()
def get_funding_call(call_id: str) -> JsonDict | str:
    """Return one funding call by its id, or a not-found message.

    ``call_id`` is the stable slug used throughout the dataset.
    """
    snapshot = _get_snapshot()
    if snapshot is None:
        return _NO_DATA_MSG
    call = snapshot.by_id().get(call_id)
    if call is None:
        return f"No funding call found with id {call_id!r}."
    return call.model_dump(mode="json")


@mcp.tool()
def search_funding_calls(query: str, status: str | None = None) -> list[JsonDict]:
    """Search funding calls by a case-insensitive substring match.

    Matches ``query`` against each call's name, purpose, target group and
    field domain. Optionally restrict results to a ``status`` value (``open``,
    ``upcoming`` or ``closed``).
    """
    snapshot = _get_snapshot()
    if snapshot is None:
        return []
    needle = query.lower()
    wanted = status.lower() if status is not None else None
    results: list[JsonDict] = []
    for call in snapshot.calls:
        if wanted is not None and call.status.value != wanted:
            continue
        haystack = " ".join(
            (call.name, call.purpose, call.target_group, call.field_domain)
        ).lower()
        if needle in haystack:
            results.append(call.model_dump(mode="json"))
    return results


@mcp.resource("rtk://calls", mime_type="application/json")
def all_calls_resource() -> str:
    """Every known RTK funding call, as a JSON array."""
    snapshot = _get_snapshot()
    calls = snapshot.calls if snapshot is not None else []
    payload = [call.model_dump(mode="json") for call in calls]
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.resource("rtk://calls/{call_id}", mime_type="application/json")
def call_resource(call_id: str) -> str:
    """A single RTK funding call addressed by its id, as a JSON object."""
    snapshot = _get_snapshot()
    call = snapshot.by_id().get(call_id) if snapshot is not None else None
    if call is None:
        return json.dumps({"error": f"no funding call with id {call_id!r}"})
    return json.dumps(call.model_dump(mode="json"), ensure_ascii=False, indent=2)


def main(snapshot_path: Path | None = None) -> None:
    """Resolve and preload the snapshot, then run the MCP stdio server.

    Preloading makes a bad explicit path fail loudly at startup rather than on
    the first tool call. ``snapshot_path`` takes precedence over the
    ``RTK_SNAPSHOT`` environment variable and the default location.
    """
    _state.path = snapshot_path
    _state.snapshot = None
    _state.loaded = False
    if snapshot_path is not None:
        # An explicit path must exist and parse; surface failures immediately.
        _state.snapshot = storage.load_snapshot(_resolve_path(snapshot_path))
        _state.loaded = True
    else:
        _get_snapshot()
    mcp.run()


if __name__ == "__main__":
    main()
