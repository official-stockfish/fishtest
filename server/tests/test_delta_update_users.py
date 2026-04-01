"""Test monthly contributor stats rebuild helpers."""

import copy
import unittest
from datetime import UTC, datetime

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


class DeltaUpdateUsersTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
