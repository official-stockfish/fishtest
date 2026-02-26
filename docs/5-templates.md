# Jinja2 Templates

## Environment configuration

| Setting | Value |
|---------|-------|
| Templates directory | `server/fishtest/templates/` |
| File extension | `.html.j2` |
| Autoescape | Enabled for HTML, XML, and `.j2` files |
| Undefined behavior | `StrictUndefined` (missing variables raise errors) |
| Extensions | `jinja2.ext.do` |
| Instance | Single `Environment` created at import time in `http/jinja.py` |

Custom filters and global functions are registered via `http/template_helpers.py`
and `http/jinja.py`.

### Custom filters

| Filter | Description |
|--------|-------------|
| `urlencode` | URL-encodes a value (`quote_plus`) |
| `split` | Splits a string (`str.split`) |
| `string` | Converts to string (`str()`) |

### Global functions

| Global | Source | Description |
|--------|--------|-------------|
| `static_url(path)` | `http/jinja.py` | Static asset URL with cache-buster token |
| `diff_url(...)` | `util.py` | GitHub diff URL builder |
| `format_bounds(...)` | `util.py` | SPRT bounds formatter |
| `format_date(dt)` | `util.py` | Date formatter |
| `format_group(groups)` | `util.py` | User group label formatter |
| `format_results(...)` | `util.py` | Game results formatter |
| `format_time_ago(dt)` | `util.py` | Relative time formatter |
| `display_residual(r)` | `util.py` | Chi-squared residual display |
| `is_active_sprt_ltc(run)` | `util.py` | Checks if run is active SPRT LTC |
| `is_elo_pentanomial_run(run)` | `template_helpers.py` | Checks pentanomial display |
| `nelo_pentanomial_summary(...)` | `template_helpers.py` | Pentanomial ELO summary (returns `Markup`) |
| `results_pre_attrs(...)` | `template_helpers.py` | HTML attributes for results display (returns `Markup`) |
| `run_tables_prefix(username)` | `template_helpers.py` | Toggle prefix for run tables |
| `tests_run_setup(...)` | `template_helpers.py` | Test form default values |
| `tests_repo(run)` | `util.py` | Extract tests repo URL from run |
| `worker_name(info)` | `util.py` | Format worker name from info dict |
| `list_to_string(values, decimals)` | `template_helpers.py` | Formats a list of floats as a string |
| `pdf_to_string(...)` | `template_helpers.py` | Formats a probability density function |
| `t_conf(...)` | `template_helpers.py` | Confidence interval formatting |
| `fishtest` | `fishtest` package | Package module (version, metadata) |
| `gh` | `github_api.py` | GitHub API module (commit_url, etc.) |
| `math`, `datetime`, `copy`, `urllib`, `float` | Python stdlib | Standard library access |

## Rendering flow

