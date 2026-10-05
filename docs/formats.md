# Formats reference

Every output is produced from one `Snapshot` by the serializers in
`src/rtk_funding_watch/serialize/`. The exporter writes four files under
`site/api/`:

| Format | File | Content-Type |
| --- | --- | --- |
| JSON | `calls.json` | `application/json; charset=utf-8` |
| TOON | `calls.toon` | `text/plain; charset=utf-8` |
| CSV | `calls.csv` | `text/csv; charset=utf-8` |
| RSS | `feed.xml` | `application/rss+xml; charset=utf-8` |

All four share the same data model, defined in `src/rtk_funding_watch/models.py`.

## Data model

### `FundingCall`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable slug derived from the detail-URL path. The match key for diffing. |
| `name` | string | Measure name as published. |
| `status` | string enum | `open`, `upcoming`, or `closed`. |
| `application_period` | string | Raw Estonian application-period text, verbatim. Default `""`. |
| `application_start` | date or null | `YYYY-MM-DD`, parsed from the period when determinable. |
| `application_end` | date or null | `YYYY-MM-DD`, parsed from the period when determinable. |
| `deadline_note` | string | Extra qualifier, e.g. "until budget is exhausted". Default `""`. |
| `target_group` | string | Default `""`. |
| `purpose` | string | Default `""`. |
| `field_domain` | string | Default `""`. |
| `funding_source` | string | Instrument tag when known: `SF`, `RRF`, `EMP`/`Norra`, `RE`. Default `""`. |
| `detail_url` | string | URL of the measure's detail page. |
| `source_host` | string | Host the detail page lives on, e.g. `rtk.ee`. |
| `regulation_urls` | array of string | Riigi Teataja legal-act URLs. |
| `document_links` | array of string | Measure-specific document URLs (forms, guides, annexes). |
| `image_urls` | array of string | Measure-specific content image URLs. |

### `Snapshot`

| Field | Type | Notes |
| --- | --- | --- |
| `source_url` | string | The listing URL that was scraped. |
| `scraped_at` | datetime | Timezone-aware. See per-format note below. |
| `generator` | string | Default `"rtk-funding-watch"`. |
| `calls` | array of `FundingCall` | Sorted by `(status, name)`. |
| `common_resources` | array of string | Site-wide helper documents lifted out of individual calls. |

A document link that appears on at least 60% of the calls (and on at least 5 of
them) is treated as site-wide boilerplate and moved from each call's
`document_links` into `Snapshot.common_resources`.

## JSON: `calls.json`

Pydantic's canonical JSON for the whole snapshot, two-space indented, with a
trailing newline. Lists stay as real JSON arrays. Dates render as `YYYY-MM-DD`;
`scraped_at` renders in UTC with a `Z` suffix (e.g. `2026-10-05T12:00:00Z`).
The top level is the `Snapshot`; `calls` holds the array of `FundingCall`
objects described above. JSON does not include the `counts` block (that is TOON
only).

```json
{
  "source_url": "https://www.rtk.ee/.../avatud-ja-suletud-taotlusvoorud",
  "scraped_at": "2026-10-05T12:00:00Z",
  "generator": "rtk-funding-watch",
  "calls": [
    {
      "id": "kagu-eesti-ettevotluse-arengutoetuse-andmine-2021-2027",
      "name": "Kagu-Eesti ettevõtluse arengutoetuse andmine",
      "status": "open",
      "application_period": "alates 01.09.2025",
      "application_start": "2025-09-01",
      "application_end": null,
      "deadline_note": "",
      "target_group": "mikro- ja väikeettevõtjast äriühing ...",
      "purpose": "aidata kaasa Kagu-Eesti piirkonna arengule",
      "field_domain": "regionaalareng",
      "funding_source": "",
      "detail_url": "https://rtk.ee/kagu-eesti-ettevotluse-...",
      "source_host": "rtk.ee",
      "regulation_urls": ["https://www.riigiteataja.ee/akt/104102023013?leiaKehtiv"],
      "document_links": ["https://pilv.rtk.ee/s/J4BwGYG7g3ZTpnN"],
      "image_urls": ["https://rtk.ee/sites/default/files/2025-08/Kagu-Eesti.png"]
    }
  ],
  "common_resources": ["https://pilv.rtk.ee/s/commonGuide123"]
}
```

## TOON: `calls.toon`

