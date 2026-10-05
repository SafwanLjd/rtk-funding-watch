# rtk-funding-watch

A watchdog for Estonian public-sector funding calls. It scrapes the funding
rounds that Riigi Tugiteenuste Keskus (RTK) publishes at
[rtk.ee](https://rtk.ee), normalizes them into a single data model, and
republishes them in several machine-readable formats: JSON, TOON, CSV, and an
RSS change feed. It also ships an MCP server so an LLM agent can query the
calls, and a static website that renders the current calls and recent changes.

Each run saves a timestamped snapshot. The next run diffs against the previous
snapshot, so new calls, closed calls, status changes, and edits become a feed
of change events.

## Scope

rtk-funding-watch reads only public pages on `rtk.ee`. It does not log in to,
scrape, or touch the authenticated **e-toetus** portal. It sends a descriptive
`User-Agent`, fetches the public listing and the linked detail pages, and does
nothing else.

## Install

The project is managed with [uv](https://docs.astral.sh/uv/) and needs Python
3.11 or newer.

```bash
# clone, then from the repo root:
uv sync                 # create .venv and install runtime + dev dependencies
```

To install it as a package into an existing environment:

```bash
uv pip install -e .     # editable install, exposes the two console scripts
```

This installs two commands: `rtk-watch` (the CLI) and `rtk-funding-mcp` (the
MCP server).

## Quickstart

```bash
# 1. Fetch the listing and save a snapshot under data/snapshots/.
rtk-watch scrape

# 2. Show what changed since the previous snapshot.
rtk-watch diff

# 3. Write the machine-readable files under site/api/.
rtk-watch export

# 4. Export the files and render the static site under site/.
rtk-watch build-site

# Or do all of the above in one pass:
rtk-watch run
```

`rtk-watch scrape` prints the saved path and a status summary:

```
Saved snapshot data/snapshots/snapshot-20261005T120000Z.json (2 calls)
      RTK funding calls
  status     count
  open           1
  upcoming       1
  closed         0
  total          2
```

Use `-v` / `--verbose` for info-level logging. Every command takes
`--data-dir` (snapshot store, default `data/snapshots`); the export, build-site,
and run commands take `--out` (output root, default `site`).

## Commands

| Command | What it does |
| --- | --- |
| `rtk-watch scrape` | Fetch the listing + detail pages, save a timestamped snapshot and refresh `latest.json`. |
| `rtk-watch diff` | Print the change events between the two most recent snapshots. |
| `rtk-watch export` | Write `calls.json`, `calls.toon`, `calls.csv`, and `feed.xml` under `<out>/api/`. |
| `rtk-watch build-site` | Export the files, then render the static website under `<out>/`. |
| `rtk-watch run` | The full pipeline: scrape, diff against the prior snapshot, export, render the site. |
| `rtk-watch mcp` | Launch the MCP stdio server (optionally `--snapshot PATH`). |

## Machine-readable formats

Every format is produced from the same `Snapshot`. The exporter writes all four
under `site/api/`. See [docs/formats.md](docs/formats.md) for the full field
reference.

### JSON: `api/calls.json`

The full snapshot, serialized by Pydantic. Lists stay as real arrays.

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
      "funding_source": "",
      "detail_url": "https://rtk.ee/kagu-eesti-ettevotluse-...",
      "regulation_urls": ["https://www.riigiteataja.ee/akt/104102023013?leiaKehtiv"],
      "document_links": ["https://pilv.rtk.ee/s/J4BwGYG7g3ZTpnN"],
      "image_urls": ["https://rtk.ee/sites/default/files/2025-08/Kagu-Eesti.png"]
    }
  ],
  "common_resources": ["https://pilv.rtk.ee/s/commonGuide123"]
}
```

### TOON: `api/calls.toon`

[TOON](https://github.com/toon-format/toon) (Token-Oriented Object Notation)
renders the uniform `calls` array as one tabular block, which is cheaper to feed
to an LLM than JSON. The header lists the columns once; each call is one row.
The three URL-list fields are flattened to `;`-joined strings so the table stays
tabular (JSON keeps them as arrays).

```
scraped_at: "2026-10-05T12:00:00+00:00"
generator: rtk-funding-watch
counts:
  open: 1
  upcoming: 1
  closed: 0
  total: 2
