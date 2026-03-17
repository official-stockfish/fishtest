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
| `poll` | `http/jinja.py` | Shared htmx polling intervals exposed to templates |
| `htmx` | `http/jinja.py` | Shared htmx timing defaults exposed to templates |
| `cookies` | `http/jinja.py` | Shared cookie max-age values for page scripts/templates |
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
| `pending_users_count` | int | Pending-user count used by the sidebar `Users` link |
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
   "tests_finished": "/tests/finished",
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

### Shared sidebar status links

- `base.html.j2` includes `pending_users_nav_fragment.html.j2` inside a stable
   htmx poll wrapper. The wrapper owns the `load` and `every` triggers, while
   the fragment owns only the rendered anchor HTML.
- `base.html.j2` renders the sidebar `GitHub Rate Limits` anchor directly.
   `static/js/application.js` updates that link, not a server fragment
   endpoint, because the browser-side GitHub token lives in local storage and
   is not part of server session state.
- `rate_limits.html.j2` exposes the same browser-side client poll cadence via
   `data-poll-seconds` on `#client_rate_limit`, so the page row and the sidebar
   link read the same client limit state.

## Client-side behavior pattern

Behavior-heavy page scripts should prefer static assets plus `data-*`
configuration over large inline `<script>` blocks.

Current examples:

- `contributors.html.j2` -> `static/js/contributors.js`
- `tests.html.j2` -> `static/js/tests_homepage.js`
- `user.html.j2` (profile mode) -> `static/js/user_profile.js`

`tests_homepage.js` owns the homepage Workers panel cookie state and triggers
an immediate `machines:load` refresh whenever Bootstrap reports that the panel
has been opened.

Shared behavior that spans multiple pages belongs in shared assets instead of
page-local inline scripts. Search/filter inputs remain plain
`<input type="search">` controls, and any shared behavior or styling should
live in shared assets instead of page-local inline scripts.

This keeps templates focused on structure and server-provided state, aligns with
MDN separation-of-concerns guidance, and makes the JS contract testable without
embedding implementation details in the template body.

## Sortable table accessibility baseline

Seven content-fragment templates define inline `sort_header` Jinja2 macros for
sortable data tables. All sortable tables must satisfy:

1. **`scope="col"`** on every `<th>` in `<thead>` (including non-sortable
   column headers like the `#` row number). Helps assistive technologies
   associate headers with data cells.
2. **`<caption class="visually-hidden">`** as the first child of each
   `<table>`. Provides a programmatic name for the table so screen readers
   can announce it before reading cells.
3. **`class="sticky-top"`** on `<thead>` so column headers remain visible when
   scrolling long tables.
4. **`aria-sort`** only on the currently active sort column header. Values:
   `ascending` or `descending`.
5. **`aria-hidden="true"`** on the decorative sort-indicator icon span.

Templates that follow this contract:

| Template | Table ID | Caption text |
|----------|----------|-------------|
| `actions_content_fragment.html.j2` | `actions_table` | Events log results |
| `contributors_content_fragment.html.j2` | `contributors_table` | Contributors |
| `machines_fragment.html.j2` | `machines_table` | Machines |
| `nns_content_fragment.html.j2` | `nns_table` | Neural networks |
| `tasks_content_fragment.html.j2` | `tasks_table` | Tasks |
| `user_management_content_fragment.html.j2` | `user_management_table` | User management |
| `workers_content_fragment.html.j2` | `workers_table` | Workers |

Regression tests in `test_http_boundary.py` enforce `scope="col"`,
`visually-hidden` caption, and `sticky-top` on `<thead>` for all seven
templates.

### Filter and cookie consistency

The seven sortable tables split into two architectural patterns that
determine their filter form and state-persistence behavior:

| Pattern | Pages | Filters | Cookie persistence | Polling |
|---------|-------|---------|-------------------|---------|
| **A** (standalone) | contributors, actions, workers, user_management, nns | `form-control` (full-size) | 0-1 client-side cookies | none |
| **B** (embedded panel) | machines, tasks | `form-control-sm` | 4-6 server-side cookies | 60 s |

Design rules:

- **No custom width overrides** on filter inputs. Let `col-md-auto` size
  fields naturally across all standalone pages.
- This rule also applies to `/tests/finished?mode=search`: its username and
   free-text controls should size through the shared grid layout, not through a
   page-specific CSS minimum width.
