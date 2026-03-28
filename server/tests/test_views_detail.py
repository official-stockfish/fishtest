"""Test `/tests/view` detail-page and detail-fragment contracts."""

import unittest
from datetime import UTC, datetime

import test_support

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
        cls.username = "ViewDetailUser"
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            close_conn=False,
        )
        cls.rundb.userdb.create_user(
            cls.username,
            "secret",
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
        self.assertNotIn("const spsaData =", response.text)

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
            f'id="spsa-data-{run_id}" type="application/json" hx-swap-oob="outerHTML"',
            response.text,
        )
        self.assertIn("ParamA", response.text)
        self.assertIn("iter: 3, A: 4", response.text)
        self.assertNotIn("<title>", response.text)
