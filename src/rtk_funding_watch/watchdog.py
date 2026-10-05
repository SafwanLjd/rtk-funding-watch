"""Diff two snapshots into a :class:`Diff` of change events: the watchdog core."""

from __future__ import annotations

from rtk_funding_watch.models import (
    ChangeEvent,
    ChangeType,
    Diff,
    FieldChange,
    FundingCall,
    Snapshot,
)

# Human-readable text fields compared verbatim for MODIFIED events.
_TEXT_FIELDS = (
    "name",
    "application_period",
    "target_group",
    "purpose",
    "field_domain",
    "funding_source",
)
_LIST_FIELDS = ("regulation_urls", "document_links", "image_urls")

_EVENT_ORDER = {
    ChangeType.ADDED: 0,
    ChangeType.STATUS_CHANGED: 1,
    ChangeType.MODIFIED: 2,
    ChangeType.REMOVED: 3,
}


def _field_changes(old: FundingCall, new: FundingCall) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for field in _TEXT_FIELDS:
        old_val, new_val = getattr(old, field), getattr(new, field)
        if isinstance(old_val, str) and old_val != new_val:
            changes.append(FieldChange(field=field, old=old_val, new=new_val))
    for field in _LIST_FIELDS:
        old_set, new_set = set(getattr(old, field)), set(getattr(new, field))
        if old_set != new_set:
            changes.append(
                FieldChange(
                    field=field,
                    old=f"{len(old_set)} links",
                    new=f"{len(new_set)} links",
                )
            )
    return changes


def diff_snapshots(old: Snapshot | None, new: Snapshot) -> Diff:
    """Compute the changes from ``old`` to ``new`` (``old`` may be ``None``)."""
    old_by = old.by_id() if old else {}
    new_by = new.by_id()
    events: list[ChangeEvent] = []

    for call_id, call in new_by.items():
        if call_id not in old_by:
            events.append(
                ChangeEvent(
                    type=ChangeType.ADDED,
                    call_id=call_id,
                    name=call.name,
                    detail_url=call.detail_url,
                    new_status=call.status,
                )
            )
            continue
        old_call = old_by[call_id]
        if old_call.status is not call.status:
            events.append(
                ChangeEvent(
                    type=ChangeType.STATUS_CHANGED,
                    call_id=call_id,
                    name=call.name,
                    detail_url=call.detail_url,
                    old_status=old_call.status,
                    new_status=call.status,
                    changes=_field_changes(old_call, call),
                )
            )
        elif old_call.content_hash() != call.content_hash():
            events.append(
                ChangeEvent(
                    type=ChangeType.MODIFIED,
                    call_id=call_id,
                    name=call.name,
                    detail_url=call.detail_url,
                    changes=_field_changes(old_call, call),
                )
            )

    for call_id, call in old_by.items():
        if call_id not in new_by:
            events.append(
                ChangeEvent(
                    type=ChangeType.REMOVED,
                    call_id=call_id,
                    name=call.name,
                    detail_url=call.detail_url,
                    old_status=call.status,
                )
            )

    events.sort(key=lambda e: (_EVENT_ORDER[e.type], e.name.lower()))
    return Diff(
        from_scraped_at=old.scraped_at if old else None,
        to_scraped_at=new.scraped_at,
        events=events,
    )