- **`autocomplete="off"`** on all search/filter text inputs to prevent
  browser autofill from interfering with htmx-driven filtering.
- **Cookie max-age** must use `PERSISTENT_UI_COOKIE_MAX_AGE_SECONDS` from
  `settings.py`, never hardcoded values. Client-side cookies set via
  `hx-on::before-request` handlers use the Jinja variable
  `{{ cookie_max_age }}` backed by this constant.

Known gaps documented for future iterations:

- Workers and user_management have zero cookie persistence for filter/sort
  state (user resets to defaults on page reload).
- Contributors has one client-side cookie (`monthly/all-time` toggle) but no
  filter-state cookies.

## Template catalog

### Page templates (extend `base.html.j2`)

| Template | Purpose |
|----------|---------|
| `base.html.j2` | Base layout (navbar, footer, asset loading, htmx CDN, pending-user nav poll target) |
| `actions.html.j2` | Paginated action log |
| `contributors.html.j2` | Contributor leaderboard (all-time and monthly) |
| `elo_results.html.j2` | ELO result display (included as partial) |
| `login.html.j2` | Login form |
| `nn_upload.html.j2` | Neural network upload form |
| `nns.html.j2` | Neural network listing with pagination |
| `notfound.html.j2` | 404 error page |
| `pagination.html.j2` | Reusable pagination partial |
| `rate_limits.html.j2` | API rate limit information page |
| `run_table.html.j2` | Single run table partial |
| `run_tables.html.j2` | Run listing container (pending/active/finished) |
| `signup.html.j2` | User registration form |
| `sprt_calc.html.j2` | SPRT calculator page |
| `tests.html.j2` | Main tests dashboard |
| `tests_finished.html.j2` | Finished tests listing with filters |
| `tests_live_elo.html.j2` | Live ELO chart page |
| `tests_run.html.j2` | New test / rerun submission form |
| `tests_stats.html.j2` | Raw statistics page shell with visibility-aware poller |
| `tests_user.html.j2` | Per-user test listing |
| `tests_view.html.j2` | Single test detail page |
| `user.html.j2` | User profile page |
| `user_management.html.j2` | User administration page |
| `workers.html.j2` | Worker blocking administration page |

### Fragment templates (standalone, no `base.html.j2`)

Fragment templates serve htmx partial responses. They do not extend the
base layout and contain only the HTML subset needed for the swap target.

| Template | Swap target | OOB | Polled |
|----------|------------|-----|--------|
| `actions_content_fragment.html.j2` | `#actions-content` | -- | -- |
| `actions_page_fragment.html.j2` | `#actions-page` | -- | -- |
| `active_run_filters_fragment.html.j2` | `#active-run-filters` | -- | -- |
| `contributors_content_fragment.html.j2` | `#contributors-content` | Yes (hidden input sync) | -- |
| `contributors_rows_fragment.html.j2` | included by `contributors_content_fragment.html.j2` | -- | -- |
| `elo_batch_fragment.html.j2` | none (OOB only) | Yes | Yes |
| `elo_results_fragment.html.j2` | none (OOB only) | Yes | Yes |
| `homepage_stats_fragment.html.j2` | none (OOB only) | Yes | -- |
| `live_elo_fragment.html.j2` | none (OOB only) | Yes | Yes |
| `machines_fragment.html.j2` | `#machines` | Yes (`#workers-count`) | Yes |
| `nns_content_fragment.html.j2` | `#nns-content` | -- | -- |
| `pending_users_nav_fragment.html.j2` | `#pending-users-nav` | -- | Yes |
| `run_table_row_fragment.html.j2` | `#run-{id}` (row swap) | -- | -- |
| `tasks_content_fragment.html.j2` | `#tasks-content` | Yes (`#tasks-view-controls`, `#tasks-pagination`, hidden input sync) | Yes |
| `tasks_controls_fragment.html.j2` | included by `tests_view.html.j2` and OOB by `tasks_content_fragment.html.j2` | -- | -- |
| `tasks_rows_fragment.html.j2` | included by `tasks_content_fragment.html.j2` | -- | -- |
| `tests_filter_tabs_fragment.html.j2` | caller-defined `hx-target` | -- | -- |
| `tests_finished_content_fragment.html.j2` | full-page shell include | -- | -- |
| `tests_finished_results_fragment.html.j2` | `#tests-finished-content` | Yes (tab wrapper in navigation mode) | -- |
| `tests_stats_content_fragment.html.j2` | `#tests-stats-content` | -- | Yes |
| `tests_user_content_fragment.html.j2` | `#tests-user-content` | -- | -- |
| `user_management_content_fragment.html.j2` | `#user-management-content` | Yes (hidden input sync) | -- |
| `user_management_rows_fragment.html.j2` | included by `user_management_content_fragment.html.j2` | -- | -- |
| `workers_content_fragment.html.j2` | `#workers-content` | Yes (hidden input sync) | -- |
| `workers_rows_fragment.html.j2` | included by `workers_content_fragment.html.j2` | -- | -- |

