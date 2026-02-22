# Production Deployment

## Prerequisites

| Component | Minimum version | Purpose |
|-----------|-----------------|---------|
| Python | >= 3.14 | Runtime |
| MongoDB | mongod service | Data store |
| nginx | -- | Reverse proxy, TLS, static files |
| uv | -- | Python package manager |

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FISHTEST_PORT` | Yes | `-1` | Port for this instance |
| `FISHTEST_PRIMARY_PORT` | Yes | `-1` | Fixed primary port (typically 8000) |
| `FISHTEST_URL` | Dev: No; Prod: Yes | -- | Public URL (e.g., `https://tests.stockfishchess.org`); may be empty in development for dynamic host/IP |
| `FISHTEST_NN_URL` | Dev: No; Prod: Yes | -- | Neural network download base URL; may be empty in development to use same-host `/nn/` redirects |
| `FISHTEST_AUTHENTICATION_SECRET` | Yes | -- | Cookie signing secret (itsdangerous) |
| `FISHTEST_CAPTCHA_SECRET` | No | -- | reCAPTCHA secret key for signup |
| `FISHTEST_CAPTCHA_SITE_KEY` | No | built-in | reCAPTCHA site key for signup |
| `FISHTEST_INSECURE_DEV` | No | -- | Set to `1` for development mode (insecure secret) |
| `FISHTEST_JINJA_TEMPLATES_DIR` | No | auto | Override Jinja2 templates directory |
| `OPENAPI_URL` | No | (empty) | Set to `/openapi.json` to enable `/docs` and `/redoc` (development-only) |
| `UVICORN_WORKERS` | No | -- | Must be `1` on primary (enforced at startup) |
| `WEB_CONCURRENCY` | No | -- | Fallback for `UVICORN_WORKERS` (checked if unset) |

**Session invalidation**: deploying a new `FISHTEST_AUTHENTICATION_SECRET`
invalidates all existing sessions. Users must re-authenticate once.

### Primary instance detection

If `FISHTEST_PORT == FISHTEST_PRIMARY_PORT`, the instance is primary. If
either value is unset or negative, the instance defaults to primary for
backward compatibility.

## Primary / secondary instance model

| Instance | Port | Responsibilities |
|----------|------|------------------|
| Primary | 8000 | Scheduler, GitHub integration, aggregated data, cache flush, worker API |
| Secondary | 8001 | UI traffic (`/tests` homepage) |
| Secondary | 8002 | Read-only API, finished tests, contributors, static pages |
| Secondary | 8003 | PGN uploads (`/api/upload_pgn`) -- 3 Uvicorn workers (production override) |

Four systemd units (ports 8000-8003), six OS processes total. The primary
(8000) must be a single process (`UVICORN_WORKERS=1`) because it holds
in-process mutable state (run cache, scheduler, task locks). As a
single-core async process, the primary saturates at roughly 15,000
concurrent workers -- this is the practical scaling ceiling. Port 8003
runs 3 Uvicorn workers via a systemd drop-in override (see below); Uvicorn's
internal process manager distributes PGN upload requests across the workers.
The extra workers absorb the long-tail latency of large PGN writes
(p95 approx 30 s at peak load).

## Starting the server

Managed via a systemd service template (one unit per port):

```bash
sudo systemctl enable fishtest@{8000..8003}
sudo systemctl start fishtest@{8000..8003}
sudo journalctl -u fishtest@8000 # useful flags: -f, --since, --until, --no-pager
```

## systemd unit template

File: `/etc/systemd/system/fishtest@.service`

Copy the following file as-is. Replace `USER_NAME` with the actual user,
`SERVER_NAME` with the actual domain and `CHANGE_ME` with the
production cookie signing secret and the reCAPTCHA secret.

URL variables:

- **Development**: leave `FISHTEST_URL` and `FISHTEST_NN_URL` empty to allow
    dynamic host/IP usage behind nginx (useful for VM setups where the IP
    changes between boots).
- **Production**: set both to canonical HTTPS URLs so generated links and
    redirects are stable and externally correct.

