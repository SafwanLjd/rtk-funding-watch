"""TOON serializer: delegates to the official ``toon-format`` encoder.

TOON (Token-Oriented Object Notation) renders a uniform array of objects as a
compact tabular block, which is markedly cheaper to feed to an LLM than JSON.
To keep the ``calls`` array *tabular* (every column primitive), the three
URL-list fields are flattened to ';'-joined strings here; the JSON output keeps
them as real arrays for lossless consumption.
"""

from __future__ import annotations

from typing import Any

import toon_format

from rtk_funding_watch.models import Diff, FundingCall, Snapshot

_LIST_FIELDS = ("regulation_urls", "document_links", "image_urls")


def _flatten(call: FundingCall) -> dict[str, Any]:
    row = call.model_dump(mode="json")
    for field in _LIST_FIELDS:
        row[field] = ";".join(row[field])
    return row


def dumps(snapshot: Snapshot, *, diff: Diff | None = None) -> str:
    """Return the snapshot encoded as TOON (spec v4.1), calls as a table."""
    data: dict[str, Any] = {
        "source_url": snapshot.source_url,
        "scraped_at": snapshot.scraped_at.isoformat(),
        "generator": snapshot.generator,
        "counts": snapshot.counts(),
        "calls": [_flatten(call) for call in snapshot.calls],
        "common_resources": snapshot.common_resources,
    }
    return toon_format.dumps(data) + "\n"
