# Contributing

Thanks for working on rtk-funding-watch. This file describes the local setup,
the quality bar, and the commit conventions.

## Setup

The project uses [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer.

```bash
uv sync               # create .venv, install runtime + dev dependencies
pre-commit install    # install the git hooks so checks run on every commit
```

Run commands inside the environment with `uv run <cmd>`, or activate `.venv`
directly.

## Quality bar

Every change must pass the full set of checks before it is committed. The
pre-commit hooks run these on every commit; run them by hand as well:

```bash
ruff check src tests          # lint (rules in pyproject.toml)
ruff format --check src tests # formatting, line length 88
mypy src tests                # strict type checking
codespell                     # spell-check code and docs
pytest                        # tests
```

Rules worth knowing:

- **Type everything.** mypy runs in `strict` mode with the Pydantic plugin.
  Public functions have full annotations and a concise docstring.
- **No parent-relative imports.** Ruff's `TID252` forbids `from ..x import y`.
  Use absolute imports: `from rtk_funding_watch.models import Snapshot`.
- **Line length is 88.** `ruff format` is the source of truth.
- **Keep `models.py` free of I/O.** The data model is the shared contract for
  the scraper, differ, serializers, site, and MCP server; it must stay cheap to
  import and trivial to validate.

## Tests

Tests live in `tests/`. The scraper's parsing functions (`parse_listing`,
`parse_detail`, `parse_period`) are pure and are tested against saved HTML
fixtures in `tests/fixtures/`, so the suite runs with no network access. When
you change parsing, add or update a fixture rather than hitting the live site.

```bash
pytest                 # run everything
pytest --cov           # with coverage (pytest-cov is installed)
```

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
The format is:

```
<type>(<optional scope>): <description>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`.
Examples:

```
feat(serialize): add RSS change feed
fix(scraper): handle missing application-period list
docs: document the TOON format
```

[Commitizen](https://commitizen-tools.github.io/commitizen/) is configured in
`pyproject.toml` and can build the message and manage versioning for you:

```bash
cz commit     # interactive conventional-commit prompt
cz bump       # bump version + create a tag from the commit history
```

The commit-message convention is enforced by a pre-commit hook, so a
non-conforming message is rejected.

## Pull requests

- Keep each pull request focused on one change.
- Make sure `pre-commit run --all-files` and `pytest` pass.
- Update the docs in `docs/` and the `README.md` when behavior changes.
