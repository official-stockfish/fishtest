# Development Guide

## Prerequisites

| Component | Minimum version | Purpose |
|-----------|-----------------|---------|
| Python | >= 3.14 | Server Runtime |
| Python | >= 3.8 | Worker Runtime |
| MongoDB | mongod service | Data store |
| uv | -- | Python package manager |

nginx is not required for single-instance development. For multi-instance
local testing, see the [nginx development config](#nginx-development-config)
section below.

## Installation

```bash
cd server && uv sync && uv sync --group test
```

This installs all runtime and test dependencies into a virtual environment at
`server/.venv`.

## Running the development server

```bash
cd server
FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000
```

No concurrency flags are needed in development. The async event loop handles
concurrent requests natively.

Setting `FISHTEST_INSECURE_DEV=1` enables an insecure fallback secret key
for cookie signing. This must never be used in production.

### Running the worker with the development server

The worker must authenticate against `/api/request_version`, so the username
must exist in the local MongoDB and must not be `pending` or `blocked`.

After starting the server with the command above, run the worker in a second
terminal:

```bash
cd worker
uv run worker.py USERNAME PASSWORD --protocol http --host 127.0.0.1 --port 8000
```

### OpenAPI documentation

To enable the interactive OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`)
during development:

```bash
OPENAPI_URL=/openapi.json FISHTEST_INSECURE_DEV=1 uv run uvicorn fishtest.app:app --reload --port 8000
```

OpenAPI docs are disabled in production (`openapi_url` defaults to `None`,
which prevents FastAPI from registering the `/openapi.json`, `/docs`, and
`/redoc` routes). Setting `OPENAPI_URL=/openapi.json` re-enables them and
exposes the full API and UI route schema in the Swagger UI.

## Environment variables

The full environment variables table is in [8-deployment.md](8-deployment.md).
The following subset is relevant during development:

| Variable | Default | Description |
|----------|---------|-------------|
| `FISHTEST_INSECURE_DEV` | -- | Set to `1` to use insecure fallback signing secret |
| `OPENAPI_URL` | (empty) | Set to `/openapi.json` to enable `/docs` and `/redoc` |
| `FISHTEST_PORT` | `-1` | Defaults to primary when unset |
| `FISHTEST_PRIMARY_PORT` | `-1` | Defaults to primary when unset |
| `FISHTEST_JINJA_TEMPLATES_DIR` | auto | Override Jinja2 templates directory |

When `FISHTEST_PORT` and `FISHTEST_PRIMARY_PORT` are both unset or negative,
the instance defaults to primary -- the expected mode for single-instance
development.

## Running tests

```bash
cd server && uv run python -m unittest discover -s tests -q
```

See [0-README.md](0-README.md) for pre-commit hooks and CI workflows.

## nginx development config

For local multi-instance testing with nginx, use the development-only HTTP
config below. This mirrors the production routing topology without TLS and
works on local VMs where the IP may change between boots. Leave
`FISHTEST_URL` and `FISHTEST_NN_URL` empty in the systemd units to allow
dynamic host/IP usage.

File: `/etc/nginx/sites-available/fishtest.conf`

```nginx
upstream backend_8000 {
    server 127.0.0.1:8000;
    keepalive 256;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

upstream backend_8001 {
    server 127.0.0.1:8001;
    keepalive 256;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

upstream backend_8002 {
    server 127.0.0.1:8002;
    keepalive 256;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

upstream backend_8003 {
    server 127.0.0.1:8003;
    keepalive 256;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

map $uri $backends {
    /tests                                 backend_8001;
    ~^/api/(actions|active_runs|calc_elo)  backend_8002;
    ~^/api/(nn|pgn|run_pgns)/              backend_8002;
    ~^/api/upload_pgn                      backend_8003;
    ~^/tests/(finished|machines|user)      backend_8002;
    ~^/(actions/|contributors)             backend_8002;
    ~^/(api|tests)/                        backend_8000;
    default                                backend_8001;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    server_tokens off;

    location = /nginx_status {
        stub_status  on;
        allow        127.0.0.1;
        allow        ::1;
        deny         all;
    }

    location = /        { return 308 /tests; }
    location = /tests/  { return 308 /tests; }

    location = /robots.txt {
        alias       /var/www/fishtest/static/robots.txt;
        access_log  off;
    }

    location = /favicon.ico {
        alias       /var/www/fishtest/static/favicon.ico;
        access_log  off;
        expires     1y;
        add_header  Cache-Control "public, max-age=31536000, immutable";
    }

    location ^~ /static/ {
        alias       /var/www/fishtest/static/;
        try_files   $uri =404;
        access_log  off;
        etag        on;
        expires     1y;
        add_header  Cache-Control "public, max-age=31536000, immutable";
    }

    location /nn/ {
        root         /var/www/fishtest;
        gzip_static  always;
        gunzip       on;
    }

    location / {
        # Canonical upstream identity
        proxy_set_header Host               $http_host;
        proxy_set_header X-Real-IP          $remote_addr;

        # Forwarded chain
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
        proxy_set_header X-Forwarded-Host   $host;
        proxy_set_header X-Forwarded-Port   $server_port;
        proxy_set_header Connection         "";

        # Custom metadata
        proxy_set_header X-Country-Code     $region;

        # Timeouts
        proxy_connect_timeout    2s;
        proxy_send_timeout       30s;
        proxy_read_timeout       60s;

        # Buffering
        proxy_request_buffering  on;
        proxy_buffering          on;
        proxy_next_upstream      off;

        client_max_body_size     200m;
        client_body_buffer_size  512k;

        proxy_redirect           off;
        proxy_http_version       1.1;

        # Decompression
        gunzip                   on;

        proxy_pass http://$backends;
    }
}
```
