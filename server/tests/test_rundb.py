import sys
import unittest
from datetime import datetime, timezone

import util
from fishtest.api import WORKER_VERSION
from pymongo import DESCENDING

run_id = None


class CreateRunDBTest(unittest.TestCase):
    def setUp(self):
        self.stdout = sys.stdout
        sys.stdout = None
        self.rundb = util.get_rundb()
        self.rundb.runs.create_index(
            [("last_updated", DESCENDING), ("tc_base", DESCENDING)],
            name="finished_ltc_runs",
            partialFilterExpression={"finished": True, "tc_base": {"$gte": 40}},
        )
        self.chunk_size = 200
        self.worker_info = {
            "uname": "Linux 5.11.0-40-generic",
            "architecture": ["64bit", "ELF"],
            "concurrency": 1,
            "max_memory": 5702,
            "min_threads": 1,
            "username": "JoeUserWorker",
            "version": WORKER_VERSION,
            "python_version": [
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ],
            "gcc_version": [
                9,
                3,
                0,
            ],
            "unique_key": "unique key",
            "near_github_api_limit": False,
            "modified": True,
            "ARCH": "?",
            "nps": 0.0,
        }

    def tearDown(self):
        self.rundb.runs.delete_many({"args.username": "travis"})
        # Shutdown flush thread:
        self.rundb.stop()
        sys.stdout = self.stdout

    def test_10_create_run(self):
        global run_id
        # STC
        run_id_stc = self.rundb.new_run(
            "master",
            "master",
            100000,
            "10+0.01",
            "10+0.01",
            "book",
            10,
            1,
            "",
            "",
            username="travis",
            tests_repo="travis",
            start_time=datetime.now(timezone.utc),
        )
        run = self.rundb.get_run(run_id_stc)
        run["finished"] = True
        task = {
            "num_games": self.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "pending": True,
            "active": True,
        }
        run["tasks"].append(task)

        self.rundb.buffer(run, True)

        # LTC
        run_id = self.rundb.new_run(
            "master",
            "master",
            100000,
            "150+0.01",
            "150+0.01",
            "book",
            10,
            1,
            "",
            "",
            username="travis",
            tests_repo="travis",
            start_time=datetime.now(timezone.utc),
        )
        run = self.rundb.get_run(run_id)
        task = {
            "num_games": self.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "pending": True,
            "active": True,
        }
        run["tasks"].append(task)

        self.assertTrue(run["tasks"][0]["active"])
        run["tasks"][0]["active"] = True
        run["tasks"][0]["worker_info"] = self.worker_info
        run["workers"] = run["cores"] = 1

    def test_20_update_task(self):
        run = self.rundb.get_run(run_id)
        run["tasks"][0]["active"] = True
        run["tasks"][0]["worker_info"] = self.worker_info
        run["workers"] = run["cores"] = 1
        self.rundb.buffer(run, True)
        run = self.rundb.update_task(
            self.worker_info,
            run_id,
            0,
            {
                "wins": 1,
                "losses": 1,
                "draws": self.chunk_size - 3,
                "crashes": 0,
                "time_losses": 0,
            },
            {},
        )
        self.assertFalse(run["task_alive"])
        self.assertTrue("error" in run)
        run = self.rundb.update_task(
            self.worker_info,
            run_id,
            0,
            {
                "wins": 1,
                "losses": 1,
                "draws": self.chunk_size - 4,
                "crashes": 0,
                "time_losses": 0,
            },
            {},
        )
        self.assertFalse(run["task_alive"])
        self.assertTrue("info" in run)
        # revive task
        run_ = self.rundb.get_run(run_id)
        run_["tasks"][0]["active"] = True
        self.rundb.buffer(run_, True)
        run = self.rundb.update_task(
            self.worker_info,
            run_id,
            0,
            {
                "wins": 1,
                "losses": 1,
                "draws": self.chunk_size - 4,
                "crashes": 0,
                "time_losses": 0,
            },
            {},
        )
        self.assertEqual(run, {"task_alive": True})
        run = self.rundb.update_task(
            self.worker_info,
            run_id,
            0,
            {
                "wins": 1,
                "losses": 1,
                "draws": self.chunk_size - 2,
                "crashes": 0,
                "time_losses": 0,
            },
            {},
        )
        self.assertEqual(run, {"task_alive": False})

    def test_30_finish(self):
        run = self.rundb.get_run(run_id)
        run["finished"] = True
        self.rundb.buffer(run, True)

    def test_90_delete_runs(self):
        for run in self.rundb.runs.find():
            if run["args"]["username"] == "travis" and "deleted" not in run:
                run["deleted"] = True
                run["finished"] = True
                for w in run["tasks"]:
                    w["pending"] = False
                self.rundb.buffer(run, True)


if __name__ == "__main__":
    unittest.main()