Column notes:
- **OOB**: template contains `hx-swap-oob` attributes that update additional
  DOM elements beyond the primary swap target.
- **Polled**: template is fetched on a timer via `hx-trigger="every Ns"`.

## Context contracts

Each template has an explicit context contract documenting the required keys.
Templates do not fetch data; views provide fully shaped context.

### `base.html.j2`

Uses shared base context only. All other templates extend this.

### `actions.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `actions` | list of dicts | Action rows (see below) |
| `visible_actions` | int | Action rows rendered on the current page |
| `num_actions` | int | Total matching action count |
| `page_size` | int | Page size used for the current result set |
| `current_page` | int | 1-based page index rendered in the summary |
| `run_id_filter` | string | Active run filter, if the page is scoped to one run |
| `max_count` | int or None | Effective server-side action cap carried through GET forms |
| `sort` | string | Active sort field (`time`, `event`, `source`, `target`, `comment`) |
| `order` | string | Active sort direction (`asc` or `desc`) |
| `sort_summary` | string | Optional summary line describing capped full-result sorting scope |
| `filters` | dict | `{action, username, text, run_id}` |
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
| `users` | list of dicts | Contributor rows (current page) |
| `pages` | list | Pagination items |
| `search` | string | Active search query |
| `sort` | string | Active server sort field |
| `order` | string | Active sort direction |
| `view` | string | `paged` or `all` |
| `highlight` | string | Highlighted username, usually set by `findme` redirects |
| `is_truncated` | bool | Whether `view=all` was capped |
| `num_users` | int | Total filtered row count before paging/cap |
| `max_all` | int | Hard cap used for `view=all` |

Each contributor row: `username`, `user_url`, `rank`, `percentile`, `cpu_pct`,
`last_updated_label`, `last_updated_sort`, `games_per_hour`, `cpu_hours`,
`games`, `tests`, `tests_repo_url`, `tests_user_url`.

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

Behavior notes:

- The fragment refreshes the `#workers-count` label out of band with the same
   short format used by the homepage shell: `Workers - <total>` or
   `Workers - <total> (<filtered>)`.
- Homepage polling keeps including the current filter form state, so fragment
   refreshes continue while the `q` search filter is active.
- The hidden homepage Workers header is refreshed from the current machine
  snapshot during `/tests` and `/tests/elo_batch` rendering, so a collapsed
  panel still shows a live filtered count.

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

Behavior notes:

- Search is URL-driven and rendered by the same `/nns` endpoint.
- htmx search updates only `#nns-content`; full-page rendering still works.
- Typing in `network_name` / `user` and toggling `master_only` triggers
   htmx requests, while submit remains available as a non-JS fallback.
- `network_name` and `user` are literal case-insensitive substring filters;
   regex metacharacters are escaped before reaching Mongo.
- The page shell owns the heading and filter form; the summary cards,
  explanatory copy, view toggle, pagination, and table live in the content
  fragment.

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
| `count_text` | string or None |
| `runs` | list of run row dicts |
| `pages` | list of pagination items |
| `toggle` | string or None |
| `toggle_state` | `"Hide"` or `"Show"` |
| `show_delete` | bool |
| `active_run_filters` | dict or None |

### `run_tables.html.j2`

| Key | Type |
|-----|------|
| `page_idx` | int |
| `prefix` | string |
| `pending_approval_runs` | list of run rows |
| `paused_runs` | list of run rows |
| `failed_runs` | list of run rows |
| `active_runs` | list of run rows |
| `active_count_text` | string |
| `active_run_filters` | dict or None |
| `finished_runs` | list of run rows |
| `num_finished_runs` | int |
| `finished_runs_pages` | list |