calls[2]{id,name,status,application_period,application_start,application_end,deadline_note,target_group,purpose,field_domain,funding_source,detail_url,source_host,regulation_urls,document_links,image_urls}:
  kagu-eesti-...,Kagu-Eesti ettevõtluse arengutoetuse andmine,open,alates 01.09.2025,2025-09-01,null,"","mikro- ja väikeettevõtjast...",...,regionaalareng,"",...,rtk.ee,"https://www.riigiteataja.ee/akt/104102023013?leiaKehtiv","https://pilv.rtk.ee/s/J4BwGYG7g3ZTpnN;https://pilv.rtk.ee/s/HfENAwa3X858etZ","https://rtk.ee/sites/default/files/2025-08/Kagu-Eesti.png"
common_resources[1]: "https://pilv.rtk.ee/s/commonGuide123"
```

### CSV: `api/calls.csv`

One row per call, with a header. Columns, in order:

```
id, status, name, application_period, application_start, application_end,
deadline_note, target_group, purpose, field_domain, funding_source,
detail_url, source_host, regulation_urls, document_links, image_urls
```

The three URL-list columns are `;`-joined, matching the TOON flattening.

### RSS: `api/feed.xml`

An RSS 2.0 feed. When a diff is available, each change is one item (new call,
status change, edit, removal). With no previous snapshot, the feed falls back to
listing the currently open calls.

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

The MCP server exposes the funding calls to LLM agents over the Model Context
Protocol. It runs over stdio and serves a loaded snapshot read-only. It does
not scrape on demand.

```bash
rtk-funding-mcp                      # serve data/snapshots/latest.json
RTK_SNAPSHOT=data/snapshots/latest.json rtk-funding-mcp   # serve a specific file
# equivalently, through the CLI (supports --snapshot):
rtk-watch mcp --snapshot data/snapshots/latest.json
```

Register it with an MCP client (for example, in a client's `mcpServers`
config):

```json
{
  "mcpServers": {
    "rtk-funding": {
      "command": "rtk-funding-mcp",
      "env": { "RTK_SNAPSHOT": "/absolute/path/to/data/snapshots/latest.json" }
    }
  }
}
```

The server exposes three tools: `list_funding_calls` (optionally filtered by
status), `get_funding_call` by id, and `search_funding_calls` by text. It also exposes two
resources: `rtk://calls` (all calls as JSON) and `rtk://calls/{call_id}` (one
call). Argument and return shapes are documented in
[docs/formats.md](docs/formats.md#mcp-server).

## How the watchdog works

Every scrape is stored as an immutable, timestamped JSON file:

```
data/snapshots/
  snapshot-20261004T120000Z.json
  snapshot-20261005T120000Z.json
  latest.json                       # a copy of the newest snapshot
```

The watchdog compares the two most recent snapshots call by call. A call is
matched by its stable `id` (a slug from its detail URL). The differ emits:

- `added`: a call present in the new snapshot but not the old one.
- `removed`: a call that disappeared from the listing.
- `status_changed`: the same call, different status (e.g. `upcoming` → `open`).
- `modified`: same status, but a tracked field changed. Edits are detected by
  a content hash over the call's semantic fields, so reordering a URL list or a
  volatile scrape timestamp never registers as a change.

Those change events drive the RSS feed and the "recent changes" section of the
static site. See [docs/architecture.md](docs/architecture.md) for the full
pipeline.

## Project layout

```
src/rtk_funding_watch/
  models.py        # Pydantic data model: FundingCall, Snapshot, Diff, ...
  scraper.py       # fetch + parse rtk.ee into a Snapshot
  storage.py       # save/load timestamped snapshots, find latest/previous
  watchdog.py      # diff two snapshots into change events
  serialize/       # json, toon, csv, rss serializers + dispatcher
  site.py          # render the static website (built separately)
  mcp_server.py    # MCP stdio server (built separately)
  templates/       # Jinja2 templates for the site
  static/          # static assets for the site
  cli.py           # the rtk-watch command
data/snapshots/    # saved snapshots + latest.json
site/              # generated website + site/api/ machine-readable files
tests/             # pytest suite with saved-HTML fixtures
docs/              # this documentation
```

## Development

```bash
uv sync                       # install runtime + dev dependencies
pre-commit install            # install the git hooks
pre-commit run --all-files    # run every hook across the repo

ruff check src tests          # lint
ruff format src tests         # format (line length 88)
mypy src tests                # strict type checking
codespell                     # spell-check code and docs
pytest                        # run the test suite
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
[Commitizen](https://commitizen-tools.github.io/commitizen/) is configured in
`pyproject.toml`:

```bash
cz commit      # guided conventional-commit message
cz bump        # bump the version and tag from the commit history
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow.

## License

MIT. The license is declared in `pyproject.toml`.
