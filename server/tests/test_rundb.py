import random
import sys
import unittest
from datetime import UTC, datetime

import test_support
from pymongo import DESCENDING

from fishtest.api import WORKER_VERSION
from fishtest.run_cache import Prio
from fishtest.spsa_handler import _pack_flips, _unpack_flips

run_id = None


class CreateRunDBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()

    def setUp(self):
        random.seed()
        self.remote_addr = "127.0.0.1"
        self.rundb.runs.create_index(
            [("last_updated", DESCENDING), ("tc_base", DESCENDING)],
            name="finished_ltc_runs",
            partialFilterExpression={
                "finished": True,
                "tc_base": {"$gte": self.rundb.ltc_lower_bound},
            },
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
            "unique_key": "amaya-5a28-4b7d-b27b-d78d97ecf11a",
            "near_github_api_limit": False,
            "modified": True,
            "ARCH": "?",
            "nps": 0.0,
            "remote_addr": self.remote_addr,
        }

    def tearDown(self):
        self.rundb.runs.delete_many({"args.username": "travis"})

    def test_10_create_run(self):
        global run_id
        # STC
        num_tasks = 4
        num_games = num_tasks * self.chunk_size

        run_id_stc = self.rundb.new_run(
            "master",
            "master",
            num_games,
            "10+0.01",
            "10+0.01",
            "book.pgn",
            "10",
            1,
            "",
            "",
            info="The ultimate patch",
            resolved_base="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            resolved_new="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            msg_base="Bad stuff",
            msg_new="Super stuff",
            base_signature="123456",
            new_signature="654321",
            base_nets=["nn-0000000000a0.nnue"],
            new_nets=["nn-0000000000a0.nnue", "nn-0000000000a1.nnue"],
            rescheduled_from="653db116cc309ae839563103",
            tests_repo="https://github.com/15408be06cfa0ff6/Stockfish",
            auto_purge=False,
            username="travis",
            start_time=datetime.now(UTC),
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

        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        # LTC
        run_id = self.rundb.new_run(
            "master",
            "master",
            num_games,
            "10+0.01",
            "10+0.01",
            "book.pgn",
            "10",
            1,
            "",
            "",
            info="The ultimate patch",
            resolved_base="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            resolved_new="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            msg_base="Bad stuff",
            msg_new="Super stuff",
            base_signature="123456",
            new_signature="654321",
            base_nets=["nn-0000000000a0.nnue"],
            new_nets=["nn-0000000000a0.nnue", "nn-0000000000a1.nnue"],
            rescheduled_from="653db116cc309ae839563103",
            tests_repo="https://github.com/15408be06cfa0ff6/Stockfish",
            auto_purge=False,
            username="travis",
            start_time=datetime.now(UTC),
        )
        run = self.rundb.get_run(run_id)
        task = {
            "num_games": self.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "pending": True,
            "active": True,
        }
        run["tasks"].append(task)

        print(run["tasks"][0])
        self.assertTrue(run["tasks"][0]["active"])
        run["tasks"][0]["active"] = True
        run["tasks"][0]["worker_info"] = self.worker_info
        run["workers"] = run["cores"] = 1

        for run in self.rundb.get_unfinished_runs():
            if run["args"]["username"] == "travis":
                print(run["args"])

    def test_20_update_task(self):
        run = self.rundb.get_run(run_id)
        run["tasks"][0]["active"] = True
        run["tasks"][0]["worker_info"] = self.worker_info
        run["workers"] = run["cores"] = 1
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        self.rundb.connections_counter[self.remote_addr] = 1
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
        self.rundb.connections_counter[self.remote_addr] = 1
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
        self.rundb.buffer(run_, priority=Prio.SAVE_NOW)
        self.rundb.connections_counter[self.remote_addr] = 1
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
        print("run_id: {}".format(run_id))
        run = self.rundb.get_run(run_id)
        run["finished"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

    def test_40_list_LTC(self):
        finished_runs = self.rundb.get_finished_runs(limit=3, ltc_only=True)[0]
        for run in finished_runs:
            print(run["args"]["tc"])

    def test_90_delete_runs(self):
        for run in self.rundb.runs.find():
            if run["args"]["username"] == "travis" and "deleted" not in run:
                print("del ")
                run["deleted"] = True
                run["finished"] = True
                for w in run["tasks"]:
                    w["pending"] = False
                self.rundb.buffer(run, priority=Prio.SAVE_NOW)

    def test_flips(self):
        random.seed(0)
        for _ in range(0, 100):
            L = random.randint(0, 1000)
            a = [random.choice((-1, 1)) for _ in range(0, L)]
            b = _pack_flips(a)
            self.assertTrue(isinstance(b, bytes))
            c = _unpack_flips(b, length=L)
            self.assertEqual(a, c)


if __name__ == "__main__":
    unittest.main()