### `signup.html.j2`

| Key | Type |
|-----|------|
| `recaptcha_site_key` | string |

### `sprt_calc.html.j2`

Shared base context only.

### `tasks_content_fragment.html.j2`

| Key | Type |
|-----|------|
| `tasks` | list of task row dicts |
| `show_pentanomial` | bool |
| `show_residual` | bool |
| `run_id` | string |
| `show_task` | int |
| `sort` | string (default `"idx"`) |
| `order` | string (`"asc"` or `"desc"`, default `"desc"`) |
| `q` | string (combined worker/info filter) |
| `view` | string (`"paged"` or `"all"`) |
| `pages` | list of pagination dicts |
| `num_tasks` | int |
| `max_all` | int |
| `is_truncated` | bool |

Primary swap target: `#tasks-content`.

The fragment swaps the scrolling task table body into `#tasks-content` and
refreshes the fixed controls/pagination wrappers out of band. OOB updates
target `#tasks-view-controls`, `#tasks-pagination`, and the hidden form inputs
`#tasks_sort`, `#tasks_order`, and `#tasks_view`.

Each task row: `task_id`, `row_class`, `worker_label`, `worker_url`,
`info_label`, `last_updated_label`, `played_label`, `results_cells`,
`crashes`, `time_losses`, `residual_label`, `residual_bg`.

### `tasks_controls_fragment.html.j2`

Included by `tests_view.html.j2` for the page-owned tasks table shell and
returned OOB by `tasks_content_fragment.html.j2` after sort, filter, or view
changes.

| Key | Type |
|-----|------|
| `run_id` | string |
| `show_task` | int |
| `sort` | string |
| `order` | string |
| `q` | string |
| `view` | string |
| `num_tasks` | int |
| `max_all` | int |
| `is_truncated` | bool |

### `tasks_rows_fragment.html.j2`

Included by `tasks_content_fragment.html.j2`. Renders `<tr>` rows from
the `tasks` list. No standalone context requirements beyond `tasks`,
`show_pentanomial`, and `show_residual`.

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

Behavior notes:

- `tests.html.j2` forwards the homepage Active-panel first-paint filter state
   through `run_tables_ctx`, including restored checkbox selections, filtered
   count text, and initial hide selectors.
- Notification button state is not part of `run_tables_ctx` because it is
   derived from browser-local follow state at page load time.

### `tests_finished.html.j2`

| Key | Type |
|-----|------|
| `filters` | dict (`ltc_only`, `success_only`, `yellow_only`) |
| `title_suffix` | string |
| `finished_runs` | list of run rows |
| `visible_finished_runs` | int |
| `num_finished_runs` | int |
| `finished_runs_pages` | list |

### `tests_live_elo.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `page_title` | string |
| `run_status_label` | string |
| `sprt_state` | string |
| `elo_raw`, `ci_lower_raw`, `ci_upper_raw` | float |
| `LLR_raw`, `LOS_raw`, `a_raw`, `b_raw` | float |
| `elo_value`, `ci_lower`, `ci_upper`, `LLR`, `LOS` | number |
| `W`, `L`, `D`, `games` | int |
| `w_pct`, `l_pct`, `d_pct` | float |
| `pentanomial` | list |
| `elo_model`, `elo0`, `elo1`, `alpha`, `beta` | mixed |

The page script renders LOS, LLR, and Elo gauges from `gauge-data` attributes.
The Elo gauge supports a fixed default range (`[-4, +4]`) and a dynamic range.
The gauge reports the uncapped server Elo value while the needle remains
visually bounded by the active range.

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

Rendered structure notes:

- the preset chooser caption for `Test type` is a neutral heading row, not a
   `label` wrapper;
- the ellipsis control is a sibling button that toggles the extra preset blocks
   through Bootstrap collapse;
- the collapsed preset blocks expose stable ids so the toggle button can name
   them through `aria-controls`.

### `tests_stats.html.j2`

Page shell for `/tests/stats/{id}`. Includes the shared stats content fragment and,
for unfinished non-SPSA runs, a visibility-aware htmx poller targeting
`#tests-stats-content` using the dedicated raw-statistics poll cadence
`poll.stats_detail`.