```ini
[Unit]
Description=Fishtest Server port %i
After=network.target mongod.service

[Service]
Type=simple

Environment="UVICORN_WORKERS=1"
Environment="FISHTEST_URL=https://SERVER_NAME"
Environment="FISHTEST_NN_URL=https://data.stockfishchess.org"
# Cookie-session signing secret (required in production).
# Development-only insecure fallback requires explicit opt-in: Environment="FISHTEST_INSECURE_DEV=1"
Environment="FISHTEST_AUTHENTICATION_SECRET=CHANGE_ME"
Environment="FISHTEST_CAPTCHA_SECRET=CHANGE_ME"

# Port of *this* instance
Environment="FISHTEST_PORT=%i"
# Fixed primary port for the cluster
Environment="FISHTEST_PRIMARY_PORT=8000"

WorkingDirectory=/home/USER_NAME/fishtest/server
User=USER_NAME

# At 20k workers the primary needs ~15k fds; 32768 provides 2x headroom.
LimitNOFILE=32768

ExecStart=/home/USER_NAME/fishtest/server/.venv/bin/python -m uvicorn fishtest.app:app --host 127.0.0.1 --port %i --proxy-headers --forwarded-allow-ips=127.0.0.1 --backlog 16384 --log-level warning --workers $UVICORN_WORKERS
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### PGN upload worker override

In production, port 8003 handles PGN uploads which have long-tail latency.
Running 3 Uvicorn workers on this port prevents slow uploads from blocking
fast ones. Create a per-instance drop-in override:

```bash
sudo mkdir -p /etc/systemd/system/fishtest@8003.service.d
```

Create the file
`/etc/systemd/system/fishtest@8003.service.d/override.conf`:

```ini
[Service]
Environment="UVICORN_WORKERS=3"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart fishtest@{8000..8003}
```

### Uvicorn flags

**`--backlog 16384`** -- Sets the kernel TCP listen queue size. This absorbs
connection bursts from large worker fleets without dropping connections.
The value must exceed the peak burst arrival rate during restarts (when
all backed-off workers reconnect simultaneously).

**Do NOT use `--limit-concurrency`.** This flag rejects connections beyond
the specified limit with HTTP 503 (plain text "Service Unavailable").
Workers receiving this non-JSON response trigger a `JSONDecodeError` and
enter exponential backoff (15 s -> 900 s), effectively removing themselves
from the active pool. Under Uvicorn's ASGI async model, connection
acceptance is handled by the event loop and costs negligible resources per
idle connection. Application-level throttling (`task_semaphore(5)` +
`request_task_lock` in `rundb.py`) governs the critical scheduling path.
There is no need for an HTTP-layer concurrency cap.

**OpenAPI docs** (`/docs`, `/redoc`, `/openapi.json`) are disabled in
production (`openapi_url` defaults to `None`). Set `OPENAPI_URL=/openapi.json`
in the environment to re-enable during development.

## nginx configuration

The nginx setup uses two configuration files:

1. **`/etc/nginx/conf.d/default.conf`** -- catch-all server that handles
   HTTP->HTTPS redirects and rejects TLS handshakes for unrecognized
   hostnames. This prevents certificate leaks when multiple vhosts share
   one IP address.

2. **`/etc/nginx/sites-available/fishtest.conf`** -- the named fishtest
   vhost with upstream routing, static file serving, and reverse proxy.

### Default server configuration

File: `/etc/nginx/conf.d/default.conf`

This file replaces the stock nginx `default.conf`. It owns the
`default_server` designation for both ports 80 and 443, handling
infrastructure concerns (redirects, monitoring, and unknown-hostname
rejection) so that named vhosts stay focused on application routing.

```nginx
# --- HTTP catch-all ---
server {
    listen      80 default_server backlog=16384;
    listen [::]:80 default_server backlog=16384;
    server_name _;

    server_tokens off;

    # Monitoring (localhost only)
    location = /nginx_status {
        stub_status  on;
        allow        127.0.0.1;
        allow        ::1;
        deny         all;
    }

    # Everything else -> HTTPS (permanent redirect, preserves method)
    location / {
        return 308 https://$host$request_uri;
    }
}

