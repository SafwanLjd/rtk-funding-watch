# Architecture

rtk-funding-watch is a pipeline. A scrape produces a `Snapshot`; the snapshot is
saved and diffed against the previous one; the snapshot and diff are then
serialized into machine-readable files, a static site, and the MCP server's
responses.

```
            rtk.ee (public listing + detail pages)
                       |
                       v
   +---------------------------------------+
   |  scraper.scrape()                     |   fetch + parse
   +---------------------------------------+
                       |
                       v
                   Snapshot  ------------------+
                       |                        |
     storage.save_snapshot()                    |
                       |                        |
                       v                        |
        data/snapshots/snapshot-*.json          |
            data/snapshots/latest.json          |
                       |                        |
        storage.previous_snapshot()             |
                       |                        |
                       v                        v
   +---------------------------------------+   (snapshot)
   |  watchdog.diff_snapshots(prev, new)   |
   +---------------------------------------+
                       |
                       v
                     Diff  (change events)
                       |
         +-------------+-----------------------------+
         |             |                             |
         v             v                             v
   serialize/*    site.build_site()           mcp_server.main()
   json toon      templates + static          stdio MCP server
   csv  rss       -> site/ + site/api/        (tools + resources)
```

## Modules

Each module has one job and depends only on `models.py` plus its own concern.

| Module | Responsibility |
| --- | --- |
| `models.py` | The Pydantic data model shared by everything. No I/O, no parsing. |
| `scraper.py` | Fetch the rtk.ee listing and detail pages and parse them into a `Snapshot`. Parsing functions are pure and fixture-testable. |
| `storage.py` | Write and read timestamped snapshot JSON files; find the latest and previous snapshot; maintain `latest.json`. |
| `watchdog.py` | Diff an old and a new `Snapshot` into an ordered `Diff` of change events. The watchdog core. |
| `serialize/` | Render a `Snapshot` (and optional `Diff`) into JSON, TOON, CSV, and RSS. A dispatcher enumerates the formats. |
| `site.py` | Render the static website from a snapshot and diff, using the Jinja2 `templates/` and `static/` assets. Built separately. |
| `mcp_server.py` | Serve a loaded snapshot over the Model Context Protocol (stdio). Built separately. |
| `cli.py` | The `rtk-watch` command wiring the pipeline together. |

## The pipeline, step by step

1. **Scrape.** `scraper.scrape()` fetches the listing, parses it into skeleton
   calls (name, status, application period, and the four labelled list fields),
   then fetches each detail page concurrently to collect regulation URLs,
   document links, and images. It deduplicates call ids, lifts site-wide
   boilerplate documents into `common_resources`, sorts the calls, and returns a
   `Snapshot`. The timestamp is injectable so tests are deterministic.

2. **Save.** `storage.save_snapshot()` writes the snapshot to
   `data/snapshots/snapshot-<UTC-timestamp>.json` and refreshes
   `latest.json`. Filenames are sortable, so "latest" and "previous" are just
   the last two entries of a sorted glob.

3. **Diff.** `watchdog.diff_snapshots(prev, new)` matches calls by `id` and
   emits `added`, `removed`, `status_changed`, and `modified` events. Edits are
   detected by `FundingCall.content_hash()` over the semantic fields, so a
   reordered URL list or a changed scrape timestamp does not register as a
   change. Events are ordered: added, status-changed, modified, removed, then by
   name.

4. **Serialize.** `serialize.serialize(snapshot, fmt, diff=diff)` renders each
   format. JSON and CSV carry the calls; TOON adds a `counts` block and a
   tabular `calls` block; RSS turns the diff's events into feed items (or lists
   the open calls when there is no diff).

5. **Publish.** `site.build_site()` renders the HTML pages (current calls plus a
   "recent changes" section driven by the diff) alongside the `site/api/` files.
   Separately, `mcp_server.main()` serves a loaded snapshot to MCP clients.

The CLI composes these steps. `rtk-watch run` does the whole sequence; the other
subcommands run individual stages. See [formats.md](formats.md) for the output
shapes and the [README](../README.md) for usage.

## Data model

The model lives in `models.py` and is the single contract every other module
reads and writes.

- **`FundingCall`**: one funding measure / application round. `content_hash()`
  is a 16-hex-char digest over its semantic fields (name, status, period, target
  group, purpose, domain, funding source, and the sorted URL lists), used by the
  differ to detect edits.
- **`Snapshot`**: a full scrape at a point in time: `source_url`, `scraped_at`,
  `generator`, `calls`, and `common_resources`. `by_id()` indexes the calls;
  `counts()` tallies them per status plus a total.
- **`Status`**: a string enum: `open`, `upcoming`, `closed`.
- **`Diff`**: the ordered changes from an older to a newer snapshot:
  `from_scraped_at`, `to_scraped_at`, `events`, and `is_empty()`.
- **`ChangeEvent`**: one change to one call: a `ChangeType`
  (`added`/`removed`/`modified`/`status_changed`), the call id and name, the
  detail URL, old/new status, and a list of `FieldChange`.
- **`FieldChange`**: one `field` with its `old` and `new` values.

All models forbid extra fields (`extra="forbid"`), so a malformed snapshot fails
validation on load rather than silently carrying junk.
