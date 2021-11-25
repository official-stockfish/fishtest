import base64
import datetime
import sys
import unittest
import zlib

from fishtest.api import WORKER_VERSION, ApiView
from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.testing import DummyRequest
from util import get_rundb


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.rundb = get_rundb()

        # Set up a run
        num_tasks = 4
        num_games = num_tasks * self.rundb.chunk_size
        run_id = self.rundb.new_run(
            "master",
            "master",
            num_games,
            "10+0.01",
            "10+0.01",
            "book",
            10,
            1,
            "",
            "",
            username="travis",
            tests_repo="travis",
            start_time=datetime.datetime.utcnow(),
        )
        self.run_id = str(run_id)
        run = self.rundb.get_run(self.run_id)
        run["approved"] = True

        # Set up a task
        self.task_id = 0

        task = {
            "num_games": self.rundb.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "active": True,
        }

        run["tasks"].append(task)

        self.rundb.buffer(run, True)

        # Set up an API user (a worker)
        self.username = "JoeUserWorker"
        self.password = "secret"
        self.unique_key = "unique key"
        self.remote_addr = "127.0.0.1"
        self.concurrency = 7

        self.worker_info = {
            "uname": "Linux 5.11.0-40-generic",
            "architecture": ["64bit", "ELF"],
            "concurrency": self.concurrency,
            "max_memory": 5702,
            "min_threads": 1,
            "username": self.username,
            "version": "{}:{}.{}.{}".format(
                WORKER_VERSION,
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ),
            "gcc_version": "9.3.0",
            "unique_key": "unique key",
            "rate": {"limit": 5000, "remaining": 5000},
        }
        run["tasks"][0]["worker_info"] = self.worker_info
        self.rundb.userdb.create_user(self.username, self.password, "email@email.email")
        user = self.rundb.userdb.get_user(self.username)
        user["blocked"] = False
        user["machine_limit"] = 50
        self.rundb.userdb.save_user(user)

        self.rundb.userdb.user_cache.insert_one(
            {"username": self.username, "cpu_hours": 0}
        )
        self.rundb.userdb.flag_cache.insert_one(
            {"ip": self.remote_addr, "country_code": "??"}
        )

    @classmethod
    def tearDownClass(self):
        self.rundb.runs.delete_one({"_id": self.run_id})
        self.rundb.userdb.users.delete_many({"username": self.username})
        self.rundb.userdb.user_cache.delete_many({"username": self.username})
        self.rundb.userdb.flag_cache.delete_many({"ip": self.remote_addr})
        self.rundb.stop()
        self.rundb.runs.drop()

    def build_json_request(self, json_body):
        return DummyRequest(
            rundb=self.rundb,
            userdb=self.rundb.userdb,
            actiondb=self.rundb.actiondb,
            remote_addr=self.remote_addr,
            json_body=json_body,
        )

    def invalid_password_request(self):
        return self.build_json_request(
            {"username": self.username, "password": "wrong password"}
        )

    def correct_password_request(self, json_body={}):
        return self.build_json_request(
            {
                "username": self.username,
                "password": self.password,
                "unique_key": "unique key",
                **json_body,
            }
        )

    def test_get_active_runs(self):
        request = DummyRequest(rundb=self.rundb)
        response = ApiView(request).active_runs()
        self.assertTrue(self.run_id in response)

    def test_get_run(self):
        request = DummyRequest(rundb=self.rundb, matchdict={"id": self.run_id})
        response = ApiView(request).get_run()
        self.assertEqual(self.run_id, response["_id"])

    def test_get_elo(self):
        request = DummyRequest(rundb=self.rundb, matchdict={"id": self.run_id})
        response = ApiView(request).get_elo()
        self.assertTrue(not response)

    def test_request_task(self):
        with self.assertRaises(HTTPUnauthorized):
            response = ApiView(self.invalid_password_request()).update_task()
            self.assertTrue("error" in response)

        run = self.rundb.get_run(self.run_id)
        self.assertEqual(run.get("cores"), None)

        run["tasks"][self.task_id] = {
            "num_games": self.rundb.chunk_size,
            "stats": {"wins": 0, "draws": 0, "losses": 0, "crashes": 0},
            "active": False,
        }
        self.rundb.buffer(run, True)
        request = self.correct_password_request({"worker_info": self.worker_info})
        response = ApiView(request).request_task()
        self.assertEqual(self.run_id, response["run"]["_id"])
        self.assertNotEqual(self.task_id, response["task_id"])

        run = self.rundb.get_run(self.run_id)
        self.assertEqual(run["cores"], self.concurrency)
        task = run["tasks"][response["task_id"]]
        self.assertTrue(task["active"])

    def test_update_task(self):
        self.assertFalse(self.rundb.get_run(self.run_id)["results_stale"])

        # Request fails if username/password is invalid
        with self.assertRaises(HTTPUnauthorized):
            response = ApiView(self.invalid_password_request()).update_task()
            self.assertTrue("error" in response)

        # Prepare a pending task that will be updated
        run = self.rundb.get_run(self.run_id)
        run["tasks"][self.task_id] = {
            "num_games": self.rundb.chunk_size,
            "active": True,
        }
        run["finished"] = False
        run["tasks"][self.task_id]["worker_info"] = self.worker_info

        if run["args"].get("spsa"):
            del run["args"]["spsa"]
        self.rundb.buffer(run, True)

        # Calling /api/request_task assigns this task to the worker
        request = self.correct_password_request({"worker_info": self.worker_info})
        response = ApiView(request).request_task()
        self.assertEqual(response["run"]["_id"], str(run["_id"]))

        # Task is active after calling /api/update_task with the first set of results
        request = self.correct_password_request(
            {
                "worker_info": self.worker_info,
                "run_id": self.run_id,
                "task_id": self.task_id,
                "stats": {
                    "wins": 2,
                    "draws": 0,
                    "losses": 0,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [0, 0, 0, 0, 1],
                },
            }
        )
        response = ApiView(request).update_task()
        self.assertTrue(response["task_alive"])
        self.assertFalse(self.rundb.get_run(self.run_id)["results_stale"])

        # Task is still active
        cs = self.rundb.chunk_size
        w, d, l = cs // 2 - 10, cs // 2, 0
        request.json_body["stats"] = {
            "wins": w,
            "draws": d,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, d // 2, 0, w // 2],
        }
        response = ApiView(request).update_task()
        self.assertTrue(response["task_alive"])
        self.assertFalse(self.rundb.get_run(self.run_id)["results_stale"])

        # Task is still active. Odd update.
        request.json_body["stats"] = {
            "wins": w + 1,
            "draws": d,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, d // 2, 0, w // 2],
        }
        response = ApiView(request).update_task()
        self.assertFalse(response["task_alive"])

        request.json_body["stats"] = {
            "wins": w + 2,
            "draws": d,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, d // 2, 0, w // 2 + 1],
        }
        response = ApiView(request).update_task()
        self.assertFalse(response["task_alive"])
        # revive the task
        run["tasks"][self.task_id]["active"] = True
        self.rundb.buffer(run, True)

        request.json_body["stats"] = {
            "wins": w + 2,
            "draws": d,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, d // 2, 0, w // 2 + 1],
        }
        response = ApiView(request).update_task()
        self.assertTrue(response["task_alive"])
        # Go back in time
        request.json_body["stats"] = {
            "wins": w,
            "draws": d,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, d // 2, 0, w // 2],
        }
        response = ApiView(request).update_task()
        self.assertFalse(response["task_alive"])

        # revive the task
        run["tasks"][self.task_id]["active"] = True
        self.rundb.buffer(run, True)

        # Task is finished when calling /api/update_task with results where the number of
        # games played is the same as the number of games in the task
        task_num_games = run["tasks"][self.task_id]["num_games"]
        request.json_body["stats"] = {
            "wins": task_num_games,
            "draws": 0,
            "losses": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": [0, 0, 0, 0, task_num_games // 2],
        }
        response = ApiView(request).update_task()
        self.assertFalse(self.rundb.get_run(self.run_id)["results_stale"])
        self.assertFalse(response["task_alive"])
        run = self.rundb.get_run(self.run_id)
        task = run["tasks"][self.task_id]
        self.assertFalse(task["active"])

    def test_failed_task(self):
        request = self.correct_password_request({"run_id": self.run_id, "task_id": 0})
        response = ApiView(request).failed_task()
        self.assertTrue(not response)

        run = self.rundb.get_run(self.run_id)
        run["tasks"][self.task_id]["active"] = True
        run["tasks"][self.task_id]["worker_info"] = self.worker_info
        self.rundb.buffer(run, True)
        run = self.rundb.get_run(self.run_id)
        self.assertTrue(run["tasks"][self.task_id]["active"])

        request = self.correct_password_request(
            {"run_id": self.run_id, "task_id": self.task_id}
        )
        response = ApiView(request).failed_task()
        self.assertTrue(not response)
        self.assertFalse(run["tasks"][self.task_id]["active"])

    def test_stop_run(self):
        with self.assertRaises(HTTPUnauthorized):
            response = ApiView(self.invalid_password_request()).stop_run()
            self.assertTrue("error" in response)

        run = self.rundb.get_run(self.run_id)
        self.assertFalse(run["finished"])
        run["tasks"][self.task_id]["worker_info"] = self.worker_info
        self.rundb.buffer(run, True)

        request = self.correct_password_request(
            {"run_id": self.run_id, "task_id": self.task_id, "message": "API request"}
        )
        response = ApiView(request).stop_run()
        self.assertTrue("error" in response)

        self.rundb.userdb.user_cache.update_one(
            {"username": self.username}, {"$set": {"cpu_hours": 10000}}
        )
        user = self.rundb.userdb.user_cache.find_one({"username": self.username})
        self.assertTrue(user["cpu_hours"] == 10000)

        response = ApiView(request).stop_run()
        self.assertTrue(not response)

        run = self.rundb.get_run(self.run_id)
        self.assertTrue(run["finished"])
        self.assertEqual(run["stop_reason"][-13:-2], "API request")

        run["finished"] = False
        self.rundb.buffer(run, True)

    def test_upload_pgn(self):
        pgn_text = "1. e4 e5 2. d4 d5"
        request = self.correct_password_request(
            {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "pgn": base64.b64encode(
                    zlib.compress(pgn_text.encode("utf-8"))
                ).decode(),
            }
        )
        response = ApiView(request).upload_pgn()
        self.assertTrue(not response)

        pgn_filename_prefix = "{}-{}".format(self.run_id, self.task_id)
        pgn = self.rundb.get_pgn(pgn_filename_prefix)
        self.assertEqual(pgn, pgn_text)
        self.rundb.pgndb.delete_one({"run_id": pgn_filename_prefix})

    def test_request_spsa(self):
        request = self.correct_password_request({"run_id": self.run_id, "task_id": 0})
        response = ApiView(request).request_spsa()
        self.assertFalse(response["task_alive"])

        run = self.rundb.get_run(self.run_id)
        run["args"]["spsa"] = {
            "iter": 1,
            "num_iter": 10,
            "alpha": 1,
            "gamma": 1,
            "A": 1,
            "params": [
                {"name": "param name", "a": 1, "c": 1, "theta": 1, "min": 0, "max": 100}
            ],
        }
        run["tasks"][self.task_id]["active"] = True
        self.rundb.buffer(run, True)
        request = self.correct_password_request(
            {"run_id": self.run_id, "task_id": self.task_id}
        )
        response = ApiView(request).request_spsa()
        self.assertTrue(response["task_alive"])
        self.assertTrue(response["w_params"] is not None)
        self.assertTrue(response["b_params"] is not None)

    def test_request_version(self):
        with self.assertRaises(HTTPUnauthorized):
            response = ApiView(self.invalid_password_request()).request_version()
            self.assertTrue("error" in response)

        response = ApiView(self.correct_password_request()).request_version()
        self.assertEqual(WORKER_VERSION, response["version"])

    def test_beat(self):
        with self.assertRaises(HTTPUnauthorized):
            response = ApiView(self.invalid_password_request()).beat()
            self.assertTrue("error" in response)

        request = self.correct_password_request(
            {"run_id": self.run_id, "task_id": self.task_id}
        )
        response = ApiView(request).beat()
        print(response)
        self.assertEqual("JoeUserWorker-7cores-unique key", response)