# --- HTTPS catch-all: reject unknown SNI ---
server {
    listen      443 ssl default_server backlog=16384;
    listen [::]:443 ssl default_server backlog=16384;
    http2       on;
    server_name _;

    # Reject the TLS handshake for unrecognized hostnames.
    # No certificate is sent -- the client sees a connection reset.
    # Requires nginx >= 1.19.4.
    ssl_reject_handshake on;
}
```

`backlog=16384` on the `default_server` listen directives sets the kernel TCP
listen queue for the shared socket. All server blocks on the same address:port
inherit this socket parameter. The value matches the Uvicorn `--backlog` and
absorbs thundering-herd reconnection bursts from large worker fleets.

### Site configuration

File: `/etc/nginx/sites-available/fishtest.conf`

Copy the following file as-is. Replace every occurrence of `SERVER_NAME` with
the actual domain name (e.g. `tests.stockfishchess.org`) and `CDN_HOSTNAME`
with the Cloudflare-proxied CDN hostname (e.g. `data.stockfishchess.org`).
Omit `CDN_HOSTNAME` from the `server_name` directive if no CDN is used.
Adjust Let's Encrypt certificate paths if needed.

```nginx
upstream backend_8000 {
    server 127.0.0.1:8000;
    keepalive           256;
    keepalive_requests  10000;
    keepalive_timeout   60s;
}

upstream backend_8001 {
    server 127.0.0.1:8001;
    keepalive           256;
    keepalive_requests  10000;
    keepalive_timeout   60s;
}

upstream backend_8002 {
    server 127.0.0.1:8002;
    keepalive           256;
    keepalive_requests  10000;
    keepalive_timeout   60s;
}