[TOON](https://github.com/toon-format/toon) encodes the snapshot as a compact,
mostly tabular document, produced by the official `toon-format` encoder
(spec v4.1). It is aimed at LLM input, where the tabular `calls` block uses far
fewer tokens than the equivalent JSON.

The document is a mapping with these top-level keys:

- `source_url`, `scraped_at`, `generator`: scalars. Here `scraped_at` is an
  ISO 8601 string with an explicit offset (e.g. `2026-10-05T12:00:00+00:00`),
  not the `Z` form used in JSON, because TOON serializes
  `datetime.isoformat()`.
- `counts`: a mapping of `open`, `upcoming`, `closed`, and `total`. This is
  computed for TOON and does not appear in the JSON output.
- `calls`: the tabular block.
- `common_resources`: an array of strings.

The `calls` block declares the columns once in a header, then one row per call:

```
calls[2]{id,name,status,application_period,application_start,application_end,deadline_note,target_group,purpose,field_domain,funding_source,detail_url,source_host,regulation_urls,document_links,image_urls}:
  kagu-eesti-...,Kagu-Eesti ettevõtluse arengutoetuse andmine,open,alates 01.09.2025,2025-09-01,null,"","mikro- ja väikeettevõtjast...",...,regionaalareng,"",...,rtk.ee,"https://www.riigiteataja.ee/akt/104102023013?leiaKehtiv","https://pilv.rtk.ee/s/J4BwGYG7g3ZTpnN;https://pilv.rtk.ee/s/HfENAwa3X858etZ","https://rtk.ee/sites/default/files/2025-08/Kagu-Eesti.png"
```

`calls[2]{...}` means a 2-row table with the listed columns. A tabular block
requires every column to be primitive, so the three URL-list fields
(`regulation_urls`, `document_links`, `image_urls`) are flattened to single
`;`-joined strings. The JSON output keeps them as real arrays for lossless
consumption. Use JSON when you need to split the URLs back out.

## CSV: `calls.csv`

One row per call plus a header row, comma-separated, LF line endings.
`scraped_at`, `generator`, `counts`, and `common_resources` are not included.
CSV carries the calls only. Columns, in exact order (`serialize/csv_fmt.py`
`FIELDS`):

```
id
status
name
application_period
application_start
application_end
deadline_note
target_group
purpose
field_domain
funding_source
detail_url
source_host
regulation_urls
document_links
image_urls
```

As in TOON, the three URL-list columns are `;`-joined strings. Empty dates and
empty strings are written as empty cells.

## RSS: `calls`' change feed, `feed.xml`

An RSS 2.0 feed. The channel carries:

- `title`: "RTK funding-call watchdog"
- `link`: the snapshot's `source_url`
- `description`: a fixed summary line
- `generator`: the snapshot's `generator`
- `lastBuildDate`: the snapshot's `scraped_at`, RFC 822 format

What drives the items:

- **With a non-empty diff**, each change event becomes one item, in the diff's
  order. The title is prefixed by the change type ("New call", "Call removed",
  "Call updated", "Status changed") followed by the call name. The description
  spells out the change (e.g. "Status changed from upcoming to open." or
  "Updated: application_period, purpose."). `pubDate` is the diff's
  `to_scraped_at`.
- **With no diff (or an empty one)**, the feed falls back to the currently
  **open** calls. One item per call whose status is `open`. The description is
  the call's `purpose`, or its `application_period`, or "Open funding call.".

Each item has a `title`, a `link` (the call's `detail_url`), a `description`, a
non-permalink `guid`, and a `pubDate`. The `guid` is built from the call id plus
either the snapshot timestamp and change type (diff items) or the call's content
hash (fallback items), so a given change produces a stable, unique id.

```xml
<item>
  <title>Status changed: Keskvalitsuse hoonete energiatõhususe parandamine...</title>
  <link>https://rtk.ee/keskvalitsuse-hoonete-energiatohususe-...</link>
  <description>Status changed from upcoming to open.</description>
  <guid isPermaLink="false">keskvalitsuse-...:2026-10-05T12:00:00+00:00:status_changed</guid>
  <pubDate>Mon, 05 Oct 2026 12:00:00 +0000</pubDate>
</item>
```

## MCP server

The `rtk-funding-mcp` command runs a Model Context Protocol server over stdio.
It loads one snapshot and serves it read-only: the tools and resources answer
from that snapshot and never scrape on demand. The snapshot is resolved in this
order: the `RTK_SNAPSHOT` environment variable, then `data/snapshots/latest.json`.
(Through the CLI, `rtk-watch mcp --snapshot PATH` can point at a specific file.)

### Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_funding_calls` | `status` (optional: `open`, `upcoming`, or `closed`) | The matching `FundingCall` objects. With no status, every call. |
| `get_funding_call` | `call_id` (string) | The single `FundingCall` with that `id`, or a not-found message. |
| `search_funding_calls` | `query` (string), `status` (optional) | The `FundingCall` objects whose name, purpose, target group or field contain the query (case-insensitive). |

Returned calls use the same field shape as the JSON format above.

### Resources

| Resource URI | Content | Type |
| --- | --- | --- |
| `rtk://calls` | JSON array of every `FundingCall` in the snapshot | `application/json` |
| `rtk://calls/{call_id}` | the single `FundingCall` with that `id`, or a JSON `{"error": ...}` | `application/json` |

Returned calls use the same field shape as the JSON format above.