class TestRunFinished(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.rundb = get_rundb()

        # Set up a run with 2 tasks
        num_games = 2 * self.rundb.chunk_size
        run_id = self.rundb.new_run(
            "master",
            "master",
            num_games,
            "10+0.01",
            "10+0.01",
            "book",
            10,
            1,
            "",
            "",
            username="travis",
            tests_repo="travis",
            start_time=datetime.datetime.utcnow(),
        )
        self.run_id = str(run_id)
        run = self.rundb.get_run(self.run_id)
        run["approved"] = True

        # Set up a user
        self.username = "JoeUserWorker2"
        self.password = "secret"
        self.remote_addr = "127.0.0.1"
        self.concurrency = 7
        self.worker_info = {
            "uname": "Linux 5.11.0-40-generic",
            "architecture": ["64bit", "ELF"],
            "concurrency": self.concurrency,
            "max_memory": 5702,
            "min_threads": 1,
            "username": self.username,
            "version": "{}:{}.{}.{}".format(
                WORKER_VERSION,
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ),
            "gcc_version": "9.3.0",
            "unique_key": "unique key",
            "rate": {"limit": 5000, "remaining": 5000},
        }

        self.rundb.userdb.create_user(self.username, self.password, "email@email.email")
        user = self.rundb.userdb.get_user(self.username)
        user["blocked"] = False
        user["machine_limit"] = 50
        self.rundb.userdb.save_user(user)
        self.rundb.userdb.user_cache.insert_one(
            {"username": self.username, "cpu_hours": 0}
        )
        self.rundb.userdb.flag_cache.insert_one(
            {"ip": self.remote_addr, "country_code": "??"}
        )

    @classmethod
    def tearDownClass(self):
        self.rundb.userdb.users.delete_many({"username": self.username})
        self.rundb.userdb.user_cache.delete_many({"username": self.username})
        self.rundb.stop()
        self.rundb.runs.drop()

    def build_json_request(self, json_body):
        return DummyRequest(
            rundb=self.rundb,
            userdb=self.rundb.userdb,
            actiondb=self.rundb.actiondb,
            remote_addr=self.remote_addr,
            json_body=json_body,
        )

    def correct_password_request(self, json_body={}):
        return self.build_json_request(
            {"username": self.username, "password": self.password, **json_body}
        )

    def test_auto_purge_runs(self):
        run = self.rundb.get_run(self.run_id)
        num_games = 600
        run["args"]["num_games"] = num_games
        self.rundb.buffer(run, True)

        # Request task 1 of 2
        request = self.correct_password_request({"worker_info": self.worker_info})
        response = ApiView(request).request_task()
        self.assertEqual(response["run"]["_id"], str(run["_id"]))
        self.assertEqual(response["task_id"], 0)
        task1 = self.rundb.get_run(self.run_id)["tasks"][0]
        task_size1 = task1["num_games"]

        # Request task 2 of 2
        request = self.correct_password_request({"worker_info": self.worker_info})
        response = ApiView(request).request_task()
        self.assertEqual(response["run"]["_id"], str(run["_id"]))
        self.assertEqual(response["task_id"], 1)
        task2 = self.rundb.get_run(self.run_id)["tasks"][1]
        task_size2 = task2["num_games"]
        task_start2 = task2["start"]

        self.assertEqual(task_start2, task_size1)

        # Finish task 1 of 2
        n_wins = task_size1 // 5
        n_losses = task_size1 // 5
        n_draws = task_size1 - n_wins - n_losses

        request = self.correct_password_request(
            {
                "worker_info": self.worker_info,
                "run_id": self.run_id,
                "task_id": 0,
                "stats": {
                    "wins": n_wins,
                    "draws": n_draws,
                    "losses": n_losses,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [n_losses // 2, 0, n_draws // 2, 0, n_wins // 2],
                },
            }
        )
        response = ApiView(request).update_task()
        self.assertFalse(response["task_alive"])
        run = self.rundb.get_run(self.run_id)
        self.assertFalse(run["finished"])

        # Finish task 2 of 2
        n_wins = task_size2 // 5
        n_losses = task_size2 // 5
        n_draws = task_size2 - n_wins - n_losses

        request = self.correct_password_request(
            {
                "worker_info": self.worker_info,
                "run_id": self.run_id,
                "task_id": 1,
                "stats": {
                    "wins": n_wins,
                    "draws": n_draws,
                    "losses": n_losses,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [n_losses // 2, 0, n_draws // 2, 0, n_wins // 2],
                },
            }
        )
        response = ApiView(request).update_task()
        self.assertFalse(response["task_alive"])

        # The run should be marked as finished after the last task completes
        run = self.rundb.get_run(self.run_id)
        self.assertTrue(run["finished"])
        self.assertFalse(run["results_stale"])
        self.assertTrue(all([not t["active"] for t in run["tasks"]]))
        self.assertTrue("Total: {}".format(num_games) in run["results_info"]["info"][1])


if __name__ == "__main__":
    unittest.main()
