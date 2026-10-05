"""Serializers that render a :class:`~rtk_funding_watch.models.Snapshot` into
each published machine-readable format.

Every format module exposes ``dumps(snapshot, *, diff=None) -> str``. Use the
:func:`serialize` dispatcher, or :data:`FORMATS` to enumerate them.
"""

from __future__ import annotations

from rtk_funding_watch.models import Diff, Snapshot

from . import csv_fmt, json_fmt, rss_fmt, toon_fmt

__all__ = ["FORMATS", "content_type", "file_name", "serialize"]

_DUMPERS = {
    "json": json_fmt.dumps,
    "toon": toon_fmt.dumps,
    "csv": csv_fmt.dumps,
    "rss": rss_fmt.dumps,
}

_CONTENT_TYPES = {
    "json": "application/json; charset=utf-8",
    "toon": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "rss": "application/rss+xml; charset=utf-8",
}

_FILE_NAMES = {
    "json": "calls.json",
    "toon": "calls.toon",
    "csv": "calls.csv",
    "rss": "feed.xml",
}

FORMATS = tuple(_DUMPERS)


def serialize(snapshot: Snapshot, fmt: str, *, diff: Diff | None = None) -> str:
    """Render ``snapshot`` in ``fmt`` (one of :data:`FORMATS`)."""
    try:
        dumper = _DUMPERS[fmt]
    except KeyError:
        raise ValueError(
            f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}"
        ) from None
    return dumper(snapshot, diff=diff)


def content_type(fmt: str) -> str:
    """HTTP ``Content-Type`` for a format."""
    return _CONTENT_TYPES[fmt]


def file_name(fmt: str) -> str:
    """Conventional output file name for a format."""
    return _FILE_NAMES[fmt]
