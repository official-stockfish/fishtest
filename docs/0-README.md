# Fishtest Server Documentation

## Overview

Fishtest is a distributed chess engine testing system. The server assigns
testing tasks to volunteer workers, collects game results, and computes
statistical analyses (SPRT, ELO) to determine whether code changes improve
Stockfish. The web interface provides dashboards for managing test runs,
viewing results, and administering users and workers.

## Documents

| # | Document | Audience | Description |
|---|---|---|---|
| 1 | [1-architecture.md](1-architecture.md) | All contributors | Server structure, module map, request flow, startup/shutdown |
| 2 | [2-threading-model.md](2-threading-model.md) | Backend contributors | Async/sync boundaries, threadpool usage, rules for new code |
| 3 | [3-api-reference.md](3-api-reference.md) | Worker and integration developers | Worker API endpoints, protocol invariants, error shapes |
| 4 | [4-ui-reference.md](4-ui-reference.md) | UI contributors | UI routes, view dispatch pipeline, htmx fragment dispatch, session/CSRF/auth |
| 5 | [5-templates.md](5-templates.md) | UI contributors | Jinja2 environment, template catalog (page + fragment), context contracts |
| 6 | [6-worker.md](6-worker.md) | Worker contributors | Worker architecture, task lifecycle, API usage |
| 7 | [7-development.md](7-development.md) | All developers | Dev setup, local server, testing, OpenAPI |
| 8 | [8-deployment.md](8-deployment.md) | Operators | systemd, nginx, kernel tuning, capacity audit |
| 9 | [9-references.md](9-references.md) | All developers | FastAPI, Starlette, Jinja2, htmx curated references |

## Quick start

```bash
# Clone and install
cd server && uv sync

# Run tests
uv run python -m unittest discover -s tests -q

# Start the development server
FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000

# Start with OpenAPI docs enabled (/docs, /redoc)
OPENAPI_URL=/openapi.json FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000

# Entrypoint
# server/fishtest/app.py
```

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Starlette (ASGI) |
| Application server | Uvicorn |
| Templates | Jinja2 (`.html.j2`, `StrictUndefined`) |
| Client interactivity | htmx 2.0.8 (CDN, fragment polling/swaps, OOB updates) |
| Session management | itsdangerous `TimestampSigner` cookie sessions |
| Database | MongoDB (pymongo) |
| Validation | vtjson (19 schemas; no Pydantic) |
| Statistics | scipy, numpy (SPRT, ELO calculations) |
| Python (server) | >= 3.14 |
| Python (worker) | >= 3.8 |

## Project layout
```
fishtest/
|-- pyproject.toml             -- Root: dev tools (ruff, ty, pre-commit)
|-- uv.lock                    -- Locked dependency set for the root project
|-- .pre-commit-config.yaml    -- Pre-commit hooks (ruff, format, uv-lock)
|-- .github/workflows/         -- CI: lint, server tests, worker tests (POSIX + MSYS2)
|-- server/
|   |-- pyproject.toml         -- Server package: runtime + test dependencies
|   `-- fishtest/              -- FastAPI application (Python >= 3.14)
`-- worker/
    |-- pyproject.toml         -- Worker package: runtime dependencies (Python >= 3.8)
    |-- worker.py              -- Main worker script
    |-- games.py               -- Engine compilation, game execution
    |-- updater.py             -- Self-update mechanism
    `-- packages/              -- Vendored packages
```

### Why three `pyproject.toml` files

The root `pyproject.toml` defines **development-only tools** (ruff, ty, pre-commit)
shared across the repo. The server and worker each have their own
`pyproject.toml` with independent dependency sets and Python version
constraints -- the server requires Python >= 3.14 while the worker supports
Python >= 3.8 to run on contributor machines with older distributions.

### Build system

Both the server and worker use **hatchling** as the build backend. Hatchling
is a lightweight, standards-compliant PEP 517 build system with no runtime
dependencies.

### Dependency management with uv

[uv](https://docs.astral.sh/uv/) is the package manager. The root `uv.lock`
locks all dependencies (root + server + worker) for reproducible installs.

```bash
# Install all dependencies (server)
cd server && uv sync

# Add a dependency
uv add <package>               # runtime dependency
uv add --group test <package>  # test-only dependency

# Remove a dependency
uv remove <package>

# Update a dependency
uv lock --upgrade-package <package>

# Regenerate the lock file from scratch
uv lock
```

After any dependency change, commit both the modified `pyproject.toml` and
the updated `uv.lock`.

### Pre-commit hooks

The `.pre-commit-config.yaml` runs on every commit:

- **pre-commit-hooks** -- large file check, TOML/YAML validation, trailing whitespace
- **ruff** -- lint (`--fix`) and format
- **uv-lock** -- verify `uv.lock` is up to date

Install with: `uv run pre-commit install`

### CI workflows

| Workflow | File | Trigger | What it does |
|----------|------|---------|-------------|
| Lint | `lint.yaml` | push, PR | ruff check + format |
| Server | `server.yaml` | push, PR | Server test suite (MongoDB required) |
| Worker POSIX | `worker_posix.yaml` | push, PR | Worker tests on Linux/macOS |
| Worker MSYS2 | `worker_msys2.yaml` | push, PR | Worker tests on Windows (MSYS2) |
