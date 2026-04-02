"""Test monthly contributor stats rebuild helpers."""

import copy
import sys
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from utils import delta_update_users


def _user_stats(username):
    return {
        "username": username,
        "cpu_hours": 0.0,
        "games": 0,
        "games_per_hour": 0.0,
        "tests": 0,
        "tests_repo": "",
        "last_updated": datetime.min.replace(tzinfo=UTC),
    }


class _FakeRunsCollection:
    def find(self, *_args, **_kwargs):
        return []


class _FakeRunDb:
    def __init__(self, unfinished_runs):
        self._unfinished_runs = unfinished_runs
        self.get_unfinished_runs_called = False
        self.get_unfinished_runs_for_stats_called = False
        self.runs = _FakeRunsCollection()

    def get_unfinished_runs(self):
        self.get_unfinished_runs_called = True
        return iter([])

    def get_unfinished_runs_for_stats(self):
        self.get_unfinished_runs_for_stats_called = True
        return iter(self._unfinished_runs)


class _FakeRunDbForRates:
    def __init__(self, machines):
        self._machines = machines

    def get_machines(self):
        return self._machines


class DeltaUpdateUsersTest(unittest.TestCase):
    def test_compute_games_rates_updates_both_info_dicts(self):
        machine = {
            "username": "worker-user",
            "nps": delta_update_users.REFERENCE_CORE_NPS,
            "concurrency": 2,
            "run": {
                "args": {
                    "tc": "10+0.1",
                    "threads": 1,
                }
            },
        }
        rundb = _FakeRunDbForRates([machine])
        info_total = {"worker-user": _user_stats("worker-user")}
        info_top_month = copy.deepcopy(info_total)

        delta_update_users.compute_games_rates(rundb, info_total, info_top_month)

        expected = 2 * (
            3600
            / delta_update_users.estimate_game_duration(machine["run"]["args"]["tc"])
        )
        self.assertAlmostEqual(info_total["worker-user"]["games_per_hour"], expected)
        self.assertAlmostEqual(
            info_top_month["worker-user"]["games_per_hour"],
            expected,
        )

    def test_process_run_requires_tasks(self):
        info = {"run-author": _user_stats("run-author")}
        run = {
            "_id": "unfinished-run",
            "args": {"username": "run-author", "tc": "10+0.1", "threads": 1},
        }

        with self.assertRaises(KeyError):
            delta_update_users.process_run(run, info)

    def test_update_info_uses_stats_reader_for_unfinished_runs(self):
        last_updated = datetime.now(UTC)
        run = {
            "_id": "unfinished-run",
            "args": {"username": "run-author", "tc": "10+0.1", "threads": 1},
            "tasks": [
                {
                    "worker_info": {"username": "worker-user"},
                    "stats": {"wins": 2, "losses": 1, "draws": 3},
                    "last_updated": last_updated,
                    "num_games": 6,
                }
            ],
        }
        rundb = _FakeRunDb([run])
        info_total = {
            "run-author": _user_stats("run-author"),
            "worker-user": _user_stats("worker-user"),
        }
        info_top_month = copy.deepcopy(info_total)

        new_deltas = delta_update_users.update_info(
            rundb,
            {},
            info_total,
            info_top_month,
            clear_stats=True,
        )

        self.assertEqual(new_deltas, {})
        self.assertTrue(rundb.get_unfinished_runs_for_stats_called)
        self.assertFalse(rundb.get_unfinished_runs_called)
        self.assertEqual(info_total["run-author"]["tests"], 0)
        self.assertEqual(info_top_month["run-author"]["tests"], 1)
        self.assertEqual(info_top_month["worker-user"]["games"], 6)
        self.assertEqual(info_top_month["worker-user"]["last_updated"], last_updated)
        self.assertGreater(info_top_month["worker-user"]["cpu_hours"], 0.0)

    def test_main_uses_db_backed_rundb_for_stats_rebuild(self):
        fake_rundb = unittest.mock.Mock()
        fake_rundb.deltas.find.return_value = []

        with (
            patch.object(
                delta_update_users, "RunDb", return_value=fake_rundb
            ) as run_db,
            patch.object(delta_update_users, "initialize_info", return_value=({}, {})),
            patch.object(delta_update_users, "update_info", return_value={}),
            patch.object(delta_update_users, "compute_games_rates"),
            patch.object(delta_update_users, "update_collection"),
            patch.object(delta_update_users, "cleanup_users"),
        ):
            old_argv = sys.argv
            try:
                sys.argv = ["delta_update_users.py"]
                delta_update_users.main()
            finally:
                sys.argv = old_argv

        run_db.assert_called_once_with(is_primary_instance=False)


if __name__ == "__main__":
    unittest.main()