| Key | Type |
|-----|------|
| `run` | dict |
| `page_title` | string |
| `stats` | dict |

### `tests_stats_content_fragment.html.j2`

Shared stats-body fragment used by both the full-page shell and `HX-Request`
responses for `/tests/stats/{id}`.

| Key | Type |
|-----|------|
| `run` | dict |
| `page_title` | string |
| `stats` | dict |

Rendered structure:

- `#tests-stats-content` root element
- original heading-and-table statistics layout shared by full-page and htmx renders
- SPRT bounds rendered as a table
- SPSA message rendered in place of the statistics tables when applicable

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

Detail-page ELO polling contract:

- Unfinished runs render a visibility-aware htmx poller targeting
   `/tests/elo/{id}?expected=<status>`.
- The `expected` query param must match the page's current run status label:
   `active`, `paused`, or `pending`.
- The page-level `_status` Jinja expression is the canonical source for both
   the visible status label and the poller's expected state.

Detail-page tasks loader contract:

- When `tasks_shown` is true, `#tasks-body` starts an htmx load request from
   `tests_view.html.j2`.
- The template attaches the `htmx:afterSwap` and error listeners for
   `#tasks-body` before `await DOMContentLoaded()` so the initial `load` request
   cannot outrun the promise-resolution path.
- The same script also resolves immediately if `#tasks-body` is already marked
   loaded or already contains rows.

Run-table row contract:

- Run tables use the normal `.table-striped` contract.
- Active-run filtering emits a first-paint style block that hides excluded
   rows, and the Active filter script keeps the visible rows contiguous in tbody
   order so the normal `.table-striped` pattern stays correct while filters are
   active. The first-paint style block is hide-only and does not encode row
   parity.
- The Active row markup carries filter dimensions plus a source-order index for
   restoring the current server order after checkbox changes and OOB swaps; it
   does not use a row-parity contract.

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
| `all_count` | int |
| `pending_count` | int |
| `blocked_count` | int |
| `idle_count` | int |
| `approvers_count` | int |
| `group` | string |
| `sort` | string |
| `order` | string |
| `q` | string |
| `view` | string |
| `pages` | list |
| `users` | list of user row dicts |
| `num_selected_users` | int |
| `max_all` | int |
| `is_truncated` | bool |

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
| `filter_value` | string |
| `sort` | string |
| `order` | string |
| `q` | string |
| `view` | string |
| `pages` | list |
| `blocked_workers` | list of dicts |
| `num_workers` | int |
| `max_all` | int |
| `is_truncated` | bool |

Each blocked worker row: `worker_name`, `last_updated_label`, `actions_url`,
`owner_email`, `mailto_url`.

## Fragment context contracts

Fragment templates receive the shared base context (via
`build_template_context()`) plus handler-specific keys.

### `actions_content_fragment.html.j2`

Same context as `actions.html.j2` (`actions`, `visible_actions`, `num_actions`, `page_size`,
`current_page`, `run_id_filter`, `max_count`, `sort`, `order`,
`sort_summary`, `filters`, `pages`).

### `actions_page_fragment.html.j2`

Same context as `actions.html.j2`. This fragment owns the filter form,
the `#actions-content` include, and the search-first `/actions` form that owns
the debounced username and free-text filters. The username filter is
substring-based; the view resolves matching usernames before running the exact
action query so the debounced form stays fast on large logs. The free-text help
control is a labeled button that opens the Bootstrap modal, so the icon trigger
is keyboard-focusable and announced as a button.

### `active_run_filters_fragment.html.j2`

| Key | Type |
|-----|------|
| `active_runs` | list (run dicts for the Active panel) |
| `active_run_filters` | dict or `None` (parsed cookie state) |
| `cookies.persistent_ui_max_age` | int (cookie max-age seconds) |

Renders the faceted filter panel (SPRT/SPSA/NumGames, STC/LTC, ST/SMP)
above the Active runs table. Server-side rendering of initial checkbox
state eliminates the flash where all rows are briefly visible before JS
reapplies the persisted filter. The template only renders when
`active_runs` is non-empty.

### `contributors_content_fragment.html.j2`

Same context as the content area of `contributors.html.j2`: `users`, `pages`,
`sort`, `order`, `view`, `num_users`, `max_all`, `is_truncated`.

