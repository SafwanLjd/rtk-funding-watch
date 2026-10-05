"""Command-line interface for rtk-funding-watch.

Subcommands:

* ``scrape``     : fetch the RTK listing, save a timestamped snapshot.
* ``diff``       : show changes between the two most recent snapshots.
* ``export``     : write machine-readable files (json/toon/csv/rss).
* ``build-site`` : export the files and render the static website.
* ``run``        : the full watchdog pipeline (scrape → diff → export → site).
* ``mcp``        : launch the MCP stdio server.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rtk_funding_watch import serialize, storage
from rtk_funding_watch.models import Diff, Snapshot
from rtk_funding_watch.scraper import ScraperConfig, scrape
from rtk_funding_watch.watchdog import diff_snapshots

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Watchdog for RTK (rtk.ee) funding calls.",
)
console = Console()

DEFAULT_DATA_DIR = Path("data/snapshots")
DEFAULT_SITE_DIR = Path("site")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.callback()
def _main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable info logging.")
    ] = False,
) -> None:
    _setup_logging(verbose)


def _load_latest(data_dir: Path) -> Snapshot:
    snapshot = storage.latest_snapshot(data_dir)
    if snapshot is None:
        console.print(
            f"[red]No snapshots found in {data_dir}. Run 'rtk-watch scrape' first.[/]"
        )
        raise typer.Exit(code=1)
    return snapshot


def _current_diff(data_dir: Path, latest: Snapshot) -> Diff | None:
    previous = storage.previous_snapshot(data_dir)
    return diff_snapshots(previous, latest) if previous else None


def _print_summary(snapshot: Snapshot) -> None:
    counts = snapshot.counts()
    table = Table(title="RTK funding calls", show_edge=False)
    table.add_column("status", style="cyan")
    table.add_column("count", justify="right")
    for status in ("open", "upcoming", "closed", "total"):
        table.add_row(status, str(counts[status]))
    console.print(table)


def _write_api_files(
    snapshot: Snapshot, diff: Diff | None, out_dir: Path
) -> list[Path]:
    api_dir = out_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in serialize.FORMATS:
        path = api_dir / serialize.file_name(fmt)
        path.write_text(serialize.serialize(snapshot, fmt, diff=diff), encoding="utf-8")
        written.append(path)
    return written


@app.command()
def scrape_cmd(
    data_dir: Annotated[
        Path, typer.Option("--data-dir", help="Where snapshots are stored.")
    ] = DEFAULT_DATA_DIR,
    listing_url: Annotated[
        str | None, typer.Option("--listing-url", help="Override the listing URL.")
    ] = None,
) -> None:
    """Scrape the RTK listing and save a timestamped snapshot."""
    cfg = ScraperConfig(listing_url=listing_url) if listing_url else ScraperConfig()
    snapshot = scrape(cfg)
    path = storage.save_snapshot(snapshot, data_dir)
    console.print(f"[green]Saved snapshot[/] {path} ({len(snapshot.calls)} calls)")
    _print_summary(snapshot)


@app.command()
def diff(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    """Show changes between the two most recent snapshots."""
    latest = _load_latest(data_dir)
    changes = _current_diff(data_dir, latest)
    if changes is None or changes.is_empty():
        console.print("[yellow]No previous snapshot or no changes detected.[/]")
        return
    table = Table(title="Changes")
    table.add_column("type", style="magenta")
    table.add_column("call")
    table.add_column("detail")
    for event in changes.events:
        detail = ""
        if event.old_status and event.new_status:
            detail = f"{event.old_status} → {event.new_status}"
        elif event.changes:
            detail = ", ".join(c.field for c in event.changes)
        table.add_row(event.type, event.name, detail)
    console.print(table)


@app.command()
def export(
    out_dir: Annotated[Path, typer.Option("--out")] = DEFAULT_SITE_DIR,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    """Write machine-readable files (json/toon/csv/rss) under OUT/api/."""
    latest = _load_latest(data_dir)
    changes = _current_diff(data_dir, latest)
    written = _write_api_files(latest, changes, out_dir)
    for path in written:
        console.print(f"[green]wrote[/] {path}")


@app.command()
def build_site(
    out_dir: Annotated[Path, typer.Option("--out")] = DEFAULT_SITE_DIR,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
) -> None:
    """Export machine-readable files and render the static website."""
    from rtk_funding_watch import site  # noqa: PLC0415 (lazy: optional heavy import)

    latest = _load_latest(data_dir)
    changes = _current_diff(data_dir, latest)
    _write_api_files(latest, changes, out_dir)
    pages = site.build_site(latest, changes, out_dir)
    for path in pages:
        console.print(f"[green]rendered[/] {path}")


@app.command()
def run(
    out_dir: Annotated[Path, typer.Option("--out")] = DEFAULT_SITE_DIR,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = DEFAULT_DATA_DIR,
    listing_url: Annotated[str | None, typer.Option("--listing-url")] = None,
) -> None:
    """Full watchdog pipeline: scrape, diff, export and render the site."""
    from rtk_funding_watch import site  # noqa: PLC0415 (lazy: optional heavy import)

    cfg = ScraperConfig(listing_url=listing_url) if listing_url else ScraperConfig()
    previous = storage.latest_snapshot(data_dir)
    snapshot = scrape(cfg)
    storage.save_snapshot(snapshot, data_dir)
    changes = diff_snapshots(previous, snapshot)
    _write_api_files(snapshot, changes, out_dir)
    site.build_site(snapshot, changes, out_dir)
    console.print(
        f"[green]Watchdog run complete[/]: {len(snapshot.calls)} calls, "
        f"{len(changes.events)} change(s)."
    )
    _print_summary(snapshot)


@app.command()
def mcp(
    snapshot: Annotated[
        Path | None, typer.Option("--snapshot", help="Snapshot JSON to serve.")
    ] = None,
) -> None:
    """Launch the MCP stdio server exposing the funding calls."""
    from rtk_funding_watch import mcp_server  # noqa: PLC0415 (lazy: optional dep)

    mcp_server.main(snapshot_path=snapshot)


# Typer uses the function name for the command; expose 'scrape' not 'scrape-cmd'.
app.registered_commands[0].name = "scrape"


if __name__ == "__main__":
    app()
