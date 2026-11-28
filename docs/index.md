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
| 1 | [Architecture](architecture.md) | All contributors | Server structure, module map, request flow, startup/shutdown |
| 2 | [Threading model](threading-model.md) | Backend contributors | Async/sync boundaries, threadpool usage, rules for new code |
| 3 | [Worker API reference](api-reference.md) | Worker and integration developers | Worker API endpoints, protocol invariants, error shapes |
| 4 | [UI routes](ui-reference.md) | UI contributors | UI routes, view dispatch pipeline, htmx fragment dispatch, session/CSRF/auth |
| 5 | [Templates](templates.md) | UI contributors | Jinja2 environment, template catalog (page + fragment), context contracts |
| 6 | [Worker](worker.md) | Worker contributors | Worker architecture, task lifecycle, API usage |
| 7 | [Development](development.md) | All developers | Dev setup, validation workflows, vtjson rules, OpenAPI |
| 8 | [Deployment](deployment.md) | Operators | systemd, nginx, kernel tuning, capacity audit |
| 9 | [External references](references.md) | All developers | FastAPI, Starlette, Jinja2, htmx, Python, MongoDB, and tooling references |

## Quick start

```bash
# Install server dependencies (from repo root)
(cd server && uv sync --group test)

# Start the development server (from server/)
(cd server && FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000)
```

For OpenAPI docs, worker setup, local validation workflows, and vtjson
validation rules, see
[Development](development.md).

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Starlette (ASGI) |
| Application server | Uvicorn |
| Templates | Jinja2 (`.html.j2`, `StrictUndefined`) |
| Client interactivity | htmx 4.0.1 (CDN, fragment polling/swaps, OOB updates) |
| Session management | itsdangerous `TimestampSigner` cookie sessions |
| Database | MongoDB (pymongo) |
| Validation | vtjson (schema-first validation; no Pydantic) |
| Statistics | scipy, numpy (SPRT, ELO calculations) |
| Python (server) | >= 3.15 |
| Python (worker) | >= 3.8 |

## Project layout
```
fishtest/
|-- pyproject.toml             -- Root: dev tools (ruff, ty, pre-commit)
|-- uv.lock                    -- Locked dependency set for the root project
|-- .pre-commit-config.yaml    -- Pre-commit hooks (file checks, ruff, uv-lock)
|-- .github/workflows/         -- CI: lint, server tests, worker tests (POSIX + MSYS2)
|-- docs/                      -- Architecture and reference documentation
|-- server/
|   |-- pyproject.toml         -- Server package: runtime + test dependencies
|   |-- uv.lock                -- Locked dependency set for the server
|   |-- fishtest/              -- FastAPI application (Python >= 3.15)
|   |-- tests/                 -- Focused unit and HTTP contract tests
|   `-- utils/                 -- Operational utilities (backup, indexes, migration, analysis)
`-- worker/
    |-- pyproject.toml         -- Worker package: runtime dependencies (Python >= 3.8)
    |-- uv.lock                -- Locked dependency set for the worker
    |-- worker.py              -- Main worker script
    |-- games.py               -- Engine compilation, game execution
    |-- updater.py             -- Self-update mechanism
    |-- sri.txt                -- SRI hashes of the worker files
    |-- tests/                 -- Worker tests
    `-- packages/              -- Vendored packages
```

### Why three `pyproject.toml` files

The root `pyproject.toml` defines **development-only tools** (ruff, ty, pre-commit)
shared across the repo. The server and worker each have their own
`pyproject.toml` with independent dependency sets and Python version
constraints -- the server requires Python >= 3.15 while the worker supports
Python >= 3.8 to run on contributor machines with older distributions.

### Build system

Both the server and worker use **hatchling**, a standards-compliant PEP 517
build backend.

### Dependency management with uv

[uv](https://docs.astral.sh/uv/) is the package manager. The root, the
server and the worker are three independent projects, each with its own
`uv.lock`; run `uv` in the directory of the project it should change.

```bash
# Install the server's runtime and test dependencies
cd server && uv sync --group test

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

- **pre-commit-hooks** -- large file check, TOML and YAML validation (YAML
  with `--unsafe`), end-of-file fixer, trailing whitespace
- **ruff** -- lint with `--fix --exit-zero`, which applies the fixes it can and
  never fails the commit, and format
- **uv-lock** -- re-lock the root `uv.lock` when the root `pyproject.toml`
  changes; `server/uv.lock` and `worker/uv.lock` are not checked

Install with: `uv run pre-commit install`

### CI workflows

| Workflow | File | Trigger | What it does |
|----------|------|---------|-------------|
| Lint | `lint.yaml` | push, PR, manual | ruff check, import sort and format; Prettier check of the static CSS, HTML and JS; zizmor security audit of the workflows |
| Server | `server.yaml` | push, PR, manual | Server test suite (MongoDB required) |
| Worker POSIX | `worker_posix.yaml` | push, PR, manual | Worker tests on Linux/macOS |
| Worker MSYS2 | `worker_msys2.yaml` | push, PR, manual | Worker tests on Windows (MSYS2) |
