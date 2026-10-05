"""rtk-funding-watch: watchdog for RTK (rtk.ee) funding calls.

Scrapes the public funding-call listing and republishes it as JSON, TOON, CSV
and an RSS change feed, plus an MCP server and a static website.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rtk-funding-watch")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
