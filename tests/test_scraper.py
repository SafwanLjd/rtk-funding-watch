"""Tests for parsing (no network)."""

from __future__ import annotations

import datetime as dt

import httpx
import respx

from rtk_funding_watch.models import Status
from rtk_funding_watch.scraper import (
    ScraperConfig,
    _clean,
    _dedupe_ids,
    _drop_boilerplate,
    parse_detail,
    parse_listing,
    parse_period,
    scrape,
)
from tests.factories import make_call


def test_parse_period_start_and_end() -> None:
    start, end, note = parse_period("alates 03.08.2026 kuni 18.11.2026 kell 16.00")
    assert start == dt.date(2026, 8, 3)
    assert end == dt.date(2026, 11, 18)
    assert note == ""


def test_parse_period_budget_note() -> None:
    _, _, note = parse_period(
        "alates 20.05.2026 kuni 31.08.2027 voi kuni eelarvevahendite ammendumiseni"
    )
    assert "budget" in note


def test_parse_period_fallback_bare_date() -> None:
    start, end, _ = parse_period("Taotlusvoor avatud alates 16.06.2025")
    assert start == dt.date(2025, 6, 16)
    assert end is None


def test_parse_listing_statuses_and_fields(listing_html: str) -> None:
    calls = parse_listing(listing_html)
    by_id = {c.id: c for c in calls}
    assert set(by_id) == {"alpha-meede", "beta-meede", "gamma-meede", "delta-meede"}
    assert by_id["alpha-meede"].status is Status.OPEN
    assert by_id["gamma-meede"].status is Status.UPCOMING
    assert by_id["delta-meede"].status is Status.CLOSED
    alpha = by_id["alpha-meede"]
    assert alpha.funding_source == "SF"
    assert alpha.field_domain == "regionaalareng"
    assert alpha.application_start == dt.date(2026, 9, 1)
    assert alpha.application_end == dt.date(2026, 10, 1)


def test_parse_listing_strips_tab_suffix(listing_html: str) -> None:
    calls = parse_listing(listing_html)
    beta = next(c for c in calls if c.id == "beta-meede")
    assert beta.name == "Beta meede"
    assert "budget" in beta.deadline_note


def test_parse_detail_classifies_links(detail_html: str) -> None:
    data = parse_detail(detail_html, "https://rtk.ee/alpha-meede")
    assert data["regulations"] == ["https://www.riigiteataja.ee/akt/123456?leiaKehtiv"]
    assert "https://pilv.rtk.ee/s/AAAAAA" in data["documents"]
    assert "https://rtk.ee/files/vorm.pdf" in data["documents"]
    assert data["images"] == [
        "https://rtk.ee/sites/default/files/2026/taotleja-teekond.png"
    ]


def test_drop_boilerplate_moves_common_docs() -> None:
    common = "https://pilv.rtk.ee/s/COMMON"
    calls = [
        make_call(f"c{i}", document_links=[common, f"https://pilv.rtk.ee/s/u{i}"])
        for i in range(6)
    ]
    cfg = ScraperConfig(boilerplate_min_pages=5, boilerplate_threshold=0.6)
    moved = _drop_boilerplate(calls, cfg)
    assert common in moved
    assert all(common not in c.document_links for c in calls)


def test_dedupe_ids_disambiguates_rounds_by_period() -> None:
    a = make_call("dup", application_period="alates 01.01.2026")
    b = make_call("dup", application_period="alates 01.06.2026")
    result = _dedupe_ids([a, b])
    ids = {c.id for c in result}
    assert len(ids) == 2
    assert all(i.startswith("dup-") for i in ids)


def test_dedupe_ids_stable_across_content_edits() -> None:
    # Two rounds of the same slug; editing one round's purpose must not change ids.
    def pair(purpose: str) -> list:  # type: ignore[type-arg]
        return [
            make_call("dup", application_period="alates 01.01.2026", purpose=purpose),
            make_call("dup", application_period="alates 01.06.2026"),
        ]

    before = {c.id for c in _dedupe_ids(pair("old"))}
    after = {c.id for c in _dedupe_ids(pair("new"))}
    assert before == after


def test_parse_period_recovers_both_dates_without_alates() -> None:
    start, end, _ = parse_period("Taotlusvoor on avatud 01.09.2025 kuni 30.09.2025")
    assert start == dt.date(2025, 9, 1)
    assert end == dt.date(2025, 9, 30)


def test_parse_period_handles_endash_range() -> None:
    start, end, _ = parse_period("01.09.2025 - 30.09.2025")
    assert start == dt.date(2025, 9, 1)
    assert end == dt.date(2025, 9, 30)


def test_parse_listing_drops_unsafe_and_offsite_links() -> None:
    html = (
        '<a name="Avatud_taotlusvoorud"></a><strong>AVATUD</strong>'
        '<p><a class="btn btn-secondary" href="javascript:alert(1)">Evil</a></p>'
        '<p><a class="btn btn-secondary" href="https://evil.example/x">Offsite</a></p>'
        '<p><a class="btn btn-secondary" href="https://rtk.ee/good">Good</a></p>'
    )
    calls = parse_listing(html)
    assert [c.id for c in calls] == ["good"]


def test_parse_detail_rejects_foreign_schemes() -> None:
    html = (
        '<a href="javascript:alert(1)">x</a>'
        '<a href="https://www.riigiteataja.ee/akt/1">reg</a>'
        '<a href="https://evil.example/riigiteataja.ee/fake">spoof</a>'
    )
    data = parse_detail(html, "https://rtk.ee/x")
    assert data["regulations"] == ["https://www.riigiteataja.ee/akt/1"]


def test_clean_strips_control_characters() -> None:
    assert _clean("bad\x01name\x1f!") == "badname!"


def test_scrape_end_to_end_mocked(listing_html: str, detail_html: str) -> None:
    cfg = ScraperConfig(listing_url="https://rtk.ee/listing", concurrency=2, retries=1)
    with respx.mock(assert_all_called=False) as router:
        router.get("https://rtk.ee/listing").mock(
            return_value=httpx.Response(200, text=listing_html)
        )
        router.get(url__regex=r"https://rtk\.ee/\w+-meede").mock(
            return_value=httpx.Response(200, text=detail_html)
        )
        snap = scrape(cfg, now=dt.datetime(2026, 10, 5, tzinfo=dt.UTC))

    assert len(snap.calls) == 4
    by_id = {c.id: c for c in snap.calls}
    assert by_id["alpha-meede"].regulation_urls == [
        "https://www.riigiteataja.ee/akt/123456?leiaKehtiv"
    ]
    assert any("pilv.rtk.ee" in u for u in by_id["alpha-meede"].document_links)
    assert snap.scraped_at == dt.datetime(2026, 10, 5, tzinfo=dt.UTC)
