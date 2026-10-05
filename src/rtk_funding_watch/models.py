"""Normalized data model for RTK funding calls.

These Pydantic models are the single contract shared by the scraper, the
watchdog differ, every serializer, the static-site generator and the MCP
server. Keep them free of I/O and parsing logic so they stay cheap to import
and trivial to validate.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ChangeEvent",
    "ChangeType",
    "Diff",
    "FieldChange",
    "FundingCall",
    "Snapshot",
    "Status",
]


class Status(StrEnum):
    """Lifecycle state of an application round, normalized across the site."""

    OPEN = "open"
    UPCOMING = "upcoming"
    CLOSED = "closed"


# Fields that define a call's *semantic* identity. The content hash is taken
# over exactly these, so volatile scrape metadata never triggers a false diff.
_HASHED_FIELDS = (
    "name",
    "status",
    "application_period",
    "target_group",
    "purpose",
    "field_domain",
    "funding_source",
)


class FundingCall(BaseModel):
    """A single funding measure / application round published by RTK."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable slug derived from the detail URL path.")
    name: str = Field(description="Measure name as published.")
    status: Status

    application_period: str = Field(
        default="", description="Raw Estonian application-period text, verbatim."
    )
    application_start: dt.date | None = Field(
        default=None, description="Parsed application start date, if determinable."
    )
    application_end: dt.date | None = Field(
        default=None, description="Parsed application end date, if determinable."
    )
    deadline_note: str = Field(
        default="",
        description="Extra deadline qualifier, e.g. 'until budget is exhausted'.",
    )

    target_group: str = ""
    purpose: str = ""
    field_domain: str = ""
    funding_source: str = Field(
        default="",
        description="Funding instrument tag when known: SF, RRF, EMP/Norra, RE.",
    )

    detail_url: str
    source_host: str = Field(
        default="", description="Host the detail page lives on (e.g. rtk.ee)."
    )

    regulation_urls: list[str] = Field(
        default_factory=list,
        description="Riigi Teataja legal-act URLs governing the measure.",
    )
    document_links: list[str] = Field(
        default_factory=list,
        description="Measure-specific document URLs (forms, guides, annexes).",
    )
    image_urls: list[str] = Field(
        default_factory=list, description="Measure-specific content image URLs."
    )

    def content_hash(self) -> str:
        """Deterministic 16-hex-char digest over the call's identity fields.

        Only the stable, human-meaningful fields in ``_HASHED_FIELDS`` are
        hashed. The regulation/document/image URL lists are deliberately
        excluded: they churn with transient detail-page fetch failures and
        with the snapshot-relative boilerplate threshold, which would
        otherwise surface as spurious "modified" events in the watchdog.
        """
        parts: list[str] = []
        for name in _HASHED_FIELDS:
            value = getattr(self, name)
            parts.append(value.value if isinstance(value, Status) else str(value))
        blob = "\u001e".join(parts).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


class Snapshot(BaseModel):
    """A full scrape of the funding-call listing at a point in time."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    scraped_at: dt.datetime
    generator: str = "rtk-funding-watch"

    @field_validator("scraped_at")
    @classmethod
    def _as_utc(cls, value: dt.datetime) -> dt.datetime:
        """Normalize to timezone-aware UTC so filenames and feeds are stable."""
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)

    calls: list[FundingCall] = Field(default_factory=list)
    common_resources: list[str] = Field(
        default_factory=list,
        description="Site-wide helper documents dropped from individual calls.",
    )

    def by_id(self) -> dict[str, FundingCall]:
        """Index the calls by their stable id (last duplicate wins)."""
        return {call.id: call for call in self.calls}

    def counts(self) -> dict[str, int]:
        """Count calls per :class:`Status` value, plus a ``total``."""
        tally: dict[str, int] = {status.value: 0 for status in Status}
        for call in self.calls:
            tally[call.status.value] += 1
        tally["total"] = len(self.calls)
        return tally


class ChangeType(StrEnum):
    """Kind of change the watchdog detected between two snapshots."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    STATUS_CHANGED = "status_changed"


class FieldChange(BaseModel):
    """A single old -> new field transition inside a modified call."""

    model_config = ConfigDict(extra="forbid")

    field: str
    old: str | None = None
    new: str | None = None


class ChangeEvent(BaseModel):
    """One change to one funding call."""

    model_config = ConfigDict(extra="forbid")

    type: ChangeType
    call_id: str
    name: str
    detail_url: str = ""
    old_status: Status | None = None
    new_status: Status | None = None
    changes: list[FieldChange] = Field(default_factory=list)


class Diff(BaseModel):
    """The ordered set of changes between an older and a newer snapshot."""

    model_config = ConfigDict(extra="forbid")

    from_scraped_at: dt.datetime | None
    to_scraped_at: dt.datetime
    events: list[ChangeEvent] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.events
