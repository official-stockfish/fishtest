"""Test `/tests/stats` page and fragment contracts."""

import unittest
from datetime import UTC, datetime

import test_support

from fishtest.http.settings import POLL_TESTS_STATS_S
from fishtest.run_cache import Prio


class TestTestsStatsView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        cls.username = "TestStatsUser"
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            close_conn=False,
        )
        cls.rundb.userdb.create_user(
            cls.username,
            "test-stats-password",
            "view-stats@example.com",
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

    def _create_run(self) -> str:
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
        run["approved"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return str(run_id)

    def test_tests_stats_page_renders_shell_with_poller(self):
        run_id = self._create_run()

        response = self.client.get(f"/tests/stats/{run_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Raw Statistics for test", response.text)
        self.assertIn(f'hx-get="/tests/stats/{run_id}"', response.text)
        self.assertIn(
            f"every {POLL_TESTS_STATS_S}s [document.visibilityState === 'visible']",
            response.text,
        )
        self.assertIn('id="tests-stats-content"', response.text)

    def test_tests_stats_hx_paused_returns_204(self):
        run_id = self._create_run()

        response = self.client.get(
            f"/tests/stats/{run_id}",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.text, "")

    def test_tests_stats_hx_active_returns_fragment(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["workers"] = 1
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(
            f"/tests/stats/{run_id}",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="tests-stats-content"', response.text)
        self.assertIn("Draws", response.text)
        self.assertNotIn("<title>", response.text)

    def test_tests_stats_hx_terminal_returns_286(self):
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["finished"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(
            f"/tests/stats/{run_id}",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 286)
        self.assertIn('id="tests-stats-content"', response.text)
