"""RSS 2.0 change-feed serializer: the watchdog's public output.

When a :class:`~rtk_funding_watch.models.Diff` is supplied, each change becomes
a feed item (new call, status change, edit, removal). With no diff, the feed
falls back to listing the currently open calls.
"""

from __future__ import annotations

from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from rtk_funding_watch.models import ChangeEvent, ChangeType, Diff, Snapshot, Status

_CHANNEL_TITLE = "RTK funding-call watchdog"
_CHANNEL_DESC = (
    "Changes to funding calls published by Riigi Tugiteenuste Keskus (rtk.ee), "
    "detected and published."
)

_EVENT_PREFIX = {
    ChangeType.ADDED: "New call",
    ChangeType.REMOVED: "Call removed",
    ChangeType.MODIFIED: "Call updated",
    ChangeType.STATUS_CHANGED: "Status changed",
}


def _event_description(event: ChangeEvent) -> str:
    if event.type is ChangeType.STATUS_CHANGED:
        old = event.old_status.value if event.old_status else "?"
        new = event.new_status.value if event.new_status else "?"
        return f"Status changed from {old} to {new}."
    if event.type is ChangeType.MODIFIED and event.changes:
        return "Updated: " + ", ".join(c.field for c in event.changes) + "."
    if event.type is ChangeType.ADDED:
        return "A new funding call was published."
    if event.type is ChangeType.REMOVED:
        return "The funding call was removed from the listing."
    return "The funding call changed."


def _add_item(
    channel: Element, *, title: str, link: str, desc: str, guid: str, pub: str
) -> None:
    item = SubElement(channel, "item")
    SubElement(item, "title").text = title
    if link:
        SubElement(item, "link").text = link
    SubElement(item, "description").text = desc
    guid_el = SubElement(item, "guid", {"isPermaLink": "false"})
    guid_el.text = guid
    SubElement(item, "pubDate").text = pub


def dumps(snapshot: Snapshot, *, diff: Diff | None = None) -> str:
    """Render an RSS 2.0 feed of changes (or of open calls if no diff)."""
    rss = Element("rss", {"version": "2.0"})
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = _CHANNEL_TITLE
    SubElement(channel, "link").text = snapshot.source_url
    SubElement(channel, "description").text = _CHANNEL_DESC
    SubElement(channel, "generator").text = snapshot.generator
    build_date = format_datetime(snapshot.scraped_at)
    SubElement(channel, "lastBuildDate").text = build_date

    if diff is not None and not diff.is_empty():
        pub = format_datetime(diff.to_scraped_at)
        for event in diff.events:
            prefix = _EVENT_PREFIX[event.type]
            _add_item(
                channel,
                title=f"{prefix}: {event.name}",
                link=event.detail_url,
                desc=_event_description(event),
                guid=f"{event.call_id}:{diff.to_scraped_at.isoformat()}:{event.type.value}",
                pub=pub,
            )
    else:
        pub = format_datetime(snapshot.scraped_at)
        for call in snapshot.calls:
            if call.status is not Status.OPEN:
                continue
            desc = call.purpose or call.application_period or "Open funding call."
            _add_item(
                channel,
                title=call.name,
                link=call.detail_url,
                desc=desc,
                guid=f"{call.id}:{call.content_hash()}",
                pub=pub,
            )

    xml = tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"
