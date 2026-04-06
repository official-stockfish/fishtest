# ruff: noqa: ANN201, ANN206, D100, D101, D102, E501, INP001, PT009
"""Test `/tests` and `/tests/user/{username}` UI route contracts."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ui_user_test_case import UiUserTestCase

from fishtest.http.settings import UI_STATE_COOKIE_MAX_AGE_SECONDS


class TestTestsHomepage(UiUserTestCase):
    username = "TestHomepageUser"

    def test_tests_homepage_hidden_workers_count_recomputes_filtered_value(self):
        now = datetime.now(UTC)
        docs = [
            {
                "username": self.username,
                "country_code": "us",
                "concurrency": 2,
                "unique_key": "joekey-aaaa-bbbb",
                "nps": 2_500_000,
                "max_memory": 4096,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 100,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-joe", "args": {"new_tag": "main"}},
            },
            {
                "username": "TestPeerUser",
                "country_code": "it",
                "concurrency": 4,
                "unique_key": "otherkey-cccc-dddd",
                "nps": 3_000_000,
                "max_memory": 8192,
                "uname": "Windows 11",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "clang",
                "python_version": [3, 11, 0],
                "version": 101,
                "modified": False,
                "task_id": 2,
                "last_updated": now - timedelta(seconds=30),
                "run": {"_id": "run-other", "args": {"new_tag": "dev"}},
            },
        ]
        aggregate_result = ({"pending": [], "active": []}, 0.0, 0, 0, 0, 2)

        self.client.cookies.set("machines_q", "windows")
        self.client.cookies.set("machines_filtered_count", "99")
        self.client.cookies.set("machines_state", "Show")

        with (
            patch.object(
                self.rundb,
                "aggregate_unfinished_runs",
                return_value=aggregate_result,
            ),
            patch.object(self.rundb, "get_machines", return_value=docs),
        ):
            homepage = self.client.get("/tests")

        self.assertEqual(homepage.status_code, 200)
        self.assertIn("Workers - 2 (1)", homepage.text)

    def test_tests_homepage_live_run_tables_recomputes_filtered_workers_count_label(
        self,
    ):
        now = datetime.now(UTC)
        docs = [
            {
                "username": self.username,
                "country_code": "us",
                "concurrency": 2,
                "unique_key": "joekey-aaaa-bbbb",
                "nps": 2_500_000,
                "max_memory": 4096,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 100,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-joe", "args": {"new_tag": "main"}},
            },
            {
                "username": "TestPeerUser",
                "country_code": "it",
                "concurrency": 4,
                "unique_key": "otherkey-cccc-dddd",
                "nps": 3_000_000,
                "max_memory": 8192,
                "uname": "Windows 11",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "clang",
                "python_version": [3, 11, 0],
                "version": 101,
                "modified": False,
                "task_id": 2,
                "last_updated": now - timedelta(seconds=30),
                "run": {"_id": "run-other", "args": {"new_tag": "dev"}},
            },
        ]
        runs = {"pending": [], "active": []}
        aggregate_result = (runs, 0.0, 0, 0, 0, 2)

        self.client.cookies.set("machines_q", "windows")
        self.client.cookies.set("machines_filtered_count", "99")

        with (
            patch.object(
                self.rundb,
                "aggregate_unfinished_runs",
                return_value=aggregate_result,
            ),
            patch.object(self.rundb, "get_machines", return_value=docs),
        ):
            response = self.client.get(
                "/tests?live=run_tables",
                headers={"HX-Request": "true"},
            )

        self.assertEqual(response.status_code, 286)
        self.assertIn("Workers - 2 (1)", response.text)

    def test_tests_homepage_live_run_tables_keeps_hidden_active_filtered_count_current(
        self,
    ):
        now = datetime.now(UTC)
        runs = {
            "pending": [],
            "active": [
                {
                    "_id": "run-sprt-stc-st",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
                {
                    "_id": "run-spsa-ltc-smp",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "spsa-ltc-smp",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "60+0.6",
                        "threads": 4,
                        "spsa": {"iter": 1, "num_iter": 10},
                        "num_games": 1000,
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 16,
                    "workers": 4,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
            ],
        }
        aggregate_result = (runs, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "sprt,stc,st")
        self.client.cookies.set("active_state", "Show")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            response = self.client.get(
                "/tests?live=run_tables",
                headers={"HX-Request": "true"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="active-count"', response.text)
        self.assertIn('id="active-tbody"', response.text)
        self.assertIn("sprt-stc-st", response.text)
        self.assertIn("spsa-ltc-smp", response.text)
        self.assertIn("Active - 2 (1) tests", response.text)

    def test_tests_homepage_machines_filters_render_and_persist(self):
        now = datetime.now(UTC)
        docs = [
            {
                "username": self.username,
                "country_code": "us",
                "concurrency": 2,
                "unique_key": "joekey-aaaa-bbbb",
                "nps": 2_500_000,
                "max_memory": 4096,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 100,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-joe", "args": {"new_tag": "main"}},
            }
        ]

        self._login_user()
        with patch.object(self.rundb, "get_machines", return_value=docs):
            set_state_response = self.client.get(
                "/tests/machines?sort=machine&order=asc&page=2&my_workers=1&q=linux"
            )

        self.assertEqual(set_state_response.status_code, 200)

        homepage = self.client.get("/tests")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn('id="machines-filters"', homepage.text)
        self.assertIn('id="machines_q"', homepage.text)
        self.assertIn('placeholder="Filter any column"', homepage.text)
        self.assertIn('value="linux"', homepage.text)
        self.assertIn('id="machines_my_workers"', homepage.text)
        self.assertIn('id="machines_sort" name="sort" value="machine"', homepage.text)
        self.assertIn('id="machines_order" name="order" value="asc"', homepage.text)
        self.assertIn('id="machines_page" name="page" value="1"', homepage.text)
        self.assertIn("checked", homepage.text)
        self.assertIn(
            f'data-toggle-cookie-max-age="{UI_STATE_COOKIE_MAX_AGE_SECONDS}"',
            homepage.text,
        )
        self.assertIn("static/js/tests_homepage.js", homepage.text)
        self.assertNotIn("document.activeElement?.id !== 'machines_q'", homepage.text)
        self.assertIn(
            "visibilitychange[document.visibilityState === 'visible' && document.getElementById('machines-panel').classList.contains('show')] from:document",
            homepage.text,
        )
        self.assertIn('hx-get="/tests?live=run_tables"', homepage.text)

    def test_tests_homepage_active_filters_render_persisted_first_paint_state(self):
        now = datetime.now(UTC)
        runs = {
            "pending": [],
            "active": [
                {
                    "_id": "run-sprt-stc-st",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "info": "sprt run",
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
                {
                    "_id": "run-spsa-ltc-smp",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "spsa-ltc-smp",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "60+0.6",
                        "threads": 4,
                        "spsa": {"iter": 1, "num_iter": 10},
                        "num_games": 1000,
                        "info": "spsa run",
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 16,
                    "workers": 4,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
            ],
        }
        aggregate_result = (runs, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "sprt,stc,st")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            homepage = self.client.get("/tests")

        self.assertEqual(homepage.status_code, 200)
        self.assertIn("Active - 2 (1) tests", homepage.text)
        self.assertIn('id="active-run-filter-style"', homepage.text)
        self.assertIn("display: none !important;", homepage.text)
        self.assertIn("[data-test-type=&#34;spsa&#34;]", homepage.text)
        self.assertIn("[data-time-control=&#34;ltc&#34;]", homepage.text)
        self.assertIn('data-active-filter-index="0"', homepage.text)
        self.assertIn('data-active-filter-index="1"', homepage.text)
        self.assertNotIn("data-row-parity", homepage.text)
        self.assertLess(
            homepage.text.index('id="active-run-filter-style"'),
            homepage.text.index(
                'src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"'
            ),
        )
        self.assertIn(
            'id="active-filter-sprt" value="sprt"\n               data-dimension="test-type" checked',
            homepage.text,
        )
        self.assertIn(
            'id="active-filter-spsa" value="spsa"\n               data-dimension="test-type" >',
            homepage.text,
        )

    def test_tests_homepage_active_filters_keep_parentheses_when_count_matches_total(
        self,
    ):
        now = datetime.now(UTC)
        runs = {
            "pending": [],
            "active": [
                {
                    "_id": "run-sprt-stc-st-1",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st-1",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
                {
                    "_id": "run-sprt-stc-st-2",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st-2",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
            ],
        }
        aggregate_result = (runs, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "sprt,stc,st")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            homepage = self.client.get("/tests")

        self.assertEqual(homepage.status_code, 200)
        self.assertIn("Active - 2 (2) tests", homepage.text)

    def test_tests_homepage_active_filter_bar_visible_without_active_runs(self):
        aggregate_result = ({"pending": [], "active": []}, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "sprt,stc,st")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            homepage = self.client.get("/tests")

        self.assertEqual(homepage.status_code, 200)
        self.assertIn('id="active-run-filters"', homepage.text)
        self.assertIn('id="active-filter-toggle"', homepage.text)
        self.assertIn('id="active-filter-all"', homepage.text)
        self.assertIn('id="active-filter-sprt"', homepage.text)
        self.assertIn("No active tests", homepage.text)

    def test_tests_homepage_live_run_tables_keeps_active_parentheses_when_count_matches_total(
        self,
    ):
        now = datetime.now(UTC)
        runs = {
            "pending": [],
            "active": [
                {
                    "_id": "run-sprt-stc-st-1",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st-1",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
                {
                    "_id": "run-sprt-stc-st-2",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st-2",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
            ],
        }
        aggregate_result = (runs, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "sprt,stc,st")
        self.client.cookies.set("active_state", "Show")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            response = self.client.get(
                "/tests?live=run_tables",
                headers={"HX-Request": "true"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Active - 2 (2) tests", response.text)

    def test_tests_user_page_uses_canonical_live_run_tables_url(self):
        self._create_run()

        response = self.client.get(f"/tests/user/{self.username}?success_only=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'hx-get="/tests/user/{self.username}?success_only=1&amp;live=run_tables"',
            response.text,
        )

    def test_tests_user_page_live_url_omits_stray_username_query(self):
        self._create_run()

        response = self.client.get(
            f"/tests/user/{self.username}?username=TestPeerUser&success_only=1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'hx-get="/tests/user/{self.username}?success_only=1&amp;live=run_tables"',
            response.text,
        )
        self.assertNotIn("username=TestPeerUser", response.text)

    def test_tests_homepage_active_filters_persist_none_selection(self):
        now = datetime.now(UTC)
        runs = {
            "pending": [],
            "active": [
                {
                    "_id": "run-sprt-stc-st",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "sprt-stc-st",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "10+0.1",
                        "threads": 1,
                        "sprt": {
                            "llr": 0.0,
                            "lower_bound": -2.94,
                            "upper_bound": 2.94,
                            "elo0": 0.0,
                            "elo1": 2.0,
                            "state": "",
                        },
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 2,
                    "workers": 1,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
                {
                    "_id": "run-numgames-ltc-smp",
                    "args": {
                        "username": self.username,
                        "base_tag": "master",
                        "new_tag": "numgames-ltc-smp",
                        "resolved_base": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "resolved_new": "347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
                        "tc": "60+0.6",
                        "threads": 2,
                        "num_games": 1000,
                        "tests_repo": self.tests_repo,
                    },
                    "start_time": now,
                    "finished": False,
                    "cores": 8,
                    "workers": 2,
                    "results": {"wins": 0, "losses": 0, "draws": 0},
                },
            ],
        }
        aggregate_result = (runs, 0.0, 0, 0, 0, 0)

        self.client.cookies.set("active_run_filters", "none")

        with patch.object(
            self.rundb,
            "aggregate_unfinished_runs",
            return_value=aggregate_result,
        ):
            homepage = self.client.get("/tests")

        self.assertEqual(homepage.status_code, 200)
        self.assertIn("Active - 2 (0) tests", homepage.text)
        self.assertIn('id="active-run-filter-style"', homepage.text)
        self.assertIn("display: none !important;", homepage.text)
        self.assertIn("[data-test-type=&#34;sprt&#34;]", homepage.text)
        self.assertIn("[data-test-type=&#34;numgames&#34;]", homepage.text)
        self.assertIn('data-active-filter-index="0"', homepage.text)
        self.assertIn('data-active-filter-index="1"', homepage.text)
        self.assertNotIn("data-row-parity", homepage.text)
        self.assertLess(
            homepage.text.index('id="active-run-filter-style"'),
            homepage.text.index(
                'src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"'
            ),
        )
        self.assertIn(
            'id="active-filter-sprt" value="sprt"\n               data-dimension="test-type" >',
            homepage.text,
        )

    def test_tests_user_hx_filter_fragment_keeps_notification_and_toggle_hooks(self):
        self._create_run()

        response = self.client.get(
            f"/tests/user/{self.username}?success_only=1",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="tests-user-filters"', response.text)
        self.assertIn('id="notification_', response.text)
        self.assertIn('data-toggle-cookie-name="', response.text)
        self.assertIn(
            f'data-toggle-cookie-max-age="{UI_STATE_COOKIE_MAX_AGE_SECONDS}"',
            response.text,
        )

    def test_notifications_js_reinitializes_after_htmx_swaps(self):
        js_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "js"
            / "notifications.js"
        )
        js_source = js_path.read_text(encoding="utf-8")

        self.assertIn('document.addEventListener("htmx:afterSwap"', js_source)
        self.assertIn('document.addEventListener("htmx:load"', js_source)
        self.assertIn("initializeNotificationButtons(target)", js_source)
        self.assertIn('notification.dataset.notificationReady = "1"', js_source)
