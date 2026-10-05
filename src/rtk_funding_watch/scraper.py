"""Scrape and parse RTK funding calls from rtk.ee into a :class:`Snapshot`.

The public entry point is :func:`scrape`. Parsing is factored into pure
functions (:func:`parse_listing`, :func:`parse_detail`, :func:`parse_period`)
so they can be unit-tested against saved HTML fixtures without network access.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import FundingCall, Snapshot, Status

logger = logging.getLogger(__name__)

DEFAULT_LISTING_URL = (
    "https://www.rtk.ee/toetused-taotlemine/taotlusvoorud/"
    "avatud-ja-suletud-taotlusvoorud"
)
USER_AGENT = "rtk-funding-watch/0.1 (+https://github.com/SafwanLjd/rtk-funding-watch)"

# <a name="..."> anchors that mark the three status sections, in document order.
_SECTION_ANCHORS: dict[str, Status] = {
    "avatud_taotlusvoorud": Status.OPEN,
    "peagi_avanevad_taotlusvoorud": Status.UPCOMING,
    "suletud_taotlusvoorud": Status.CLOSED,
}

_FIELD_LABELS: dict[str, str] = {
    "taotlemine": "application_period",
    "sihtgrupp": "target_group",
    "eesmärk": "purpose",
    "valdkond": "field_domain",
}

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_START_RE = re.compile(r"alates\s*(\d{1,2}\.\d{1,2}\.\d{4})", re.IGNORECASE)
_END_RE = re.compile(r"kuni\s*(\d{1,2}\.\d{1,2}\.\d{4})", re.IGNORECASE)
_FUNDING_RE = re.compile(r"\((SF|RRF|EMP[^)]*|Norra|RE)\)")
_TAB_SUFFIX_RE = re.compile(r"\s*avaneb uues vahekaardis\s*$", re.IGNORECASE)

_DOC_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|ods|rtf)(\?|$)", re.IGNORECASE)
_IMG_CHROME_RE = re.compile(
    r"logo|icon|sprite|placeholder|avatar|vapp_toetame|/css/|/js/", re.IGNORECASE
)


@dataclass(slots=True)
class ScraperConfig:
    """Tunables for a scrape run."""

    listing_url: str = DEFAULT_LISTING_URL
    timeout: float = 30.0
    concurrency: int = 5
    retries: int = 3
    user_agent: str = USER_AGENT
    # A document link present on at least this fraction of calls (and on at
    # least ``boilerplate_min_pages`` of them) is treated as a site-wide helper
    # resource, dropped from individual calls into ``Snapshot.common_resources``.
    boilerplate_threshold: float = 0.6
    boilerplate_min_pages: int = 5


def _slug(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    return tail.lower() or "call"


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _to_date(token: str) -> dt.date | None:
    m = _DATE_RE.search(token)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_period(text: str) -> tuple[dt.date | None, dt.date | None, str]:
    """Extract (start, end, note) from an Estonian application-period string."""
    text = " ".join(text.split())
    start = _to_date(m.group(1)) if (m := _START_RE.search(text)) else None
    end = _to_date(m.group(1)) if (m := _END_RE.search(text)) else None
    if start is None and end is None and (m := _DATE_RE.search(text)):
        # Fall back to the first bare date (e.g. "Taotlusvoor ... 16.06.2025").
        start = _to_date(m.group(0))
    note = ""
    if "ammendum" in text.lower():
        note = "kuni eelarvevahendite ammendumiseni (until budget is exhausted)"
    return start, end, note


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).strip()


def _dedupe(items: list[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    return list(dict.fromkeys(items))


def _attr(el: Tag, name: str) -> str:
    """Return a single string value for an attribute (BS4 may return a list)."""
    value = el.get(name)
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def parse_listing(html: str) -> list[FundingCall]:
    """Parse the listing page into skeleton calls (no detail-page fields yet)."""
    soup = BeautifulSoup(html, "lxml")
    calls: list[FundingCall] = []
    current: Status | None = None
    pending: FundingCall | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            calls.append(pending)
            pending = None

    for el in soup.find_all(["a", "ul"]):
        if not isinstance(el, Tag):
            continue
        if el.name == "a":
            anchor_name = _attr(el, "name").strip().lower()
            if anchor_name in _SECTION_ANCHORS:
                current = _SECTION_ANCHORS[anchor_name]
                continue
            classes = el.get("class") or []
            href = _attr(el, "href")
            if "btn-secondary" in classes and href and current is not None:
                name = _TAB_SUFFIX_RE.sub("", _clean(el.get_text(" ")))
                if not name:
                    continue
                flush()
                fsrc = m.group(1) if (m := _FUNDING_RE.search(name)) else ""
                pending = FundingCall(
                    id=_slug(href),
                    name=name,
                    status=current,
                    detail_url=urljoin("https://rtk.ee/", href),
                    source_host=_host(urljoin("https://rtk.ee/", href)),
                    funding_source=fsrc,
                )
        elif el.name == "ul" and pending is not None and not pending.application_period:
            for li in el.find_all("li", recursive=False) or el.find_all("li"):
                txt = _clean(li.get_text(" "))
                low = txt.lower()
                for label, attr in _FIELD_LABELS.items():
                    if low.startswith(label):
                        value = _clean(txt[len(label) :].lstrip(" :"))
                        setattr(pending, attr, value)
                        break
            flush()
    flush()

    for call in calls:
        if call.application_period:
            start, end, note = parse_period(call.application_period)
            call.application_start, call.application_end, call.deadline_note = (
                start,
                end,
                note,
            )
    return calls


def parse_detail(html: str, base_url: str) -> dict[str, list[str]]:
    """Extract regulation, document and image URLs from a measure detail page."""
    soup = BeautifulSoup(html, "lxml")
    regulations: list[str] = []
    documents: list[str] = []
    images: list[str] = []

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, str(a["href"]).strip())
        low = href.lower()
        if "riigiteataja.ee" in low:
            regulations.append(href)
        elif "pilv.rtk.ee/s/" in low or _DOC_EXT_RE.search(low):
            documents.append(href)

    for img in soup.find_all("img", src=True):
        src = str(img["src"]).strip()
        if _IMG_CHROME_RE.search(src):
            continue
        if re.search(r"\.(png|jpe?g|gif|webp)(\?|$)", src, re.IGNORECASE):
            images.append(urljoin(base_url, src))

    return {
        "regulations": _dedupe(regulations),
        "documents": _dedupe(documents),
        "images": _dedupe(images),
    }


def _fetch(client: httpx.Client, url: str, retries: int) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:  # pragma: no cover - network timing
            last_exc = exc
            logger.warning(
                "fetch %s failed (attempt %d/%d): %s", url, attempt, retries, exc
            )
    raise RuntimeError(f"failed to fetch {url}: {last_exc}")


def _drop_boilerplate(calls: list[FundingCall], cfg: ScraperConfig) -> list[str]:
    """Move site-wide helper documents out of calls into a shared list."""
    if not calls:
        return []
    freq: Counter[str] = Counter()
    for call in calls:
        freq.update(set(call.document_links))
    cutoff = max(cfg.boilerplate_min_pages, cfg.boilerplate_threshold * len(calls))
    common = {url for url, n in freq.items() if n >= cutoff}
    if not common:
        return []
    for call in calls:
        call.document_links = [u for u in call.document_links if u not in common]
    return sorted(common)


def _dedupe_ids(calls: list[FundingCall]) -> list[FundingCall]:
    """Ensure ids are unique and stable; drop exact (slug+content) duplicates."""
    by_slug: dict[str, list[FundingCall]] = defaultdict(list)
    for call in calls:
        by_slug[call.id].append(call)
    result: list[FundingCall] = []
    for slug, group in by_slug.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        seen_hashes: set[str] = set()
        for call in group:
            digest = call.content_hash()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            call.id = f"{slug}-{digest[:6]}"
            result.append(call)
    return result


def scrape(
    cfg: ScraperConfig | None = None, *, now: dt.datetime | None = None
) -> Snapshot:
    """Scrape the RTK listing and all detail pages into a :class:`Snapshot`.

    ``now`` is injectable so callers (and tests) control the timestamp.
    """
    cfg = cfg or ScraperConfig()
    scraped_at = now or dt.datetime.now(dt.UTC)
    headers = {"User-Agent": cfg.user_agent}
    with httpx.Client(
        headers=headers, timeout=cfg.timeout, follow_redirects=True
    ) as client:
        logger.info("fetching listing %s", cfg.listing_url)
        listing_html = _fetch(client, cfg.listing_url, cfg.retries)
        calls = parse_listing(listing_html)
        logger.info("parsed %d calls from listing", len(calls))

        unique_urls = sorted({c.detail_url for c in calls})

        def load(url: str) -> tuple[str, dict[str, list[str]] | None]:
            try:
                return url, parse_detail(_fetch(client, url, cfg.retries), url)
            except Exception as exc:  # pragma: no cover - network timing
                logger.warning("detail fetch failed for %s: %s", url, exc)
                return url, None

        details: dict[str, dict[str, list[str]]] = {}
        with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
            for url, data in pool.map(load, unique_urls):
                if data is not None:
                    details[url] = data

    for call in calls:
        if data := details.get(call.detail_url):
            call.regulation_urls = data["regulations"]
            call.document_links = data["documents"]
            call.image_urls = data["images"]

    calls = _dedupe_ids(calls)
    common = _drop_boilerplate(calls, cfg)
    calls.sort(key=lambda c: (c.status.value, c.name.lower()))

    return Snapshot(
        source_url=cfg.listing_url,
        scraped_at=scraped_at,
        calls=calls,
        common_resources=common,
    )
