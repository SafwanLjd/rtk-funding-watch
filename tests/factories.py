"""Test data builders."""

from __future__ import annotations

from rtk_funding_watch.models import FundingCall, Status


def make_call(
    call_id: str = "alpha", status: Status = Status.OPEN, **kw: object
) -> FundingCall:
    data: dict[str, object] = {
        "id": call_id,
        "name": f"Call {call_id}",
        "status": status,
        "detail_url": f"https://rtk.ee/{call_id}",
    }
    data.update(kw)
    return FundingCall(**data)
