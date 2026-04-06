"""Test `/tests/view` detail-page and detail-fragment contracts."""

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import test_support
from ui_user_test_case import UiUserTestCase

from fishtest.http.settings import UI_STATE_COOKIE_MAX_AGE_SECONDS
from fishtest.run_cache import Prio


def _make_task(task_id, username, unique_key, now, *, wins, losses, draws):
    return {
        "task_id": task_id,
        "num_games": 30,
        "active": True,
        "last_updated": now,
        "worker_info": {
            "username": username,
            "unique_key": unique_key,
            "concurrency": 1,
            "uname": "Linux",
            "max_memory": 2048,
            "compiler": "g++",
            "gcc_version": [13, 2, 0],
            "python_version": [3, 12, 0],
            "version": 1,
            "ARCH": "popcnt",
            "worker_arch": "x86-64",
        },
        "stats": {
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "crashes": 0,
            "time_losses": 0,
        },
    }


class TestTestsViewDetail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        cls.username = "TestDetailUser"
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            close_conn=False,
        )
        cls.rundb.userdb.create_user(
            cls.username,
            "test-detail-password",
            "view-detail@example.com",
            "https://github.com/official-stockfish/Stockfish",
        )

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            clear_runs=True,
            drop_runs=True,
        )

    def setUp(self):
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )

    def _assert_expected_input(
        self,
        html: str,
        value: str,
        *,
        oob: bool = False,
    ) -> None:
        self.assertIn('id="tests-view-detail-expected"', html)
        self.assertIn('name="expected"', html)
        self.assertIn(f'value="{value}"', html)
        if oob:
            self.assertIn('hx-swap-oob="true"', html)

    def _create_run(self, *, approved: bool = True) -> str:
        run_id = self.rundb.new_run(
            "master",
            "master",
            400,
            "10+0.01",
            "10+0.01",
            "book.pgn",
            "10",
            1,
            "",
            "",
            info="UI test run",
            resolved_base="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            resolved_new="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            msg_base="Base",
            msg_new="New",
            base_signature="123456",
            new_signature="654321",
            base_nets=["nn-0000000000a0.nnue"],
            new_nets=["nn-0000000000a0.nnue"],
            rescheduled_from="653db116cc309ae839563103",
            tests_repo="https://github.com/official-stockfish/Stockfish",
            auto_purge=False,
            username=self.username,
            start_time=datetime.now(UTC),
            arch_filter="avx",
        )
        run = self.rundb.get_run(run_id)
        run["approved"] = approved
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return str(run_id)

    def test_tests_view_page_renders_detail_poller_and_spsa_container(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["workers"] = 1
        run["args"]["spsa"] = {
            "iter": 1,
            "num_iter": 10,
            "A": 4,
            "alpha": 0.602,
            "gamma": 0.101,
            "params": [
                {
                    "name": "ParamA",
                    "theta": 12.5,
                    "start": 10,
                    "min": 0,
                    "max": 20,
                    "c": 1.6,
                    "c_end": 0.1,
                    "a": 0.2,
                    "r_end": 1.0e-03,
                },
            ],
            "param_history": [[{"theta": 12.0, "c": 1.5}]],
        }
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(f"/tests/view/{run_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.text.count(
                f'hx-get="/tests/view/{run_id}/detail"',
            ),
            1,
        )
        self.assertIn(
            f'hx-get="/tests/view/{run_id}/detail"',
            response.text,
        )
        self.assertIn(
            'hx-include="#tests-view-detail-expected"',
            response.text,
        )
        self._assert_expected_input(response.text, "active")
        self.assertNotIn(f'hx-get="/tests/elo/{run_id}?expected=active"', response.text)
        self.assertIn('id="tests-view-spsa"', response.text)
        self.assertIn(
            f'id="spsa-data-{run_id}" type="application/json"',
            response.text,
        )
        self.assertIn('id="spsa_history_scroll"', response.text)
        self.assertIn('id="spsa_history_plot"', response.text)
        self.assertNotIn('id="spsa_history_plot" style=', response.text)
        self.assertNotIn("const spsaData =", response.text)

    def test_tests_view_page_renders_query_free_open_graph_metadata(self):
        run_id = self._create_run()

        response = self.client.get(f"/tests/view/{run_id}?follow=1&show_task=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            test_support.extract_meta_content(
                response.text,
                property_name="og:title",
            ),
            "400 games - master vs master | Stockfish Testing",
        )
        self.assertEqual(
            test_support.extract_meta_content(
                response.text,
                property_name="og:url",
            ),
            f"http://testserver/tests/view/{run_id}",
        )
        description = test_support.extract_meta_content(
            response.text,
            property_name="og:description",
        )
        self.assertIn("Total:", description)
        self.assertIn("\n", description)
        self.assertNotIn("```", description)

    def test_tests_view_page_uses_shared_ui_cookie_max_age_for_theme_and_tasks(self):
        run_id = self._create_run()

        response = self.client.get(f"/tests/view/{run_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"window.uiStateCookieMaxAgeSeconds = {UI_STATE_COOKIE_MAX_AGE_SECONDS};",
            response.text,
        )
        self.assertIn('id="tasks-button"', response.text)
        self.assertIn(
            f'data-toggle-cookie-max-age="{UI_STATE_COOKIE_MAX_AGE_SECONDS}"',
            response.text,
        )

    def test_tests_view_page_open_graph_description_is_multiline_and_keeps_ptnml(
        self,
    ):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["results"] = {
            "wins": 22,
            "losses": 18,
            "draws": 20,
            "pentanomial": [3, 5, 14, 6, 2],
        }
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(f"/tests/view/{run_id}")

        self.assertEqual(response.status_code, 200)
        description = test_support.extract_meta_content(
            response.text,
            property_name="og:description",
        )
        self.assertIn("\n", description)
        self.assertNotIn("```", description)
        self.assertIn("Elo:", description)
        self.assertIn("nElo:", description)
        self.assertIn("+/-", description)
        self.assertIn("Ptnml(0-2):", description)
        self.assertNotIn("&plusmn;", description)

    def test_tests_view_detail_polls_pending_then_paused_then_204(self):
        run_id = self._create_run(approved=False)

        page_response = self.client.get(f"/tests/view/{run_id}")

        self.assertEqual(page_response.status_code, 200)
        self._assert_expected_input(page_response.text, "pending")

        run = self.rundb.get_run(run_id)
        run["approved"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        transition_response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=pending",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(transition_response.status_code, 200)
        self._assert_expected_input(transition_response.text, "paused", oob=True)
        self.assertIn(
            f'id="run-status-{run_id}" hx-swap-oob="innerHTML">paused<',
            transition_response.text,
        )

        settled_response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=paused",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(settled_response.status_code, 204)
        self.assertEqual(settled_response.text, "")

    def test_tests_view_detail_polls_paused_then_pending_then_204(self):
        run_id = self._create_run(approved=True)

        page_response = self.client.get(f"/tests/view/{run_id}")

        self.assertEqual(page_response.status_code, 200)
        self._assert_expected_input(page_response.text, "paused")

        run = self.rundb.get_run(run_id)
        run["approved"] = False
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        transition_response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=paused",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(transition_response.status_code, 200)
        self._assert_expected_input(transition_response.text, "pending", oob=True)
        self.assertIn(
            f'id="run-status-{run_id}" hx-swap-oob="innerHTML">pending<',
            transition_response.text,
        )

        settled_response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=pending",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(settled_response.status_code, 204)
        self.assertEqual(settled_response.text, "")

    def test_tests_view_detail_hx_paused_returns_204(self):
        run_id = self._create_run()

        response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=paused",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.text, "")

    def test_tests_view_detail_hx_active_returns_non_spsa_oob_fragments(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        now = datetime.now(UTC)
        run["workers"] = 2
        run["results"] = {"wins": 22, "losses": 18, "draws": 20}
        run["tasks"] = [
            _make_task(
                1,
                "WorkerOne",
                "worker-one-0001",
                now,
                wins=8,
                losses=9,
                draws=13,
            ),
            _make_task(
                2,
                "WorkerTwo",
                "worker-two-0002",
                now,
                wins=14,
                losses=9,
                draws=7,
            ),
        ]
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=active",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'id="elo-{run_id}" hx-swap-oob="innerHTML"', response.text)
        self.assertIn(
            f'id="run-status-{run_id}" hx-swap-oob="innerHTML"',
            response.text,
        )
        self.assertIn('id="tasks-totals" hx-swap-oob="innerHTML"', response.text)
        self.assertIn(
            'id="tests-view-details" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertIn(
            'id="tests-view-stats" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertIn(
            'id="tests-view-time" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertIn("chi^2", response.text)
        self.assertIn("p-value", response.text)
        self.assertNotIn("<title>", response.text)

    def test_tests_view_detail_hx_active_returns_spsa_oob_fragments(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["workers"] = 1
        run["results"] = {"wins": 4, "losses": 2, "draws": 6}
        run["args"]["spsa"] = {
            "iter": 2,
            "num_iter": 10,
            "A": 4,
            "alpha": 0.602,
            "gamma": 0.101,
            "params": [
                {
                    "name": "ParamA",
                    "theta": 12.5,
                    "start": 10,
                    "min": 0,
                    "max": 20,
                    "c": 1.6,
                    "c_end": 0.1,
                    "a": 0.2,
                    "r_end": 1.0e-03,
                },
            ],
            "param_history": [
                [{"theta": 11.5, "c": 1.5}],
                [{"theta": 12.0, "c": 1.4}],
            ],
        }
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(
            f"/tests/view/{run_id}/detail?expected=active",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'id="elo-{run_id}" hx-swap-oob="innerHTML"', response.text)
        self.assertIn(
            f'id="run-status-{run_id}" hx-swap-oob="innerHTML"',
            response.text,
        )
        self.assertIn('id="tasks-totals" hx-swap-oob="innerHTML"', response.text)
        self.assertIn(
            'id="tests-view-details" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertIn(
            'id="tests-view-time" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertNotIn('id="tests-view-stats" hx-swap-oob="outerHTML"', response.text)
        self.assertIn(
            f'id="spsa-data-{run_id}" type="application/json" hx-swap-oob="innerHTML"',
            response.text,
        )
        self.assertIn("ParamA", response.text)
        self.assertIn("iter: 3, A: 4", response.text)
        self.assertNotIn("<title>", response.text)

    def test_spsa_script_skips_noop_redraws_without_hover_gating(self):
        script_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "js"
            / "spsa.js"
        )
        script_source = script_path.read_text(encoding="utf-8")

        self.assertIn("payloadText === lastRenderedPayloadText", script_source)
        self.assertIn("const scroller = getSPSAScrollContainer();", script_source)
        self.assertNotIn('historyPlot.addEventListener("pointerenter"', script_source)
        self.assertNotIn('historyPlot.addEventListener("pointerleave"', script_source)
        self.assertNotIn("deferredRefreshPending", script_source)

    def test_spsa_plot_shell_keeps_fixed_chart_dimensions(self):
        repo_root = Path(__file__).resolve().parents[1]
        template_source = (
            repo_root / "fishtest" / "templates" / "tests_view_spsa_section.html.j2"
        ).read_text(encoding="utf-8")
        css_source = (
            repo_root / "fishtest" / "static" / "css" / "application.css"
        ).read_text(encoding="utf-8")
        script_source = (
            repo_root / "fishtest" / "static" / "js" / "spsa.js"
        ).read_text(encoding="utf-8")

        self.assertIn('id="spsa_history_plot"', template_source)
        self.assertNotIn('id="spsa_history_plot" style=', template_source)
        self.assertIn(
            'class="overflow-auto overflow-y-hidden" id="spsa_history_scroll"',
            template_source,
        )
        self.assertIn("#spsa_history_plot {", css_source)
        self.assertIn("width: 100%;", css_source)
        self.assertIn("max-width: 1000px;", css_source)
        self.assertIn("min-height: 500px;", css_source)
        self.assertNotIn("#spsa_history_scroll {", css_source)
        self.assertNotIn("overflow-x: auto;", css_source)
        self.assertNotIn("getBoundingClientRect()", script_source)
        self.assertNotIn("getComputedStyle(historyPlot)", script_source)
        self.assertNotIn("chartOptions.width = plotSize.width", script_source)
        self.assertIn("width: 1000,", script_source)
        self.assertIn("height: 500,", script_source)


class TestTestsViewTasks(UiUserTestCase):
    username = "TasksUser"

    def test_tests_view_tasks_loader_attaches_before_domcontentloaded(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "templates"
            / "tests_view.html.j2"
        )
        template_source = template_path.read_text(encoding="utf-8")

        self.assertIn(
            'tasksContainer?.addEventListener("htmx:afterSwap", resolveTasksLoadedOnce);',
            template_source,
        )
        self.assertIn(
            'const tasks_head = tasks_container?.querySelector("thead");',
            template_source,
        )
        self.assertIn(
            "const container_rect = tasks_container.getBoundingClientRect();",
            template_source,
        )
        self.assertIn(
            "const row_rect = task_row.getBoundingClientRect();",
            template_source,
        )
        self.assertIn(
            "const max_scroll_top = Math.max(",
            template_source,
        )
        self.assertIn(
            "tasks_container.scrollTop = Math.min(",
            template_source,
        )
        self.assertIn(
            "const nextFrame = () => new Promise((resolve) => {",
            template_source,
        )
        self.assertIn(
            "await nextFrame();",
            template_source,
        )
        self.assertNotIn('document.getElementById("tasks-head")', template_source)
        self.assertIn(
            'if (tasksContainer && (tasksContainer.dataset.tasksLoaded === "1" || tasksContainer.children.length > 0)) {',
            template_source,
        )
        self.assertIn('hx-sync="#tasks-filters:abort"', template_source)
        self.assertIn(
            'tasksContainer?.addEventListener("htmx:responseError", clearTasksLoadingState);',
            template_source,
        )
        self.assertIn(
            'tasksContainer?.addEventListener("htmx:sendError", clearTasksLoadingState);',
            template_source,
        )
        self.assertNotIn("Something went wrong. Please try again.", template_source)
        self.assertNotIn('btn.textContent = "Retry";', template_source)
        tasks_region_start = template_source.index("let resolveTasksLoaded = null;")
        tasks_region = template_source[tasks_region_start:]
        self.assertLess(
            tasks_region.index(
                'tasksContainer?.addEventListener("htmx:afterSwap", resolveTasksLoadedOnce);'
            ),
            tasks_region.index("await DOMContentLoaded();"),
        )

    def test_tests_view_tasks_filters_include_worker_and_info_search(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "templates"
            / "tests_view.html.j2"
        )
        template_source = template_path.read_text(encoding="utf-8")
        tasks_form_start = template_source.index('<form\n      id="tasks-filters"')
        tasks_form_end = template_source.index("</form>", tasks_form_start)
        tasks_form_source = template_source[tasks_form_start:tasks_form_end]

        self.assertIn('id="tasks_q"', tasks_form_source)
        self.assertIn('name="q"', tasks_form_source)
        self.assertIn('class="form-control form-control-sm"', tasks_form_source)
        self.assertNotIn('label for="tasks_q"', tasks_form_source)
        self.assertIn('placeholder="Filter worker or info"', tasks_form_source)
        self.assertIn('aria-label="Filter worker or info"', tasks_form_source)
        self.assertIn(
            'id="tasks_page" name="page" value="{{ tasks_page }}"', tasks_form_source
        )
        self.assertIn("search from:#tasks_q", tasks_form_source)
        self.assertNotIn("search from:#tasks_info", tasks_form_source)
        self.assertNotIn('name="info"', tasks_form_source)
        self.assertIn('id="tasks-view-controls" class="col-auto"', tasks_form_source)
        self.assertIn('id="tasks-pagination" aria-live="polite"', template_source)
        self.assertIn('class="overflow-auto tasks-panel-scroll"', template_source)
        self.assertNotIn(
            'class="overflow-auto {{ "collapse show" if tasks_shown else "collapse" }}"',
            template_source,
        )
        self.assertIn('id="rate-limits-nav-link"', self.client.get("/rate_limits").text)
        self.assertIn(
            "const container_rect = tasks_container.getBoundingClientRect();",
            template_source,
        )
        self.assertIn(
            "const row_rect = task_row.getBoundingClientRect();", template_source
        )
        self.assertIn("const max_scroll_top = Math.max(", template_source)
        self.assertIn("tasks_container.scrollTop = Math.min(", template_source)
        self.assertIn(
            "const nextFrame = () => new Promise((resolve) => {", template_source
        )
        self.assertIn("await nextFrame();", template_source)
        template_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "templates"
            / "tasks_content_fragment.html.j2"
        )
        template_source = template_path.read_text(encoding="utf-8")

        self.assertIn('{{ sort_header("wins", "Wins") }}', template_source)
        self.assertIn('{{ sort_header("losses", "Losses") }}', template_source)
        self.assertIn('{{ sort_header("draws", "Draws") }}', template_source)
        self.assertIn(
            '{{ sort_header("pentanomial", "Pentanomial [0-2]") }}',
            template_source,
        )
        self.assertIn(
            'id="tasks-view-controls" hx-swap-oob="innerHTML"', template_source
        )
        self.assertIn('id="tasks-pagination" hx-swap-oob="innerHTML"', template_source)
        self.assertIn(
            'id="tasks_page" name="page" value="{{ current_page }}" hx-swap-oob="true"',
            template_source,
        )
        self.assertIn('hx-sync="#tasks-filters:abort"', template_source)
        self.assertIn('hx-disinherit="hx-include"', template_source)
        self.assertIn('hx-params="none"', template_source)
        self.assertNotIn('<div class="table-responsive">', template_source)

    def test_tasks_controls_fragment_disinherits_filter_include(self):
        template_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "templates"
            / "tasks_controls_fragment.html.j2"
        )
        template_source = template_path.read_text(encoding="utf-8")

        self.assertIn('hx-sync="#tasks-filters:abort"', template_source)
        self.assertIn('hx-disinherit="hx-include"', template_source)
        self.assertIn('hx-params="none"', template_source)

    def test_tasks_hx_sort_changes_order_and_active_arrow(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        try:
            now = datetime.now(UTC)
            run["tasks"] = [
                {
                    "task_id": 1,
                    "num_games": 100,
                    "active": False,
                    "last_updated": now,
                    "worker_info": {
                        "username": "ZuluUser",
                        "unique_key": "zulu-key-0001",
                        "concurrency": 1,
                        "uname": "Linux",
                        "max_memory": 2048,
                        "compiler": "g++",
                        "gcc_version": [13, 2, 0],
                        "python_version": [3, 12, 0],
                        "version": 1,
                        "ARCH": "popcnt",
                        "worker_arch": "x86-64",
                    },
                    "stats": {
                        "wins": 10,
                        "losses": 1,
                        "draws": 2,
                        "crashes": 0,
                        "time_losses": 0,
                    },
                },
                {
                    "task_id": 2,
                    "num_games": 100,
                    "active": False,
                    "last_updated": now - timedelta(seconds=10),
                    "worker_info": {
                        "username": "AlphaUser",
                        "unique_key": "alpha-key-0002",
                        "concurrency": 1,
                        "uname": "Linux",
                        "max_memory": 2048,
                        "compiler": "g++",
                        "gcc_version": [13, 2, 0],
                        "python_version": [3, 12, 0],
                        "version": 1,
                        "ARCH": "popcnt",
                        "worker_arch": "x86-64",
                    },
                    "stats": {
                        "wins": 3,
                        "losses": 4,
                        "draws": 5,
                        "crashes": 0,
                        "time_losses": 0,
                    },
                },
            ]
            run["bad_tasks"] = []
            run["results"] = {}
            self.rundb.buffer(run, priority=Prio.SAVE_NOW)

            response = self.client.get(
                f"/tests/tasks/{run_id}?sort=worker&order=asc&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn('id="tasks_table"', response.text)
            self.assertIn('aria-sort="ascending"', response.text)
            self.assertLess(
                response.text.index("AlphaUser"),
                response.text.index("ZuluUser"),
            )
            self.assertIn(
                'id="tasks_sort" name="sort" value="worker" hx-swap-oob="true"',
                response.text,
            )
            self.assertIn(
                'id="tasks_order" name="order" value="asc" hx-swap-oob="true"',
                response.text,
            )
        finally:
            self.rundb.runs.delete_one({"_id": run["_id"]})

    def test_tasks_hx_combined_search_matches_worker_and_info_text(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        try:
            now = datetime.now(UTC)
            run["tasks"] = [
                {
                    "task_id": 1,
                    "num_games": 100,
                    "active": False,
                    "last_updated": now,
                    "worker_info": {
                        "username": "LinuxWorker",
                        "unique_key": "linux-key-0001",
                        "concurrency": 1,
                        "uname": "Linux 6.8",
                        "max_memory": 2048,
                        "compiler": "g++",
                        "gcc_version": [13, 2, 0],
                        "python_version": [3, 12, 0],
                        "version": 1,
                        "ARCH": "popcnt avx2",
                        "worker_arch": "x86-64-vnni256",
                    },
                    "stats": {
                        "wins": 1,
                        "losses": 2,
                        "draws": 3,
                        "crashes": 0,
                        "time_losses": 0,
                    },
                },
                {
                    "task_id": 2,
                    "num_games": 100,
                    "active": False,
                    "last_updated": now - timedelta(seconds=10),
                    "worker_info": {
                        "username": "WindowsWorker",
                        "unique_key": "windows-key-0002",
                        "concurrency": 1,
                        "uname": "Windows 11",
                        "max_memory": 4096,
                        "compiler": "clang",
                        "gcc_version": [17, 0, 0],
                        "python_version": [3, 11, 0],
                        "version": 2,
                        "ARCH": "sse4.1",
                        "worker_arch": "x86-64",
                    },
                    "stats": {
                        "wins": 4,
                        "losses": 5,
                        "draws": 6,
                        "crashes": 0,
                        "time_losses": 0,
                    },
                },
            ]
            run["bad_tasks"] = []
            run["results"] = {}
            self.rundb.buffer(run, priority=Prio.SAVE_NOW)

            response = self.client.get(
                f"/tests/tasks/{run_id}?q=vnni256&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("LinuxWorker", response.text)
            self.assertNotIn("WindowsWorker", response.text)

            compiler_response = self.client.get(
                f"/tests/tasks/{run_id}?q=clang&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(compiler_response.status_code, 200)
            self.assertIn("WindowsWorker", compiler_response.text)
            self.assertNotIn("LinuxWorker", compiler_response.text)

            unified_response = self.client.get(
                f"/tests/tasks/{run_id}?q=Windows%2011&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(unified_response.status_code, 200)
            self.assertIn("WindowsWorker", unified_response.text)
            self.assertNotIn("LinuxWorker", unified_response.text)
        finally:
            self.rundb.runs.delete_one({"_id": run["_id"]})

    def test_tasks_show_task_link_selects_containing_page_and_highlights_row(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        try:
            now = datetime.now(UTC)
            run["tasks"] = []
            for task_id in range(100, 130):
                run["tasks"].append(
                    {
                        "task_id": task_id,
                        "num_games": 100,
                        "active": False,
                        "last_updated": now - timedelta(seconds=task_id),
                        "worker_info": {
                            "username": f"Worker{task_id}",
                            "unique_key": f"worker-key-{task_id}",
                            "concurrency": 1,
                            "uname": "Linux",
                            "max_memory": 2048,
                            "compiler": "g++",
                            "gcc_version": [13, 2, 0],
                            "python_version": [3, 12, 0],
                            "version": 1,
                            "ARCH": "popcnt",
                            "worker_arch": "x86-64",
                        },
                        "stats": {
                            "wins": 1,
                            "losses": 2,
                            "draws": 3,
                            "crashes": 0,
                            "time_losses": 0,
                        },
                    },
                )
            run["bad_tasks"] = []
            run["results"] = {
                "wins": 30,
                "losses": 60,
                "draws": 90,
            }
            self.rundb.buffer(run, priority=Prio.SAVE_NOW)

            response = self.client.get(
                f"/tests/tasks/{run_id}?show_task=100&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("Worker100", response.text)
            self.assertNotIn("Worker129", response.text)
            self.assertIn('<tr class="highlight" id="task100">', response.text)

            page_response = self.client.get(f"/tests/view/{run_id}?show_task=100")

            self.assertEqual(page_response.status_code, 200)
            self.assertIn('id="tasks"', page_response.text)
            self.assertIn('class="collapse show"', page_response.text)
            self.assertIn('id="tasks_page" name="page" value="2"', page_response.text)
        finally:
            self.rundb.runs.delete_one({"_id": run["_id"]})

    def test_tasks_hx_spsa_rows_do_not_crash_without_residual_column(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        try:
            now = datetime.now(UTC)
            run["args"]["spsa"] = {"iter": 1, "num_iter": 10}
            run["tasks"] = [
                {
                    "task_id": 7,
                    "num_games": 100,
                    "active": False,
                    "last_updated": now,
                    "worker_info": {
                        "username": "SpsaWorker",
                        "unique_key": "spsa-key-0007",
                        "concurrency": 1,
                        "uname": "Linux",
                        "max_memory": 2048,
                        "compiler": "g++",
                        "gcc_version": [13, 2, 0],
                        "python_version": [3, 12, 0],
                        "version": 1,
                        "ARCH": "popcnt",
                        "worker_arch": "x86-64",
                    },
                    "stats": {
                        "wins": 1,
                        "losses": 2,
                        "draws": 3,
                        "crashes": 0,
                        "time_losses": 0,
                    },
                },
            ]
            run["bad_tasks"] = []
            run["results"] = {"wins": 1, "losses": 2, "draws": 3}
            self.rundb.buffer(run, priority=Prio.SAVE_NOW)

            response = self.client.get(
                f"/tests/tasks/{run_id}?show_task=7&view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("SpsaWorker", response.text)
            self.assertNotIn("Residual", response.text)
        finally:
            self.rundb.runs.delete_one({"_id": run["_id"]})

    def test_tasks_hx_bad_worker_cell_restores_legacy_purged_style(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        try:
            now = datetime.now(UTC)
            run["tasks"] = [
                {
                    "task_id": 18,
                    "num_games": 704,
                    "active": False,
                    "last_updated": now,
                    "worker_info": {
                        "username": "BadWorkerUser",
                        "unique_key": "bad-worker-key-0018",
                        "concurrency": 12,
                        "uname": "Windows 11",
                        "max_memory": 16200,
                        "compiler": "g++",
                        "gcc_version": [15, 2, 0],
                        "python_version": [3, 14, 3],
                        "version": 316,
                        "ARCH": "64bit VNNI BMI2 AVX2 SSE41 SSSE3 SSE2 POPCNT",
                        "worker_arch": "x86-64-avxvnni",
                    },
                    "stats": {
                        "wins": 0,
                        "losses": 0,
                        "draws": 0,
                        "crashes": 0,
                        "time_losses": 0,
                        "pentanomial": [0, 0, 0, 0, 0],
                    },
                },
            ]
            run["bad_tasks"] = []
            run["results"] = {"wins": 0, "losses": 0, "draws": 0}
            self.rundb.set_bad_task(0, run)
            self.rundb.buffer(run, priority=Prio.SAVE_NOW)

            response = self.client.get(
                f"/tests/tasks/{run_id}?view=paged",
                headers={"HX-Request": "true"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(
                'style="text-decoration:line-through; background-color:#ffebeb"',
                response.text,
            )
            self.assertIn("BadWorkerUser", response.text)
        finally:
            self.rundb.runs.delete_one({"_id": run["_id"]})

    def test_application_css_styles_task_search_cancel_button(self):
        css_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "css"
            / "application.css"
        )
        css_source = css_path.read_text(encoding="utf-8")

        self.assertIn(
            '#tasks-filters input[type="search"]::-webkit-search-cancel-button,',
            css_source,
        )
        self.assertIn(
            '#tasks-filters input[type="search"]::-webkit-search-cancel-button:hover,',
            css_source,
        )
        self.assertIn(
            "--tasks-panel-max-height: calc(var(--machines-panel-max-height) + 6rem);",
            css_source,
        )