1. The view handler returns a `(template_name, context_dict)` pair (via
   `_dispatch_view`'s `renderer` config).
2. `_dispatch_view()` calls `render_template_to_response()`.
3. `build_template_context()` in `http/boundary.py` constructs the shared
   base context (CSRF token, current user, flash messages, navigation URLs).
4. The handler-specific context is merged with the base context.
5. `Jinja2Templates.TemplateResponse(request, name, context)` renders the
   template and returns an HTML response.
6. Rendering is synchronous and executes in the threadpool.

## Shared base context

Every template receives these keys from `build_template_context()`:

| Key | Type | Description |
|-----|------|-------------|
| `request` | `Request` | Starlette request object (for `url_for`) |
| `csrf_token` | string | CSRF token for forms and meta tags |
| `current_user` | `{"username": str}` or `None` | Authenticated user |
| `theme` | string | `"dark"`, `"light"`, or empty (from cookie) |
| `pending_users_count` | int | Badge count for user management |
| `static_url` | callable | `static_url(path)` function |
| `flash` | dict | `{"error": [...], "warning": [...], "info": [...]}` |
| `urls` | dict | Navigation URLs (see below) |

### Navigation URLs (`urls` dict)

```python
{
    "home": "/",
    "login": "/login",
    "logout": "/logout",
    "signup": "/signup",
    "user_profile": "/user",
    "tests": "/tests",
    "tests_finished_ltc": "/tests/finished?ltc_only=1",
    "tests_finished_success": "/tests/finished?success_only=1",
    "tests_finished_yellow": "/tests/finished?yellow_only=1",
    "tests_run": "/tests/run",
    "tests_user_prefix": "/tests/user/",
    "tests_machines": "/tests/machines",
    "nn_upload": "/upload",
    "nns": "/nns",
    "contributors": "/contributors",
    "contributors_monthly": "/contributors/monthly",
    "actions": "/actions",
    "user_management": "/user_management",
    "workers_blocked": "/workers/show",
    "sprt_calc": "/sprt_calc",
    "rate_limits": "/rate_limits",
    "api_rate_limit": "/api/rate_limit",
}
```

## Template catalog

| Template | Purpose |
|----------|---------|
| `base.html.j2` | Base layout (navbar, footer, asset loading) |
| `actions.html.j2` | Paginated action log |
| `contributors.html.j2` | Contributor leaderboard (all-time and monthly) |
| `elo_results.html.j2` | ELO result display (included as partial) |
| `login.html.j2` | Login form |
| `machines_fragment.html.j2` | Connected worker machines table fragment |
| `nn_upload.html.j2` | Neural network upload form |
| `nns.html.j2` | Neural network listing with pagination |
| `notfound.html.j2` | 404 error page |
| `pagination.html.j2` | Reusable pagination partial |
| `rate_limits.html.j2` | API rate limit information page |
| `run_table.html.j2` | Single run table partial |
| `run_tables.html.j2` | Run listing container (pending/active/finished) |
| `signup.html.j2` | User registration form |
| `sprt_calc.html.j2` | SPRT calculator page |
| `tasks_fragment.html.j2` | Task table fragment for a run |
| `tests.html.j2` | Main tests dashboard |
| `tests_finished.html.j2` | Finished tests listing with filters |
| `tests_live_elo.html.j2` | Live ELO chart page |
| `tests_run.html.j2` | New test / rerun submission form |
| `tests_stats.html.j2` | Statistical analysis page |
| `tests_user.html.j2` | Per-user test listing |
| `tests_view.html.j2` | Single test detail page |
| `user.html.j2` | User profile page |
| `user_management.html.j2` | User administration page |
| `workers.html.j2` | Worker blocking administration page |

## Context contracts

Each template has an explicit context contract documenting the required keys.
Templates do not fetch data; views provide fully shaped context.

### `base.html.j2`

Uses shared base context only. All other templates extend this.

### `actions.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `actions` | list of dicts | Action rows (see below) |
| `filters` | dict | `{action, username, text, run_id}` |
| `usernames` | list of strings | For the search datalist |
| `pages` | list | Pagination items |

Each action row:

| Key | Type |
|-----|------|
| `time_label` | string (preformatted) |
| `time_url` | string |
| `event` | string |
| `agent_name` | string |
| `agent_url` | string or None |
| `target_name` | string |
| `target_url` | string or None |
| `message` | string |

### `contributors.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `is_monthly` | bool | Monthly vs all-time view |
| `is_approver` | bool | Current user is approver |
| `summary` | dict | `{testers, developers, active_testers, cpu_years, games, tests}` |
| `users` | list of dicts | Contributor rows |

Each contributor row: `username`, `last_updated_label`, `last_updated_sort`,
`games_per_hour`, `cpu_hours`, `games`, `tests`, `tests_repo`, `tests_repo_url`,
`tests_user_url`.

### `elo_results.html.j2`

Included as a partial within run display templates.

| Key | Type | Description |
|-----|------|-------------|
| `elo` | dict | ELO display context |

The `elo` dict contains: `info_lines`, `pre_attrs`, `show_gauge`, `chart_div_id`,
`nelo_summary_html`, `live_elo_url`, `is_sprt`.

### `login.html.j2`

Shared base context only.

### `machines_fragment.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `machines` | list of dicts | Machine rows |

Each machine row: `username`, `country_code`, `concurrency`, `worker_url`,
`worker_short`, `nps_m` (preformatted string), `max_memory`, `system`,
`worker_arch`, `compiler_label`, `python_label`, `version_label`, `run_url`,
`run_label`, `last_active_label`, `last_active_sort`.

### `nn_upload.html.j2`

| Key | Type |
|-----|------|
| `upload_url` | string |
| `testing_guidelines_url` | string |
| `cc0_url` | string |
| `nn_stats_url` | string |

### `nns.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `filters` | dict | `{network_name, user, master_only}` |
| `pages` | list | Pagination items |
| `nns` | list of dicts | Neural network rows |

Each nn row: `time_label`, `name`, `name_url`, `user`, `first_test_label`,
`first_test_url`, `last_test_label`, `last_test_url`, `downloads`, `is_master`.

### `notfound.html.j2`

Shared base context only.

### `pagination.html.j2`

Reusable partial included by other templates.

| Key | Type | Description |
|-----|------|-------------|
| `pages` | list of dicts | Each: `{idx, url, state}` |

`state` values: `"active"`, `"disabled"`, or empty string.

### `rate_limits.html.j2`

Shared base context only.

### `run_table.html.j2`

| Key | Type |
|-----|------|
| `header` | string or None |
| `count` | int or None |
| `runs` | list of run row dicts |
| `pages` | list of pagination items |
| `toggle` | string or None |
| `toggle_state` | `"Hide"` or `"Show"` |
| `show_delete` | bool |

### `run_tables.html.j2`

| Key | Type |
|-----|------|
| `page_idx` | int |
| `prefix` | string |
| `pending_approval_runs` | list of run rows |
| `paused_runs` | list of run rows |
| `failed_runs` | list of run rows |
| `active_runs` | list of run rows |
| `finished_runs` | list of run rows |
| `num_finished_runs` | int |
| `finished_runs_pages` | list |

### `signup.html.j2`

| Key | Type |
|-----|------|
| `recaptcha_site_key` | string |

### `sprt_calc.html.j2`

Shared base context only.

### `tasks_fragment.html.j2`

| Key | Type |
|-----|------|
| `tasks` | list of task row dicts |
| `show_pentanomial` | bool |
| `show_residual` | bool |

Each task row: `task_id`, `row_class`, `worker_label`, `worker_url`,
`info_label`, `last_updated_label`, `played_label`, `results_cells`,
`crashes`, `time_losses`, `residual_label`, `residual_bg`.

### `tests.html.j2`

| Key | Type |
|-----|------|
| `page_idx` | int |
| `cores` | int |
| `nps_m` | string |
| `games_per_minute` | string |
| `pending_hours` | string |
| `machines_shown` | bool |
| `machines_count` | int |
| `run_tables_ctx` | dict (for `run_tables.html.j2`) |

### `tests_finished.html.j2`

| Key | Type |
|-----|------|
| `filters` | dict (`ltc_only`, `success_only`, `yellow_only`) |
| `title_suffix` | string |
| `finished_runs` | list of run rows |
| `num_finished_runs` | int |
| `finished_runs_pages` | list |

### `tests_live_elo.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `page_title` | string |

### `tests_run.html.j2`

| Key | Type |
|-----|------|
| `args` | dict (run arguments, empty for new test) |
| `is_rerun` | bool |
| `rescheduled_from` | string or None |
| `form_action` | string |
| `tests_repo_value` | string |
| `master_info` | dict or None |
| `valid_books` | iterable |
| `pt_info` | dict |
| `setup` | dict |
| `supported_arches` | list |
| `supported_compilers` | list |

### `tests_stats.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `page_title` | string |
| `stats` | dict |

### `tests_user.html.j2`

| Key | Type |
|-----|------|
| `username` | string |
| `is_approver` | bool |
| `run_tables_ctx` | dict |

### `tests_view.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `run_args` | list of tuples `(name, value, url)` |
| `page_title` | string |
| `approver` | bool |
| `chi2` | value |
| `totals` | string (active workers summary) |
| `tasks_shown` | bool |
| `show_task` | int |
| `follow` | int |
| `can_modify_run` | bool |
| `same_user` | bool |
| `pt_info` | dict |
| `document_size` | int |
| `spsa_data` | dict or None |
| `notes` | list of strings |
| `warnings` | list of strings |
| `use_3dot_diff` | bool |
| `allow_github_api_calls` | bool |

### `user.html.j2`

| Key | Type |
|-----|------|
| `profile` | bool |
| `user` | dict (`username`, `email`, `tests_repo`, etc.) |
| `limit` | value |
| `hours` | int |
| `extract_repo_from_link` | string |
| `form_action` | URL |
| `registration_time_label` | string |
| `blocked` | bool |

### `user_management.html.j2`

| Key | Type |
|-----|------|
| `all_users` | list of user row dicts |
| `pending_users` | list |
| `blocked_users` | list |
| `idle_users` | list |
| `approvers_users` | list |

Each user row: `username`, `user_url`, `registration_label`, `groups`,
`groups_label`, `email`.

### `workers.html.j2`

| Key | Type |
|-----|------|
| `show_admin` | bool |
| `worker_name` | string |
| `last_updated_label` | string |
| `message` | string |
| `blocked` | bool |
| `show_email` | bool |
| `blocked_workers` | list of dicts |

Each blocked worker row: `worker_name`, `last_updated_label`, `actions_url`,
`owner_email`, `mailto_url`.

## Authoring rules

1. **Templates are declarative**: all data shaping stays in view handlers.
   Templates receive pre-computed values and render them.

2. **JavaScript data**: pass via the `|tojson` filter. Never interpolate
   Python values directly into `<script>` blocks.

3. **Display strings**: prefer preformatted values (e.g., `*_label` keys)
   over formatting in templates.

4. **URLs**: prefer explicit URL keys (e.g., `*_url`) over building URLs in
   templates.

5. **Macros**: use Jinja2 macros for repeated patterns (pagination, run
   tables).

6. **Request object**: not used directly in templates except via `url_for`
   and `static_url` helpers.

7. **Escaping boundary**: view handlers pass raw strings. Jinja2 autoescape
   handles HTML-escaping at render time. Do not pre-escape values into plain
   strings with `html.escape()` in Python -- that causes double-escaping.
   Escaping in Python is appropriate when constructing a `Markup` value
   (escape untrusted input first, then wrap).

8. **`|safe` filter**: use only on values already typed as `Markup`, or
   after an explicit `|e` escape followed by controlled transformations
   (e.g., `{{ value | e | replace("\n", "<br>") | safe }}`).

9. **External links**: every `target="_blank"` anchor must include
   `rel="noopener noreferrer"` to prevent reverse-tabnabbing.

10. **No inline event handlers**: use unobtrusive JavaScript (`addEventListener`
    or delegated listeners) instead of `onclick`, `onsubmit`, or similar HTML
    attributes.

## Adding a new template

1. Create `templates/mypage.html.j2` extending `base.html.j2`:
   ```jinja
   {% extends "base.html.j2" %}
   {% block content %}
   ...
   {% endblock %}
   ```

2. Define the context contract (required keys and types) in this document.

3. Build the context in the view handler using the shared base context plus
   page-specific keys.

4. Return the context dict from the handler; `_dispatch_view` renders the
   template specified in the route config's `renderer` key.

5. Add a test that verifies the template renders without errors.