Sortable headers are dual-mode links (`href` + `hx-get`) targeting
`#contributors-content` with `hx-push-url="true"`.

The outer contributors search form keeps `view`, `sort`, and `order` in hidden
inputs. htmx fragment responses refresh those inputs out of band so later form
submissions preserve the live table state.

### `contributors_rows_fragment.html.j2`

| Key | Type |
|-----|------|
| `users` | list of contributor row dicts |

### `elo_batch_fragment.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `panels` | list of dicts | Each: `tbody_id`, `rows`, `show_delete` |
| `count_updates` | list of dicts | Each: `id`, `text` (OOB count spans) |
| `machines` | list of dicts | Machine rows (OOB `#workers-count`) |
| `stats` | dict or absent | Homepage stats (OOB, omitted when filtered by user) |

Behavior notes:

- When homepage workers filters are active, the fragment recomputes the
   `#workers-count` filtered value from the current machine snapshot instead of
   trusting the last cookie-backed filtered count.
- `workers_count_text` remains the single shared workers-counter string used by
   the homepage shell and OOB fragment updates.

### `elo_results_fragment.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `elo` | dict (same as `elo_results.html.j2`) |
| `_status` | string (OOB `#run-status-{id}`) |
| `tasks_totals` | string (OOB `#tasks-totals`) |

### `homepage_stats_fragment.html.j2`

| Key | Type |
|-----|------|
| `cores` | int |
| `nps_m` | string |
| `games_per_minute` | string |
| `pending_hours` | string |

### `live_elo_fragment.html.j2`

| Key | Type |
|-----|------|
| `run` | dict |
| `run_status_label` | string |
| `sprt_state` | string |
| `elo_raw`, `ci_lower_raw`, `ci_upper_raw` | float |
| `LLR_raw`, `LOS_raw`, `a_raw`, `b_raw` | float |
| `elo_value`, `ci_lower`, `ci_upper`, `LLR`, `LOS` | number |
| `W`, `L`, `D`, `games` | int |
| `w_pct`, `l_pct`, `d_pct` | float |
| `pentanomial` | list |
| `elo_model`, `elo0`, `elo1`, `alpha`, `beta` | mixed |

This fragment is returned by `/tests/live_elo_update/{id}` and swaps
`#live-elo-data` out-of-band while preserving the current client-side gauge mode.

### `machines_fragment.html.j2`

| Key | Type |
|-----|------|
| `machines` | list of machine row dicts |
| `sort` | string |
| `order` | string |
| `q` | string |
| `current_page` | int |
| `my_workers` | bool |
| `pages` | list |
| `machines_count` | int |
| `workers_count_text` | string (OOB `#workers-count`) |

This fragment also refreshes the hidden sort/page inputs and the `#workers-count`
label out of band so homepage polling, sorting, paging, and filters stay in
sync without replacing the filter controls themselves.

The machine rows come from the current server machine snapshot. The same
snapshot is reused by `/tests` and `/tests/elo_batch` when they need to render a
live filtered workers count while the table itself is collapsed.

### `nns_content_fragment.html.j2`

Same context as `nns.html.j2` (`filters`, `pages`, `nns`, `sort`, `order`,
`view`, `num_nns`, `max_all`, `is_truncated`) plus `nns_summary` with
`nets`, `master_nets`, `contributors`, and `downloads`.

The fragment owns the NNS summary cards and the explanatory copy as well as the
filter form, view toggle, pagination, and table so filtered htmx responses
keep the full vertical page order synchronized with the current server state.

The `network_name` and `user` filters remain literal case-insensitive
substring searches. Regex syntax is not part of the public contract.

Sortable headers are dual-mode links (`href` + `hx-get`) targeting
`#nns-content` with `hx-push-url="true"`.

The fragment-owned GET form keeps `view`, `sort`, and `order` in hidden inputs.
Because the full filter form is inside the swapped fragment, htmx responses do
not need out-of-band hidden-input refresh for this page.

The `/rate_limits` page client row and the sidebar `GitHub Rate Limits` link
both project their cadence from `poll.rate_limits_github`.

The `/rate_limits` server row projects its separate cadence from
`poll.rate_limits_server`.

The sidebar link keeps a fixed label and uses the same red status styling as
the pending-users sidebar item whenever the client GitHub budget is below the
threshold.

