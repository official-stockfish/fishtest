# Contributing to Fishtest

Thank you for your interest in contributing to Fishtest! This guide covers
the development workflow and coding standards for the project.

## Getting Started

### Prerequisites

| Component | Minimum Version  | Purpose          |
|-----------|------------------|------------------|
| Python    | >= 3.14          | Server runtime   |
| Python    | >= 3.8           | Worker runtime   |
| [MongoDB](https://www.mongodb.com/docs/manual/administration/install-community/) | `mongod` service | Data store       |
| [uv](https://docs.astral.sh/uv/) | latest | Package manager |

### Local Setup

```bash
# Clone the repository
git clone https://github.com/official-stockfish/fishtest.git
cd fishtest

# Install development dependencies (pre-commit, ruff, ty)
uv sync

# Install server dependencies
cd server && uv sync && uv sync --group test && cd ..

# Install pre-commit hooks
uv run pre-commit install
```

### Running the Development Server

```bash
cd server
FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000
```

Setting `FISHTEST_INSECURE_DEV=1` enables an insecure fallback secret key
for cookie signing. This must **never** be used in production.

### Running Tests

```bash
mkdir -p .local/mongo-data
mongod --dbpath .local/mongo-data --fork --logpath .local/mongod.log
pushd server && uv run python3 -m unittest discover -s tests -v
popd && mongod --shutdown --dbpath .local/mongo-data
```

## Coding Style

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Format and lint with [Ruff](https://docs.astral.sh/ruff/):

```bash
uv run ruff format
uv run ruff check --select I --fix
uv run ruff check
```

### CSS, HTML, JavaScript

- Follow the [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html)
  and the [Google JavaScript Style Guide](https://google.github.io/styleguide/jsguide.html).
- Format with [Prettier](https://prettier.io/):

```bash
npx prettier --write 'server/fishtest/static/{css/*.css,html/*.html,js/*.js}'
```

### Pre-commit Hooks

The repository uses [pre-commit](https://pre-commit.com/) hooks to automate
formatting and linting on every commit. The hooks are configured in
`.pre-commit-config.yaml` and include:

- Trailing whitespace removal
- End-of-file fixer
- TOML/YAML validation
- Ruff formatting and linting
- `uv.lock` sync check

Run hooks manually on all files:

```bash
uv run pre-commit run --all-files
```

To temporarily skip hooks during a commit:

```bash
git commit --no-verify -m "message"
```

## Submitting Changes

1. **Open an issue first** — describe what you plan to change and wait for
   feedback from a maintainer before writing code.
2. **Fork the repository** and create a feature branch from `master`.
3. **Keep PRs small and focused** — one logical change per pull request.
4. **Run the full pre-commit suite** before pushing.
5. **Write tests** for new server functionality (the project uses `unittest`
   with `httpx` for HTTP tests).
6. **Write a clear PR description** linking to the related issue.
7. **Respond to review feedback** promptly.

## Project Structure

```
fishtest/
├── server/
│   ├── fishtest/           # Server application
│   │   ├── app.py          # FastAPI application entry point
│   │   ├── views.py        # Route handlers
│   │   ├── api.py          # Worker API endpoints
│   │   ├── rundb.py        # Test run database layer
│   │   ├── templates/      # Jinja2 templates (.html.j2)
│   │   └── static/         # CSS, JS, images
│   └── tests/              # Server test suite
├── worker/                 # Distributed worker client
├── docs/                   # Architecture & deployment docs
└── pyproject.toml          # Root project config
```

## Additional Resources

- [Development Guide](docs/7-development.md) — environment variables, nginx
  config, and multi-instance testing.
- [Architecture Overview](docs/1-architecture.md) — server design and
  threading model.
- [API Reference](docs/3-api-reference.md) — worker API endpoints.
- [Wiki Contributing Page](https://github.com/official-stockfish/fishtest/wiki/Contributing-to-Fishtest) - development environment setup, coding styles, development wrokflow.
- [Coding Style Guide (Issue #634)](https://github.com/official-stockfish/fishtest/issues/634)
  — original style discussion.
