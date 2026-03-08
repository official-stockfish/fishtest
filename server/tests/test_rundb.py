import random
import sys
import unittest
from datetime import UTC, datetime, timedelta

import test_support
from bson.objectid import ObjectId
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
        self.rundb.runs.create_index(
            [("args.info", "text")],
            name="finished_runs_text",
            default_language="none",
            partialFilterExpression={"finished": True},
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

    def test_41_finished_text_search_finds_matches_beyond_max_count_window(self):
        now = datetime.now(UTC)
        docs = []
        for index in range(1000):
            docs.append(
                {
                    "_id": ObjectId(),
                    "finished": True,
                    "args": {
                        "username": "travis",
                        "info": f"recent scope row {index}",
                    },
                    "last_updated": now - timedelta(minutes=index),
                    "tc_base": self.rundb.ltc_lower_bound,
                }
            )
        docs.append(
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "travis",
                    "info": "needle outside cap",
                },
                "last_updated": now - timedelta(minutes=1001),
                "tc_base": self.rundb.ltc_lower_bound,
            }
        )

        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                limit=10,
                text="needle",
                ltc_only=True,
                max_count=1000,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertIn("needle outside cap", finished_runs[0]["args"]["info"])
        finally:
            self.rundb.runs.delete_many(
                {"args.info": {"$regex": "^(recent scope row|needle outside cap)"}}
            )

    def test_42_finished_text_search_finds_matches_beyond_explicit_cap(self):
        now = datetime.now(UTC)
        docs = []
        for index in range(3):
            docs.append(
                {
                    "_id": ObjectId(),
                    "finished": True,
                    "args": {
                        "username": "travis",
                        "info": f"explicit cap row {index}",
                    },
                    "last_updated": now - timedelta(minutes=index),
                    "tc_base": self.rundb.ltc_lower_bound,
                }
            )
        docs.append(
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "travis",
                    "info": "explicit needle outside cap",
                },
                "last_updated": now - timedelta(minutes=4),
                "tc_base": self.rundb.ltc_lower_bound,
            }
        )

        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                limit=10,
                text="needle",
                ltc_only=True,
                max_count=3,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertIn(
                "explicit needle outside cap", finished_runs[0]["args"]["info"]
            )
        finally:
            self.rundb.runs.delete_many(
                {
                    "args.info": {
                        "$regex": "^(explicit cap row|explicit needle outside cap)"
                    }
                }
            )

    def test_43_text_search_to_info_regex_single_word(self):
        result = self.rundb._text_search_to_info_regex("ltc")
        self.assertEqual(result, r"\bltc\b")

    def test_44_text_search_to_info_regex_multiple_words(self):
        result = self.rundb._text_search_to_info_regex("ltc lmr")
        self.assertEqual(result, r"\bltc\b|\blmr\b")

    def test_45_text_search_to_info_regex_quoted_phrase(self):
        result = self.rundb._text_search_to_info_regex('"branch search"')
        self.assertEqual(result, r"branch\ search")

    def test_46_text_search_to_info_regex_negation_returns_none(self):
        result = self.rundb._text_search_to_info_regex("-master ltc")
        self.assertIsNone(result)

    def test_47_text_search_to_info_regex_empty_returns_none(self):
        self.assertIsNone(self.rundb._text_search_to_info_regex(""))
        self.assertIsNone(self.rundb._text_search_to_info_regex("   "))

    def test_48_text_search_to_info_regex_special_chars_escaped(self):
        result = self.rundb._text_search_to_info_regex("a+b")
        self.assertEqual(result, r"\ba\+b\b")

    def test_49_finished_text_only_search_uses_text_index(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "travis",
                    "info": "regex path test needle here",
                },
                "last_updated": now - timedelta(minutes=10),
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "travis",
                    "info": "regex path test other row",
                },
                "last_updated": now - timedelta(minutes=5),
                "tc_base": self.rundb.ltc_lower_bound,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                limit=10,
                text="needle",
                ltc_only=True,
                max_count=1000,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertIn("needle", finished_runs[0]["args"]["info"])
        finally:
            self.rundb.runs.delete_many({"args.info": {"$regex": "^regex path test"}})

    def test_50_finished_username_plus_text_uses_regex_path(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "searchuser50",
                    "info": "user text combo needle",
                },
                "last_updated": now - timedelta(minutes=1),
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "args": {
                    "username": "otheruser50",
                    "info": "user text combo needle",
                },
                "last_updated": now - timedelta(minutes=2),
                "tc_base": self.rundb.ltc_lower_bound,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                limit=10,
                username="searchuser50",
                text="needle",
                ltc_only=True,
                max_count=1000,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertEqual(finished_runs[0]["args"]["username"], "searchuser50")
        finally:
            self.rundb.runs.delete_many({"args.info": {"$regex": "^user text combo"}})

    def test_51_finished_runs_filters_deleted_rows_after_query(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "deleted-filter-user",
                    "info": "visible finished row",
                },
                "last_updated": now - timedelta(minutes=1),
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": True,
                "args": {
                    "username": "deleted-filter-user",
                    "info": "deleted finished row",
                },
                "last_updated": now,
                "tc_base": self.rundb.ltc_lower_bound,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                limit=10,
                username="deleted-filter-user",
                max_count=1000,
            )
            self.assertEqual(count, 2)
            self.assertEqual(len(finished_runs), 1)
            self.assertEqual(finished_runs[0]["args"]["info"], "visible finished row")
        finally:
            self.rundb.runs.delete_many({"args.username": "deleted-filter-user"})

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