The sidebar link is rendered directly in `base.html.j2` with the same
`data-poll-seconds` cadence that `application.js` uses for client-side GitHub
budget checks.

`application.js` owns the full browser-side lifecycle for that client poll:

- it initializes on every page that renders `#rate-limits-nav-link`;
- it pauses its timer while the document is hidden;
- it refreshes immediately when the page becomes visible again and on window
   `focus`;
- it refreshes again on persisted `pageshow` so bfcache restores do not leave
   stale sidebar or `/rate_limits` client-row state.

The `/rate_limits/server` endpoint returns a tiny inline HTML fragment: the
remaining server budget plus an out-of-band `#server_reset` update. This route
does not need a dedicated Jinja template.

The pending-users sidebar wrapper, the `/rate_limits/server` poller, and the
client-side GitHub rate-limit refresh all use `visibilitychange` activation, so
an active page refreshes after a hidden tab becomes visible again without
issuing duplicate calls on first page load.

The GitHub sidebar link also restores the last known client warning state from
local storage before first paint so page navigation does not briefly flash the
link back to its normal color.

### `run_table_row_fragment.html.j2`

| Key | Type |
|-----|------|
| `row` | run row dict |
| `show_delete` | bool |
| `show_gauge` | bool |

### `tasks_content_fragment.html.j2`

Content fragment for the tasks table. Swaps the scrolling table markup into
`#tasks-content` and refreshes the fixed controls/pagination wrappers OOB.
Includes `tasks_rows_fragment.html.j2` for the `<tr>` rows.
Context keys: `tasks`, `show_pentanomial`, `show_residual`, `run_id`,
`show_task`, `sort`, `order`, `q`, `view`, `pages`, `num_tasks`, `max_all`,
`is_truncated`.

### `tasks_rows_fragment.html.j2`

Row renderer included by `tasks_content_fragment.html.j2`.
Context keys: `tasks`, `show_pentanomial`, `show_residual`.

### `tests_filter_tabs_fragment.html.j2`

Reusable partial included by `tests_finished.html.j2` and
`tests_user.html.j2` for filter tab buttons (All / Green / Yellow / LTC).

| Key | Type | Description |
|-----|------|-------------|
| `filters` | dict | `{success_only, yellow_only, ltc_only}` |
| `hx_target` | string | Target element ID for `hx-target` |
| `base_url` | string | Base URL for filter links (default `/tests/finished`) |

When present, `filters.all_query_string` and `filters.filtered_query_suffix`
preserve additional GET state such as username search fields while the user
switches between the tab filters.

### `tests_finished_content_fragment.html.j2`

| Key | Type |
|-----|------|
| `filters` | dict (`ltc_only`, `success_only`, `yellow_only`, `username_query`, `text`, `max_count`) |
| `finished_runs` | list of run rows |
| `num_finished_runs` | int |
| `finished_page_size` | int |
| `finished_runs_pages` | list |

This full-page include owns the tab strip and the search-first
`/tests/finished` GET form. Username substring uses a cached finished-run
username list and the exact-username finished-run path, while the `text` field
performs a case-insensitive MongoDB text search against the last-column run
info text on finished rows only. The form preserves the effective `max_count`
cap so tab switches and pagination stay on the same server-authoritative
finished-tests query contract.

### `tests_finished_results_fragment.html.j2`

| Key | Type |
|-----|------|
| `filters` | dict |
| `finished_runs` | list of run rows |
| `num_finished_runs` | int |
| `visible_finished_runs` | int |
| `finished_page_size` | int |
| `finished_runs_pages` | list |
| `page_idx` | int |
| `search_mode` | bool |
| `is_hx` | bool |

This is the htmx fragment returned by `/tests/finished` for fragment requests.
It updates `#tests-finished-content` and, in navigation mode, piggy-backs an
out-of-band replacement of the tab wrapper so the active tab stays aligned with
the pushed URL after htmx tab clicks.

### `tests_user_content_fragment.html.j2`

| Key | Type |
|-----|------|
| `username` | string |
| `is_approver` | bool |
| `filters` | dict |
| `run_tables_ctx` | dict |

### `user_management_content_fragment.html.j2`

