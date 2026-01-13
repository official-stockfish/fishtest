# Worker API Reference

## Protocol invariants

These invariants apply to every worker API endpoint:

- Every response is a JSON object.
- Authenticated endpoints include a `duration` field (float, seconds elapsed
  server-side).
- Application errors return **HTTP 200** with `{"error": "...", "duration": N}`.
- Transport/validation errors return non-200 with a JSON error payload that
  also includes `duration`.
- Content-Type is always `application/json`.
- The current worker protocol version is defined by `WORKER_VERSION` in
  `api.py` (currently 311).

## Authentication

Workers authenticate via `username` and `password` fields in the
`worker_info` section of every POST body. Credentials are validated against
`UserDb.authenticate()`.

- Invalid credentials -> HTTP 200 + `{"error": "Invalid password ..."}`.
- Missing or malformed JSON -> HTTP 400 + `{"error": "..."}`.

## Worker API paths

The following 9 endpoints are considered **worker API paths**. On non-primary
instances, these return HTTP 503 (except `/api/upload_pgn`, which is routed
to a dedicated backend):

```
/api/request_version
/api/request_task
/api/update_task
/api/beat
/api/request_spsa
/api/failed_task
/api/stop_run
/api/upload_pgn
/api/worker_log
```

## Authenticated endpoints

### POST /api/request_version

**Purpose**: Returns the current worker protocol version. Workers call this
to check if they need to upgrade.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string" }
}
```

**Response**:
```json
{ "version": 311, "duration": 0.001 }
```

---

### POST /api/request_task

**Purpose**: Requests a testing task assignment from the server.

**Request body**:
```json
{
  "password": "string",
  "worker_info": {
    "username": "string",
    "unique_key": "string",
    "concurrency": 4,
    ...system specs...
  }
}
```

**Success response**:
```json
{
  "run": {
    "_id": "run_id",
    "args": { ...run arguments... },
    "my_task": { "num_games": 200, "start": 0 }
  },
  "task_id": 0,
  "duration": 0.05
}
```

**No work available**:
```json
{ "task_waiting": false, "duration": 0.01 }
```

---

### POST /api/update_task

**Purpose**: Reports partial or final game results for an assigned task.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0,
  "stats": { "wins": 10, "losses": 5, "draws": 15, "pentanomial": [0, 2, 8, 2, 0] }
}
```

**Response**:
```json
{ "duration": 0.02 }
```

---

### POST /api/beat

**Purpose**: Heartbeat -- keeps the task lease alive. Workers send this
periodically to prevent the server from reclaiming the task.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0
}
```

**Response**:
```json
{ "task_alive": true, "duration": 0.001 }
```

---

### POST /api/request_spsa

**Purpose**: Requests SPSA tuning parameters for the current iteration.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0
}
```

**Response**:
```json
{
  "w_params": [...],
  "b_params": [...],
  "duration": 0.01
}
```

---

### POST /api/failed_task

**Purpose**: Marks a task as failed (worker-side crash, timeout, or error).

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0,
  "message": "optional error description"
}
```

**Response**:
```json
{ "duration": 0.01 }
```

---

### POST /api/stop_run

**Purpose**: Requests early termination of a run (e.g., SPRT bounds reached).
Requires the user to have at least 1000 CPU hours.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0,
  "message": "optional reason"
}
```

**Response**:
```json
{ "duration": 0.01 }
```

---

### POST /api/upload_pgn

