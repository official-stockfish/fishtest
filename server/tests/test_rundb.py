"""Test RunDb persistence and run lifecycle behavior."""

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


class CreateRunDBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
            close_conn=False,
        )

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
        )

    def setUp(self):
        random.seed()
        self.remote_addr = "127.0.0.1"
        self.rundb.runs.create_index(
            [("last_updated", DESCENDING), ("tc_base", DESCENDING)],
            name="finished_ltc_runs",
            partialFilterExpression={
                "finished": True,
                "tc_base": {"$gte": self.rundb.ltc_lower_bound},
                "deleted": False,
            },
        )
        self.rundb.runs.create_index(
            [("args.info", "text")],
            name="finished_runs_text",
            default_language="none",
            partialFilterExpression={"finished": True, "deleted": False},
        )
        self.chunk_size = 200
        self.worker_info = {
            "uname": "Linux 5.11.0-40-generic",
            "architecture": ["64bit", "ELF"],
            "concurrency": 1,
            "max_memory": 5702,
            "min_threads": 1,
            "username": "TestWorkerUser",
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
        self.rundb.runs.delete_many({"args.username": "TestRunDbUser"})

    def _create_test_run(
        self,
        *,
        tc: str = "10+0.01",
        finished: bool = False,
        tests_repo: str = "https://github.com/15408be06cfa0ff6/Stockfish",
        master_repo: str | None = None,
    ) -> str:
        num_tasks = 4
        num_games = num_tasks * self.chunk_size

        run_id = self.rundb.new_run(
            "master",
            "master",
            num_games,
            tc,
            tc,
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
            tests_repo=tests_repo,
            master_repo=master_repo,
            auto_purge=False,
            username="TestRunDbUser",
            start_time=datetime.now(UTC),
        )

        run = self.rundb.get_run(run_id)
        run["finished"] = finished
        task = {
            "num_games": self.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "pending": True,
            "active": True,
        }
        run["tasks"].append(task)
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return run_id

    def test_10_create_run(self):
        run_id_stc = self._create_test_run(finished=True)
        run_id_ltc = self._create_test_run()
        run = self.rundb.get_run(run_id_ltc)
        print(run["tasks"][0])
        self.assertTrue(run["tasks"][0]["active"])
        run["tasks"][0]["active"] = True
        run["tasks"][0]["worker_info"] = self.worker_info
        run["workers"] = run["cores"] = 1
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        self.assertTrue(self.rundb.get_run(run_id_stc)["finished"])

        for run in self.rundb.get_unfinished_runs():
            if run["args"]["username"] == "TestRunDbUser":
                print(run["args"])

    def test_11_get_unfinished_runs_keeps_default_projection_lightweight(self):
        run_id = self._create_test_run()
        run = self.rundb.get_run(run_id)
        run["args"]["spsa"] = {
            "iter": 7,
            "param_history": [[{"theta": 12.0, "c": 1.5}]],
        }
        run["bad_tasks"] = [
            {"num_games": 0, "stats": {"wins": 0, "draws": 0, "losses": 0}}
        ]
        run["tasks"][0]["worker_info"] = self.worker_info
        run["tasks"][0]["last_updated"] = datetime.now(UTC)
        run["tasks"][0]["stats"] = {
            "wins": 1,
            "draws": self.chunk_size - 2,
            "losses": 1,
            "crashes": 0,
        }
        run["workers"] = run["cores"] = 1
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        unfinished_run = next(
            run for run in self.rundb.get_unfinished_runs() if str(run["_id"]) == run_id
        )

        self.assertNotIn("tasks", unfinished_run)
        self.assertNotIn("bad_tasks", unfinished_run)
        self.assertEqual(unfinished_run["args"]["spsa"]["iter"], 7)
        self.assertNotIn("param_history", unfinished_run["args"]["spsa"])

    def test_12_get_unfinished_runs_for_stats_returns_task_projection(self):
        run_id = self._create_test_run()
        run = self.rundb.get_run(run_id)
        run["tasks"][0]["worker_info"] = self.worker_info
        run["tasks"][0]["last_updated"] = datetime.now(UTC)
        run["tasks"][0]["stats"] = {
            "wins": 2,
            "draws": self.chunk_size - 4,
            "losses": 2,
            "crashes": 0,
        }
        run["workers"] = run["cores"] = 1
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        unfinished_run = next(
            run
            for run in self.rundb.get_unfinished_runs_for_stats()
            if str(run["_id"]) == run_id
        )

        self.assertIn("tasks", unfinished_run)
        self.assertNotIn("results", unfinished_run)
        self.assertEqual(
            set(unfinished_run["args"].keys()),
            {"username", "tc", "threads"},
        )
        self.assertEqual(
            unfinished_run["tasks"][0]["worker_info"],
            {"username": self.worker_info["username"]},
        )
        self.assertIn("last_updated", unfinished_run["tasks"][0])
        self.assertIn("num_games", unfinished_run["tasks"][0])
        self.assertIn("stats", unfinished_run["tasks"][0])
        self.assertNotIn("active", unfinished_run["tasks"][0])

    def test_13_get_unfinished_runs_username_filter_is_pushed_to_query(self):
        self._create_test_run()
        self.addCleanup(
            self.rundb.runs.delete_many,
            {"args.username": "OtherRunDbUser"},
        )
        other_run_id = self.rundb.new_run(
            "master",
            "master",
            self.chunk_size * 4,
            "10+0.01",
            "10+0.01",
            "book.pgn",
            "10",
            1,
            "",
            "",
            info="The other patch",
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
            username="OtherRunDbUser",
            start_time=datetime.now(UTC),
        )
        other_run = self.rundb.get_run(other_run_id)
        other_run["tasks"].append(
            {
                "num_games": self.chunk_size,
                "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
                "pending": True,
                "active": True,
            }
        )
        self.rundb.buffer(other_run, priority=Prio.SAVE_NOW)

        unfinished_runs = list(self.rundb.get_unfinished_runs(username="TestRunDbUser"))
        unfinished_runs_for_stats = list(
            self.rundb.get_unfinished_runs_for_stats(username="TestRunDbUser")
        )

        self.assertTrue(unfinished_runs)
        self.assertEqual(len(unfinished_runs), 1)
        self.assertEqual(unfinished_runs[0]["args"]["username"], "TestRunDbUser")
        self.assertEqual(len(unfinished_runs_for_stats), 1)
        self.assertEqual(
            unfinished_runs_for_stats[0]["args"]["username"],
            "TestRunDbUser",
        )

    def test_14_new_run_canonicalizes_tests_repo(self):
        run_id = self._create_test_run(
            tests_repo="https://github.com/15408be06cfa0ff6/Stockfish/",
        )

        run = self.rundb.get_run(run_id)

        self.assertEqual(
            run["args"]["tests_repo"],
            "https://github.com/15408be06cfa0ff6/Stockfish",
        )

    def test_15_new_run_canonicalizes_master_repo(self):
        run_id = self._create_test_run(
            master_repo="https://github.com/official-stockfish/Stockfish/",
        )

        run = self.rundb.get_run(run_id)

        self.assertEqual(
            run["args"]["master_repo"],
            "https://github.com/official-stockfish/Stockfish",
        )

    def test_20_update_task(self):
        run_id = self._create_test_run()
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
        run_id = self._create_test_run()
        print("run_id: {}".format(run_id))
        run = self.rundb.get_run(run_id)
        run["finished"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        self.assertTrue(self.rundb.get_run(run_id)["finished"])

    def test_40_list_LTC(self):
        self._create_test_run(finished=True)
        self._create_test_run(tc="40+0.4", finished=True)
        finished_runs = self.rundb.get_finished_runs(limit=3, ltc_only=True)[0]
        self.assertTrue(finished_runs)
        for run in finished_runs:
            print(run["args"]["tc"])
            self.assertGreaterEqual(run["tc_base"], self.rundb.ltc_lower_bound)

    def test_41_finished_text_search_finds_matches_beyond_max_count_window(self):
        now = datetime.now(UTC)
        docs = []
        for index in range(1000):
            docs.append(
                {
                    "_id": ObjectId(),
                    "finished": True,
                    "deleted": False,
                    "args": {
                        "username": "TestRunDbUser",
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
                "deleted": False,
                "args": {
                    "username": "TestRunDbUser",
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
                    "deleted": False,
                    "args": {
                        "username": "TestRunDbUser",
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
                "deleted": False,
                "args": {
                    "username": "TestRunDbUser",
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
                "deleted": False,
                "args": {
                    "username": "TestRunDbUser",
                    "info": "regex path test needle here",
                },
                "last_updated": now - timedelta(minutes=10),
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "TestRunDbUser",
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
                "deleted": False,
                "args": {
                    "username": "TestSearchUser50",
                    "info": "user text combo needle",
                },
                "last_updated": now - timedelta(minutes=1),
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "TestOtherUser50",
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
                username="TestSearchUser50",
                text="needle",
                ltc_only=True,
                max_count=1000,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertEqual(finished_runs[0]["args"]["username"], "TestSearchUser50")
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
                    "username": "TestDeletedFilterUser",
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
                    "username": "TestDeletedFilterUser",
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
                username="TestDeletedFilterUser",
                max_count=1000,
            )
            self.assertEqual(count, 1)
            self.assertEqual(len(finished_runs), 1)
            self.assertEqual(finished_runs[0]["args"]["info"], "visible finished row")
        finally:
            self.rundb.runs.delete_many({"args.username": "TestDeletedFilterUser"})

    def test_52_finished_runs_default_limit_returns_all_matches(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "limit-zero-user",
                    "info": "limit zero visible row 1",
                },
                "last_updated": now,
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "limit-zero-user",
                    "info": "limit zero visible row 2",
                },
                "last_updated": now - timedelta(minutes=1),
                "tc_base": self.rundb.ltc_lower_bound,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                username="limit-zero-user",
            )
            self.assertEqual(count, 2)
            self.assertEqual(len(finished_runs), 2)
            self.assertEqual(
                [run["args"]["info"] for run in finished_runs],
                ["limit zero visible row 1", "limit zero visible row 2"],
            )
        finally:
            self.rundb.runs.delete_many({"args.username": "limit-zero-user"})

    def test_53_finished_runs_limit_zero_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "limit must be None or a positive integer"
        ):
            self.rundb.get_finished_runs(limit=0)

    def test_54_finished_runs_multi_username_default_limit_returns_all(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "limit-zero-user-a",
                    "info": "multi limit zero row a",
                },
                "last_updated": now,
                "tc_base": self.rundb.ltc_lower_bound,
            },
            {
                "_id": ObjectId(),
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "limit-zero-user-b",
                    "info": "multi limit zero row b",
                },
                "last_updated": now - timedelta(minutes=1),
                "tc_base": self.rundb.ltc_lower_bound,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                usernames=["limit-zero-user-a", "limit-zero-user-b"],
            )
            self.assertEqual(count, 2)
            self.assertEqual(len(finished_runs), 2)
            self.assertEqual(
                [run["args"]["username"] for run in finished_runs],
                ["limit-zero-user-a", "limit-zero-user-b"],
            )
        finally:
            self.rundb.runs.delete_many(
                {"args.username": {"$in": ["limit-zero-user-a", "limit-zero-user-b"]}}
            )

    def test_55_finished_runs_multi_username_missing_last_updated_is_safe(self):
        now = datetime.now(UTC)
        docs = [
            {
                "_id": "z-has-last-updated",
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "heap-safe-user-a",
                    "info": "timestamped row",
                },
                "last_updated": now,
            },
            {
                "_id": "a-missing-last-updated",
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "heap-safe-user-b",
                    "info": "missing timestamp row",
                },
            },
            {
                "_id": "b-none-last-updated",
                "finished": True,
                "deleted": False,
                "args": {
                    "username": "heap-safe-user-c",
                    "info": "none timestamp row",
                },
                "last_updated": None,
            },
        ]
        self.rundb.runs.insert_many(docs)
        try:
            finished_runs, count = self.rundb.get_finished_runs(
                usernames=[
                    "heap-safe-user-a",
                    "heap-safe-user-b",
                    "heap-safe-user-c",
                ],
                limit=3,
            )
            self.assertEqual(count, 3)
            self.assertEqual(
                [run["args"]["username"] for run in finished_runs],
                [
                    "heap-safe-user-a",
                    "heap-safe-user-b",
                    "heap-safe-user-c",
                ],
            )
        finally:
            self.rundb.runs.delete_many(
                {
                    "args.username": {
                        "$in": [
                            "heap-safe-user-a",
                            "heap-safe-user-b",
                            "heap-safe-user-c",
                        ]
                    }
                }
            )

    def test_90_delete_runs(self):
        for run in self.rundb.runs.find():
            if run["args"]["username"] == "TestRunDbUser" and "deleted" not in run:
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