Same context as the content area of `user_management.html.j2`: `group`,
`sort`, `order`, `q`, `view`, `pages`, `selected_users`,
`num_selected_users`, `max_all`, `is_truncated`.

The outer GET form keeps `sort`, `order`, and `view` in hidden inputs. htmx
fragment responses refresh those inputs out of band so later form-triggered
requests preserve the current table state.

### `user_management_rows_fragment.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `selected_users` | list of user row dicts | Filtered user rows |

### `workers_content_fragment.html.j2`

Same context as the content area of `workers.html.j2`: `filter_value`,
`sort`, `order`, `q`, `view`, `pages`, `blocked_workers`, `show_email`,
`num_workers`, `max_all`, `is_truncated`.

Sortable headers are dual-mode links (`href` + `hx-get`) targeting
`#workers-content` with `hx-push-url="true"`.

The outer GET form keeps `sort`, `order`, and `view` in hidden inputs. htmx
fragment responses refresh those inputs out of band so later form-triggered
requests preserve the current table state.

## htmx shell-state rule

When a GET form stays outside the swapped fragment but the fragment owns
sort/view/pagination links, the fragment must refresh any stateful hidden form
inputs out of band. This repo uses the same pattern as `/tests/machines`:

- keep stable ids on the outer hidden inputs;
- return matching hidden inputs from the fragment with `hx-swap-oob="true"`.

That keeps later form submissions aligned with the current server-authoritative
table state without introducing page-specific synchronization JavaScript.

### `workers_rows_fragment.html.j2`

| Key | Type | Description |
|-----|------|-------------|
| `blocked_workers` | list of dicts | Filtered worker rows |
| `show_email` | bool | Show owner email column |

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

11. **Fragment templates do not extend `base.html.j2`**: htmx fragment
    templates are standalone files. They receive the shared base context
    via `build_template_context()` but must not use `{% extends %}` or
    `{% block %}` directives.

12. **OOB swap elements carry their own `hx-swap-oob` attribute**: the
    view handler does not need to set response headers for OOB updates.
    Each OOB element in the fragment template declares its own ID and swap
    strategy (e.g., `<span id="count" hx-swap-oob="innerHTML">`).

13. **Table OOB requires `<template>` wrappers**: the HTML parser rejects
    `<tbody>` inside `<div>`. Wrap table OOB elements in `<template>` tags:
    ```jinja
    <template>
      <tbody id="my-table" hx-swap-oob="innerHTML">
        {% for row in rows %}...{% endfor %}
      </tbody>
    </template>
    ```
    htmx processes the `<template>` content and discards the wrapper.

14. **DOM API over `innerHTML` in error handlers**: JavaScript retry-button
    construction must use `createElement` / `textContent` / `setAttribute`
    instead of string concatenation with `innerHTML`. This prevents XSS
    from error messages and avoids escaping issues.

15. **Unicode over HTML entities**: use literal Unicode characters (e.g.,
    `<=` or the actual symbol) instead of HTML entities (`&#8804;`,
    `&gt;`) in templates. This eliminates the need for `|safe` on values
    that contain the entity.

16. **Explicit CSRF hidden fields**: every server-rendered `<form>` that
    posts to a `require_csrf` route must include an explicit hidden input:
    ```jinja
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    ```
    The meta-tag CSRF token is a fallback for htmx headers; forms must not
    rely on it as the sole CSRF transport.

17. **Polling trigger policy**: every periodic htmx poller must include
    three trigger components: (a) a periodic trigger gated on
    `document.visibilityState === 'visible'`, (b) an immediate
    `visibilitychange[...] from:document` refresh, and (c) for
    section-scoped pollers, a gate on the section's expanded state.
    See [1-architecture.md](1-architecture.md) for the full policy.

## Adding a new template

### Page template

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

### Fragment template

1. Create `templates/mypage_fragment.html.j2` as a standalone file (no
   `{% extends %}`).

2. Define the context contract in this document.

3. In the view handler, use `_render_hx_fragment()` to return the fragment
   when `HX-Request` is present:
   ```python
   return (
       _render_hx_fragment(request, "mypage_fragment.html.j2", context)
       or context
   )
   ```

4. For OOB elements, add `hx-swap-oob` attributes directly on elements
   inside the fragment template. For table bodies, wrap in `<template>` tags.

5. Add a test that verifies both the full-page and fragment responses.