**Purpose**: Uploads gzip-compressed PGN game records for a completed task.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "run_id": "string",
  "task_id": 0,
  "pgn": "base64-encoded gzip data"
}
```

**Response**:
```json
{ "duration": 0.05 }
```

**Note**: This endpoint is routed to a non-primary backend (port 8003) for
single-instance handling. It is excluded from `PRIMARY_ONLY_WORKER_API_PATHS`.

---

### POST /api/worker_log

**Purpose**: Logs a worker-side diagnostic message on the server's action log.

**Request body**:
```json
{
  "password": "string",
  "worker_info": { "username": "string", "unique_key": "string" },
  "message": "log message string"
}
```

**Response**:
```json
{ "duration": 0.001 }
```

## CORS support

Two endpoints respond to CORS preflight requests:

| Endpoint | Purpose |
|----------|--------|
| `OPTIONS /api/actions` | Preflight for cross-origin action queries |
| `OPTIONS /api/get_run/{id}` | Preflight for cross-origin run data access |

Both return `Access-Control-Allow-Origin: *` and
`Access-Control-Allow-Headers: Content-Type`.

## Read-only endpoints (no authentication)

These endpoints do not require worker authentication. They serve data to the
web UI, external tools, and API consumers.

### GET /api/active_runs

Returns all unfinished runs as a JSON object keyed by run ID. Tasks and
heavy fields are excluded from the projection.

### GET /api/finished_runs

Returns paginated finished runs. Query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int (required) | Page number (1-based) |
| `username` | string | Filter by submitter |
| `success_only` | bool | Only successful runs |
| `yellow_only` | bool | Only inconclusive runs |
| `ltc_only` | bool | Only long time control runs |
| `timestamp` | string | UNIX timestamp filter |

### POST /api/actions

Returns up to 200 recent actions matching the JSON query body. Supports CORS
(preflight via `OPTIONS /api/actions`).

### GET /api/get_run/{id}

Returns a single run document (with tasks stripped of sensitive fields).
Supports CORS.

### GET /api/get_task/{id}/{task_id}

Returns a single task document. The `unique_key` is truncated and
`remote_addr` is masked for privacy.

### GET /api/get_elo/{id}

Returns SPRT ELO analysis for a run.

### GET /api/calc_elo

Computes ELO from provided W/D/L or pentanomial counts. Query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `W`, `D`, `L` | int | Win/Draw/Loss counts (trinomial) |
| `LL`, `LD`, `DDWL`, `WD`, `WW` | int | Pentanomial counts |
| `elo0`, `elo1` | float | SPRT bounds (optional) |
| `elo_model` | string | `BayesElo`, `logistic`, or `normalized` |

### GET /api/nn/{id}

Redirects to the neural network download URL (`FISHTEST_NN_URL`). Increments
the download counter.

### GET /api/pgn/{id}

Downloads a gzip-compressed PGN file for a specific run/task. Returns a
`StreamingResponse` with `Content-Encoding: gzip`.

### GET /api/run_pgns/{id}

Downloads all PGN files for a run as a single gzip archive. Filename must
match `{run_id}.pgn.gz`.

### GET /api/rate_limit

Returns GitHub API rate limit information.

## Validation

Request bodies are validated against vtjson schemas defined in `schemas.py`:

- `api_access_schema` -- validates the authentication fields (`username`,
  `password`, `worker_info`).
- `api_schema` -- validates the full request body structure for worker
  endpoints.
- `gzip_data` -- validates that uploaded PGN data is valid gzip.

Schema validation failures produce HTTP 400 responses.

## Error shape

All error responses from worker API endpoints follow this shape:

```json
{
  "error": "/api/endpoint_path: error message",
  "duration": 0.001
}
```

The error string is prefixed with the endpoint path for client-side
disambiguation.

## Adding a new API endpoint

1. Add the route in `api.py` with `@router.post(...)` or `@router.get(...)`.
2. Write the handler as an `async def` that constructs the appropriate
   `WorkerApi` or `UserApi` shim and offloads the handler body via
   `run_in_threadpool`.
3. Return a dict containing `"duration"` (use `GenericApi.add_time()`).
4. For application errors, use `GenericApi.handle_error()` which raises
   `HTTPException` with a dict detail payload.
5. Add a vtjson schema in `schemas.py` if the endpoint accepts structured
   input.
6. Add a contract test in `tests/test_api.py`.
7. If the endpoint requires worker authentication, add its path to
   `WORKER_API_PATHS` in `api.py`.