upstream backend_8003 {
    server 127.0.0.1:8003;
    keepalive           256;
    keepalive_requests  10000;
    keepalive_timeout   60s;
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
    listen      443 ssl;
    listen [::]:443 ssl;
    http2          on;
    server_tokens  off;

    server_name SERVER_NAME CDN_HOSTNAME;

    # TLS certificates (Let's Encrypt)
    ssl_certificate      /etc/letsencrypt/live/SERVER_NAME/fullchain.pem;
    ssl_certificate_key  /etc/letsencrypt/live/SERVER_NAME/privkey.pem;
    include              /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam          /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header Strict-Transport-Security  "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options     "nosniff" always;
    add_header X-Frame-Options            "SAMEORIGIN" always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy         "camera=(), microphone=(), geolocation=()" always;

    # block bad actors at the server level (early access phase)
    # deny  xxx.xxx.xxx.xxx;

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

The named vhost does **not** use `default_server` -- that designation belongs
exclusively to the catch-all in `default.conf`. This separation ensures
correct SNI-based certificate selection when multiple vhosts share one IP
on both IPv4 and IPv6.

### Neural network CDN (`CDN_HOSTNAME`)

In production `CDN_HOSTNAME` is `data.stockfishchess.org`, a
Cloudflare-proxied alias that points back to this origin server.
Cloudflare caches the immutable net files at the edge, reducing
origin bandwidth.

`CDN_HOSTNAME` must appear in the `server_name` directive so that
nginx accepts the TLS handshake when Cloudflare connects to the
origin. Without it, the catch-all in `default.conf` rejects the
unknown SNI and Cloudflare returns error 525 to workers.

The Let's Encrypt certificate covers only `SERVER_NAME`, not
`CDN_HOSTNAME`. This works because Cloudflare SSL mode "Full"
(not strict) validates the TLS connection without checking the
certificate hostname. If the Cloudflare zone is later switched to
"Full (Strict)", the certificate must be expanded to include both
hostnames (requires Cloudflare dashboard access for DNS-01
validation or an Origin CA certificate).

### Maintenance mode configuration

File: `/etc/nginx/sites-available/fishtest-maintenance.conf`

During planned maintenance (major upgrades, database migrations), swap the
active site symlink so that all requests receive a friendly 503 maintenance
page while static assets (logos, icons) remain available. The procedure:

```bash
sudo ln -sfn /etc/nginx/sites-available/fishtest-maintenance.conf /etc/nginx/sites-enabled/fishtest.conf
sudo nginx -t && sudo systemctl reload nginx
```

To restore normal operation:

```bash
sudo ln -sfn /etc/nginx/sites-available/fishtest.conf /etc/nginx/sites-enabled/fishtest.conf
sudo nginx -t && sudo systemctl reload nginx
```

Copy the following file as-is. Replace every occurrence of `SERVER_NAME` with
the actual domain name. Security headers and TLS settings match the production
vhost exactly.

```nginx
server {
    listen      443 ssl;
    listen [::]:443 ssl;
    http2          on;
    server_tokens  off;

    server_name SERVER_NAME;

    # TLS certificates (Let's Encrypt)
    ssl_certificate      /etc/letsencrypt/live/SERVER_NAME/fullchain.pem;
    ssl_certificate_key  /etc/letsencrypt/live/SERVER_NAME/privkey.pem;
    include              /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam          /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header Strict-Transport-Security  "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options     "nosniff" always;
    add_header X-Frame-Options            "SAMEORIGIN" always;
    add_header Referrer-Policy            "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy         "camera=(), microphone=(), geolocation=()" always;

    # Static assets remain available during maintenance
    location ^~ /img/ {
        root        /var/www/fishtest/static;
        try_files   $uri =404;
        access_log  off;
        expires     1y;
        add_header  Cache-Control "public, max-age=31536000, immutable";
    }

    location ^~ /static/ {
        alias       /var/www/fishtest/static/;
        try_files   $uri =404;
        access_log  off;
        expires     1y;
        add_header  Cache-Control "public, max-age=31536000, immutable";
    }

    location = /favicon.ico {
        alias       /var/www/fishtest/static/favicon.ico;
        access_log  off;
        expires     1y;
        add_header  Cache-Control "public, max-age=31536000, immutable";
    }

    location = /robots.txt {
        alias       /var/www/fishtest/static/robots.txt;
        access_log  off;
    }

    # Everything else -> maintenance page (HTTP 503)
    error_page 503 @maintenance;

    location / {
        return 503;
    }

    location @maintenance {
        root            /var/www/fishtest/static/html;
        rewrite ^(.*)$  /maintenance.html break;
    }
}
```

No port 80 block is needed -- `default.conf` already redirects all HTTP
traffic to HTTPS regardless of hostname.

### nginx worker tuning

The following directives belong in `/etc/nginx/nginx.conf` (not in the
site config). They raise the per-worker fd limit and connection capacity
for high worker counts:

```nginx
user  www-data;
worker_processes  2;

error_log  /var/log/nginx/error.log notice;
pid        /run/nginx.pid;
include    /etc/nginx/modules-enabled/*.conf;

# must exceed worker_connections (32768); 40k allows headroom for connections + misc
worker_rlimit_nofile  40000;

events {
    # total capacity = worker_connections * worker_processes = 65536
    # at 20k workers each process handles ~20k connections (client + upstream)
    worker_connections  32768;

    # efficiently handle multiple new connections at once
    multi_accept        on;
    use                 epoll;
}

http {
    include            /etc/nginx/mime.types;
    default_type       application/octet-stream;

    log_format  main   '$remote_addr - $remote_user [$time_local] "$request" '
                       '$status $body_bytes_sent "$http_referer" '
                       '"$http_user_agent" "$http_x_forwarded_for" $upstream_response_time';

    access_log         /var/log/nginx/access.log  main;

    sendfile           on;
    tcp_nopush         on; # combined headers into one packet
    tcp_nodelay        on; # good for small API bursts

    keepalive_timeout  65;

    gzip               on;
    gzip_vary          on;
    gzip_min_length    256;
    gzip_comp_level    5;
    gzip_types         text/plain text/css application/json application/javascript text/xml;
    gzip_proxied       any;  # compress responses from upstream python backends

    include            /etc/nginx/conf.d/*.conf;
    include            /etc/nginx/sites-enabled/*.conf;
}
```

At 20,000 workers each nginx worker process handles approximately 10,000
client connections plus 10,000 upstream proxy connections (~20,000 total).
`worker_connections 32768` provides 1.6x headroom per worker.

`keepalive 256` sets the maximum number of idle keepalive connections
retained per upstream block. At 9,400 workers the sustained request rate
is ~150 req/s with most requests completing in <100 ms. The value 256
is generous for localhost backends but harmless -- idle TCP connections
consume negligible memory.

### nginx proxy timeout rationale

Proxy timeouts are set aggressively low to fail fast on unresponsive
backends rather than accumulating stale connections:

| Directive | Value | Rationale |
|-----------|-------|----------|
| `proxy_connect_timeout` | 2 s | Backend connect should succeed in < 1 ms (localhost) |
| `proxy_send_timeout` | 30 s | Request bodies (PGN uploads) rarely exceed 10 s |
| `proxy_read_timeout` | 60 s | Accommodates slow DB queries and streaming PGN downloads |

## Kernel tuning (sysctl)

For the 20,000-worker target, verify the following `sysctl` values.
Add to `/etc/sysctl.d/99-fishtest.conf` if needed:

```ini
# fishtest production tuning (target: 20,000 workers)

# must be >= uvicorn --backlog (16384); 32768 absorbs thundering-herd reconnections
net.core.somaxconn = 32768
net.core.netdev_max_backlog = 32768
net.ipv4.tcp_max_syn_backlog = 32768

# 20k client + 20k upstream + mongodb + misc approx 45k peak; 120k provides ~2.5x headroom
fs.file-max = 120000

# each proxied request consumes an ephemeral port; default range (~28k) is too narrow
net.ipv4.ip_local_port_range = 1024 65535

# fast socket recycling under high connection churn
net.ipv4.tcp_tw_reuse = 1

# handle high-frequency socket churn from 20k workers; prevents 'time wait bucket table overflow'
net.ipv4.tcp_max_tw_buckets = 65536
```

Apply with `sudo sysctl --system`.

`net.core.somaxconn` must be >= the Uvicorn `--backlog` value (16384).
Otherwise the kernel silently truncates the listen queue. The value 32768
provides 2x headroom and absorbs a full thundering-herd reconnection burst.

## User limits

systemd `LimitNOFILE` only applies to services started by systemd. For
interactive sessions (SSH maintenance, cron jobs), set PAM limits so the
USER_NAME user inherits the same file-descriptor ceiling:

```bash
sudo mkdir -p /etc/security/limits.d
```

File: `/etc/security/limits.d/99-fishtest.conf`

```ini
# interactive fd ceiling for the USER_NAME user.
# soft (8192) covers SSH maintenance; hard (32768) matches systemd LimitNOFILE.
USER_NAME         soft    nofile          8192
USER_NAME         hard    nofile          32768
```

## Capacity audit script

Run on the production host to verify that kernel, nginx, and process
limits are correctly sized for the 20,000-worker target:

```bash
#!/usr/bin/env bash
# fishtest capacity audit -- verify system tuning for the 20,000-worker target.
# Run on the production host after applying sysctl, nginx, and systemd settings.

set -euo pipefail

readonly target=20000
readonly expected_nofile=32768
readonly expected_backlog=16384
readonly expected_tw=65536
readonly red=$'\033[0;31m'
readonly ylw=$'\033[0;33m'
readonly grn=$'\033[0;32m'
readonly rst=$'\033[0m'

pass() { echo "${grn}pass${rst} ($1)"; }
warn() { echo "${ylw}WARN${rst} ($1)"; }
fail() { echo "${red}FAIL${rst} ($1)"; }

echo "fishtest capacity audit (target: ${target} workers)"
echo "----------------------------------------------------"

# kernel: somaxconn must be >= uvicorn --backlog
printf "  %-25s " "somaxconn:"
somax=$(cat /proc/sys/net/core/somaxconn)
[[ "${somax}" -ge "${expected_backlog}" ]] \
    && pass "${somax} >= ${expected_backlog}" \
    || fail "${somax} < ${expected_backlog}"

# kernel: tw_buckets must handle high connection churn
printf "  %-25s " "tcp_max_tw_buckets:"
tw_buckets=$(cat /proc/sys/net/ipv4/tcp_max_tw_buckets)
[[ "${tw_buckets}" -ge "${expected_tw}" ]] \
    && pass "${tw_buckets} >= ${expected_tw}" \
    || fail "${tw_buckets} < ${expected_tw}"

# kernel: ephemeral port range (need ~40k for proxied connections + headroom)
printf "  %-25s " "ephemeral ports:"
read -r port_low port_high < /proc/sys/net/ipv4/ip_local_port_range
range=$((port_high - port_low))
[[ "${range}" -ge 40000 ]] \
    && pass "${range} (${port_low}-${port_high})" \
    || fail "${range} too narrow"

# nginx: total capacity must handle client + upstream connections
printf "  %-25s " "nginx capacity:"
w_proc=$(grep -E '^\s*worker_processes' /etc/nginx/nginx.conf \
    | awk '{print $2}' | tr -d ';')
[[ "${w_proc}" == "auto" ]] && w_proc=$(nproc)
w_conn=$(grep -E '^\s*worker_connections' /etc/nginx/nginx.conf \
    | awk '{print $2}' | tr -d ';')
total=$((w_proc * w_conn))
need=$((target * 2))
[[ "${total}" -ge "${need}" ]] \
    && pass "${total} >= ${need}" \
    || fail "${total} < ${need}"

# listen backlogs (nginx front door + each uvicorn port)
echo "  listen backlogs (>= ${expected_backlog}):"
for port in 443 8000 8001 8002 8003; do
    printf "    port %-18s " "${port}:"
    bl=$(ss -ltn | awk -v p=":${port}" '$4 ~ p {print $3}' | sort -rn | head -1)
    [[ -n "${bl:-}" && "${bl}" -ge "${expected_backlog}" ]] \
        && pass "${bl}" \
        || fail "${bl:-not listening}"
done

# per-process file-descriptor limits
echo "  fd limits (>= ${expected_nofile}):"
for port in 8000 8001 8002 8003; do
    printf "    port %-18s " "${port}:"
    pid=$(pgrep -f "port ${port}" | head -1 || true)
    if [[ -z "${pid}" ]]; then
        fail "no process"
        continue
    fi
    lim=$(awk '/Max open files/ {print $4}' "/proc/${pid}/limits")
    [[ "${lim}" -ge "${expected_nofile}" ]] \
        && pass "${lim}" \
        || fail "${lim} < ${expected_nofile}"
done

# mongodb: fd limit for data files + connections
printf "  %-25s " "mongodb fd limit:"
mongo_pid=$(pgrep -x mongod || true)
if [[ -n "${mongo_pid}" ]]; then
    mongo_fd=$(awk '/Max open files/ {print $4}' "/proc/${mongo_pid}/limits")
    [[ "${mongo_fd}" -ge 4096 ]] \
        && pass "${mongo_fd} >= 4096" \
        || fail "${mongo_fd} < 4096"
else
    fail "mongod not running"
fi

# mongodb: active connections vs pool capacity
printf "  %-25s " "mongo active conns:"
if command -v mongosh &>/dev/null; then
    curr_conns=$(mongosh --quiet --eval "db.serverStatus().connections.current")
    [[ "${curr_conns}" -lt 2048 ]] \
        && pass "${curr_conns}" \
        || warn "${curr_conns} (approaching pool limit)"
else
    fail "mongosh not found"
fi

# disk: I/O wait (high values signal MongoDB or PGN write pressure)
printf "  %-25s " "disk iowait:"
if command -v iostat &>/dev/null; then
    iowait=$(iostat -c 1 2 | awk '/^ / {v=$4} END {print v}')
    if awk "BEGIN {exit !(${iowait} < 5.0)}"; then
        pass "${iowait}%"
    else
        warn "${iowait}% (high)"
    fi
else
    fail "iostat not found (install sysstat)"
fi

echo "----------------------------------------------------"
```
