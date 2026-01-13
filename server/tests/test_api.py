# ruff: noqa: ANN201, ANN206, B904, D100, D101, D102, E501, EM101, EM102, INP001, PLC0415, PT009, S105, S106, TRY003

import base64
import copy
import gzip
import io
import sys
import unittest
from datetime import UTC, datetime

import test_support

from fishtest.run_cache import Prio

try:
    from fishtest.api import WORKER_VERSION
    from fishtest.util import worker_name
except ModuleNotFoundError:  # pragma: no cover
    WORKER_VERSION = None  # type: ignore[assignment]
    worker_name = None  # type: ignore[assignment]


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Skips cleanly if FastAPI/TestClient (and its deps like httpx) aren't available.
        test_support.require_fastapi()

        if WORKER_VERSION is None:  # pragma: no cover
            raise unittest.SkipTest(
                "Server HTTP dependencies missing (fishtest.api); skipping FastAPI HTTP tests",
            )

        cls.rundb = test_support.get_rundb()

        cls.username = "JoeUserWorker"
        cls.password = "secret"
        cls.unique_key = "amaya-5a28-4b7d-b27b-d78d97ecf11a"

        # Create the API user (worker).
        cls.rundb.userdb.create_user(
            cls.username,
            cls.password,
            "email@email.email",
            "https://github.com/official-stockfish/Stockfish",
        )
        user = cls.rundb.userdb.get_user(cls.username)
        user["pending"] = False
        user["machine_limit"] = 50
        cls.rundb.userdb.save_user(user)

        cls.rundb.userdb.user_cache.insert_one(
            {"username": cls.username, "cpu_hours": 0},
        )

        cls.client = test_support.make_test_client(
            rundb=cls.rundb,
            include_api=True,
            include_views=False,
        )

        cls.worker_info = {
            "uname": "Linux",
            "architecture": ["64bit", "ELF"],
            "concurrency": 7,
            "max_memory": 5702,
            "min_threads": 1,
            "username": cls.username,
            "version": WORKER_VERSION,
            "python_version": [
                sys.version_info.major,
                sys.version_info.minor,
                sys.version_info.micro,
            ],
            "gcc_version": [9, 3, 0],
            "compiler": "g++",
            "unique_key": cls.unique_key,
            "modified": True,
            "near_github_api_limit": False,
            "ARCH": "?",
            "nps": 0.0,
            "worker_arch": "x86-64-avx512",
        }

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
        )

    def setUp(self):
        self._reset_runs()

    def _reset_runs(self) -> None:
        self.rundb.runs.delete_many({})
        if hasattr(self.rundb, "run_cache"):
            self.rundb.run_cache.flush_all()
            self.rundb.run_cache.run_cache.clear()
        self.rundb.unfinished_runs.clear()
        self.rundb.wtt_map.clear()
        self.rundb.worker_runs.clear()
        self.rundb.connections_counter.clear()

    def _payload(self, *, password: str, worker_info: dict | None = None) -> dict:
        return {
            "password": password,
            "worker_info": copy.deepcopy(worker_info or self.worker_info),
        }

    def _assert_worker_error_response(
        self,
        response,
        *,
        status_code: int,
        path: str,
        contains: str | None = None,
    ) -> dict:
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertTrue(isinstance(body.get("duration"), (int, float)))
        self.assertIn("error", body)
        self.assertTrue(body["error"].startswith(f"{path}:"))
        if contains is not None:
            self.assertIn(contains, body["error"])
        return body

    def _create_run(self, *, num_games: int = 400) -> str:
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
            info="Worker API test run",
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

    def _create_run_with_task(self, *, spsa: bool = False) -> tuple[str, int]:
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        if spsa:
            run["args"]["spsa"] = {
                "iter": 1,
                "num_iter": 10,
                "alpha": 1,
                "gamma": 1,
                "A": 1,
                "params": [
                    {
                        "name": "param name",
                        "a": 1,
                        "c": 1,
                        "theta": 1,
                        "min": 0,
                        "max": 100,
                    },
                ],
            }
        worker_info = copy.deepcopy(self.worker_info)
        worker_info["remote_addr"] = "127.0.0.1"
        worker_info["country_code"] = "US"
        task = {
            "num_games": 200,
            "stats": {
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "crashes": 0,
                "time_losses": 0,
                "pentanomial": [0, 0, 0, 0, 0],
            },
            "active": True,
            "last_updated": datetime.now(UTC),
            "start": 0,
            "worker_info": worker_info,
        }
        run["tasks"].append(task)
        run["workers"] = 1
        run["cores"] = worker_info["concurrency"]
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return str(run_id), 0

    def _build_pgn_payload(self, run_id: str, task_id: int) -> str:
        pgn_text = "1. e4 e5 2. d4 d5"
        with io.BytesIO() as gz_buffer:
            with gzip.GzipFile(
                filename=f"{run_id}-{task_id}.pgn.gz",
                mode="wb",
                fileobj=gz_buffer,
            ) as gz:
                gz.write(pgn_text.encode())
            return base64.b64encode(gz_buffer.getvalue()).decode()

    def _stop_all_runs(self) -> None:
        runs = self.rundb.runs.find({})
        for run in runs:
            run_ = self.rundb.get_run(str(run["_id"]))
            run_["finished"] = True
            for task in run_["tasks"]:
                task["active"] = False
            self.rundb.buffer(run_, priority=Prio.SAVE_NOW)
        if hasattr(self.rundb, "run_cache"):
            self.rundb.run_cache.flush_all()

    def test_request_version_ok(self):
        response = self.client.post(
            "/api/request_version",
            json=self._payload(password=self.password),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], WORKER_VERSION)
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_request_version_wrong_password(self):
        response = self.client.post(
            "/api/request_version",
            json=self._payload(password="wrong password"),
        )
        self._assert_worker_error_response(
            response,
            status_code=401,
            path="/api/request_version",
        )

    def test_request_version_invalid_json_body(self):
        response = self.client.post(
            "/api/request_version",
            data=b"{",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        self.assertTrue(body["error"].startswith("/api/request_version:"))
        self.assertIn("request is not json encoded", body["error"])
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_worker_endpoints_wrong_password(self):
        endpoints = [
            "/api/request_version",
            "/api/request_task",
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
            "/api/worker_log",
        ]
        for path in endpoints:
            response = self.client.post(
                path,
                json=self._payload(password="wrong password"),
            )
            self._assert_worker_error_response(
                response,
                status_code=401,
                path=path,
            )

    def test_worker_endpoints_missing_password_is_validation_error(self):
        endpoints = [
            "/api/request_version",
            "/api/request_task",
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
            "/api/worker_log",
        ]
        for path in endpoints:
            response = self.client.post(
                path,
                json={"worker_info": copy.deepcopy(self.worker_info)},
            )
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
            )

    def test_worker_endpoints_missing_worker_info_is_validation_error(self):
        endpoints = [
            "/api/request_version",
            "/api/request_task",
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
            "/api/worker_log",
        ]
        for path in endpoints:
            response = self.client.post(
                path,
                json={"password": self.password},
            )
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
            )

    def test_worker_endpoints_invalid_json_body(self):
        endpoints = [
            "/api/request_version",
            "/api/request_task",
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
            "/api/worker_log",
        ]
        for path in endpoints:
            response = self.client.post(
                path,
                data=b"{",
                headers={"content-type": "application/json"},
            )
            self.assertEqual(response.status_code, 400)
            body = response.json()
            self.assertIn("error", body)
            self.assertTrue(body["error"].startswith(f"{path}:"))
            self.assertIn("request is not json encoded", body["error"])
            self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_invalid_arch(self):
        worker_info = copy.deepcopy(self.worker_info)
        worker_info["worker_arch"] = "bad_arch"

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password, worker_info=worker_info),
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("error", body)
        self.assertTrue(body["error"].startswith("/api/request_task:"))
        self.assertIn("bad_arch", body["error"])
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_request_task_no_runs_returns_task_waiting(self):
        self._reset_runs()
        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("task_waiting", body)
        self.assertFalse(body["task_waiting"])
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_request_task_ok(self):
        self._stop_all_runs()
        run_ids = [self._create_run() for _ in range(3)]

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("error", body)

        run_id = str(body["run"]["_id"])
        self.assertIn(run_id, run_ids)

        run = self.rundb.get_run(run_id)
        self.assertEqual(len(run["tasks"]), 1)
        self.assertEqual(run["workers"], 1)
        self.assertEqual(run["cores"], self.worker_info["concurrency"])
        self.assertTrue(run["tasks"][body["task_id"]]["active"])

    def test_request_task_blocked_worker_is_application_error(self):
        if worker_name is None:  # pragma: no cover
            raise unittest.SkipTest("worker_name import missing")

        worker_short = worker_name(self.worker_info, short=True)
        self.rundb.workerdb.update_worker(
            worker_short,
            blocked=True,
            message="blocked for test",
        )
        try:
            response = self.client.post(
                "/api/request_task",
                json=self._payload(password=self.password),
            )
        finally:
            self.rundb.workerdb.update_worker(
                worker_short,
                blocked=False,
                message="",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("Request_task:", body["error"])
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_task_endpoints_missing_run_id_is_validation_error(self):
        endpoints = [
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
        ]
        pgn_payload = self._build_pgn_payload("missing-run", 0)
        for path in endpoints:
            payload = {
                **self._payload(password=self.password),
                "task_id": 0,
            }
            if path == "/api/upload_pgn":
                payload["pgn"] = pgn_payload
            response = self.client.post(path, json=payload)
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
                contains="run_id",
            )

    def test_task_endpoints_missing_task_id_is_validation_error(self):
        run_id, task_id = self._create_run_with_task()
        endpoints = [
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
        ]
        pgn_payload = self._build_pgn_payload(run_id, task_id)
        for path in endpoints:
            payload = {
                **self._payload(password=self.password),
                "run_id": run_id,
            }
            if path == "/api/upload_pgn":
                payload["pgn"] = pgn_payload
            response = self.client.post(path, json=payload)
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
                contains="task_id",
            )

    def test_task_endpoints_invalid_run_id_is_error(self):
        endpoints = [
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
        ]
        pgn_payload = self._build_pgn_payload("0123456789abcdef01234567", 0)
        for path in endpoints:
            payload = {
                **self._payload(password=self.password),
                "run_id": "0123456789abcdef01234567",
                "task_id": 0,
            }
            if path == "/api/upload_pgn":
                payload["pgn"] = pgn_payload
            response = self.client.post(path, json=payload)
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
                contains="Invalid run_id",
            )

    def test_task_endpoints_invalid_task_id_is_error(self):
        run_id, _task_id = self._create_run_with_task()
        endpoints = [
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
        ]
        pgn_payload = self._build_pgn_payload(run_id, 0)
        for path in endpoints:
            payload = {
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": 99,
            }
            if path == "/api/upload_pgn":
                payload["pgn"] = pgn_payload
            response = self.client.post(path, json=payload)
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
                contains="Invalid task_id",
            )

    def test_task_endpoints_mismatched_worker_info_is_error(self):
        run_id, task_id = self._create_run_with_task()
        endpoints = [
            "/api/update_task",
            "/api/beat",
            "/api/request_spsa",
            "/api/failed_task",
            "/api/stop_run",
            "/api/upload_pgn",
        ]
        pgn_payload = self._build_pgn_payload(run_id, task_id)
        worker_info = copy.deepcopy(self.worker_info)
        worker_info["unique_key"] = "f4f1a1b6-2dd0-4f2b-ae6e-3f6f3b3b4c7b"
        for path in endpoints:
            payload = {
                **self._payload(password=self.password, worker_info=worker_info),
                "run_id": run_id,
                "task_id": task_id,
            }
            if path == "/api/upload_pgn":
                payload["pgn"] = pgn_payload
            response = self.client.post(path, json=payload)
            self._assert_worker_error_response(
                response,
                status_code=400,
                path=path,
                contains="Invalid unique_key",
            )

    def test_worker_log_ok(self):
        response = self.client.post(
            "/api/worker_log",
            json={
                **self._payload(password=self.password),
                "message": "hello",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_update_task_ok(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/update_task",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "stats": {
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [0, 0, 0, 0, 0],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("task_alive", body)
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_beat_ok(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/beat",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("task_alive"))
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_request_spsa_ok(self):
        run_id, task_id = self._create_run_with_task(spsa=True)
        response = self.client.post(
            "/api/request_spsa",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("task_alive"))
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_failed_task_ok(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/failed_task",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "message": "failed for test",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_stop_run_ok(self):
        run_id, task_id = self._create_run_with_task()
        self.rundb.userdb.user_cache.update_one(
            {"username": self.username},
            {"$set": {"cpu_hours": 1000}},
        )
        try:
            response = self.client.post(
                "/api/stop_run",
                json={
                    **self._payload(password=self.password),
                    "run_id": run_id,
                    "task_id": task_id,
                    "message": "stop run for test",
                },
            )
        finally:
            self.rundb.userdb.user_cache.update_one(
                {"username": self.username},
                {"$set": {"cpu_hours": 0}},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_stop_run_insufficient_cpu_hours_is_error(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/stop_run",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "message": "stop run for test",
            },
        )
        self._assert_worker_error_response(
            response,
            status_code=401,
            path="/api/stop_run",
            contains="too few games",
        )

    def test_stop_run_finished_run_is_error(self):
        run_id, task_id = self._create_run_with_task()
        run = self.rundb.get_run(run_id)
        run["finished"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        self.rundb.userdb.user_cache.update_one(
            {"username": self.username},
            {"$set": {"cpu_hours": 1000}},
        )
        try:
            response = self.client.post(
                "/api/stop_run",
                json={
                    **self._payload(password=self.password),
                    "run_id": run_id,
                    "task_id": task_id,
                    "message": "stop run for test",
                },
            )
        finally:
            self.rundb.userdb.user_cache.update_one(
                {"username": self.username},
                {"$set": {"cpu_hours": 0}},
            )

        self._assert_worker_error_response(
            response,
            status_code=401,
            path="/api/stop_run",
            contains="already finished",
        )

    def test_upload_pgn_ok(self):
        run_id, task_id = self._create_run_with_task()
        pgn_payload = self._build_pgn_payload(run_id, task_id)

        response = self.client.post(
            "/api/upload_pgn",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "pgn": pgn_payload,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(isinstance(body.get("duration"), (int, float)))

    def test_upload_pgn_missing_payload_is_error(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/upload_pgn",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
            },
        )
        self._assert_worker_error_response(
            response,
            status_code=400,
            path="/api/upload_pgn",
            contains="Missing pgn",
        )

    def test_upload_pgn_invalid_base64_is_error(self):
        run_id, task_id = self._create_run_with_task()
        response = self.client.post(
            "/api/upload_pgn",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "pgn": "not-base64",
            },
        )
        self._assert_worker_error_response(
            response,
            status_code=400,
            path="/api/upload_pgn",
        )

    def test_upload_pgn_invalid_gzip_is_error(self):
        run_id, task_id = self._create_run_with_task()
        invalid_payload = base64.b64encode(b"not-gzip").decode()
        response = self.client.post(
            "/api/upload_pgn",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": task_id,
                "pgn": invalid_payload,
            },
        )
        self._assert_worker_error_response(
            response,
            status_code=400,
            path="/api/upload_pgn",
        )

    def test_get_active_runs(self):
        run_id = self._create_run()
        response = self.client.get("/api/active_runs")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(run_id, body)

    def test_get_run(self):
        run_id = self._create_run()
        response = self.client.get(f"/api/get_run/{run_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("_id"), run_id)

    def test_get_elo(self):
        run_id = self._create_run()
        response = self.client.get(f"/api/get_elo/{run_id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json())

    def test_duplicate_workers(self):
        self._stop_all_runs()
        self._create_run(num_games=400)

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", response.json())

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", response.json())

    def test_auto_purge_runs(self):
        self._stop_all_runs()
        run_id = self._create_run(num_games=1200)

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        body = response.json()
        self.assertEqual(body["run"]["_id"], run_id)
        self.assertEqual(body["task_id"], 0)

        task1 = self.rundb.get_run(run_id)["tasks"][0]
        task_size1 = task1["num_games"]

        n_wins = task_size1 // 5
        n_losses = task_size1 // 5
        n_draws = task_size1 - n_wins - n_losses

        response = self.client.post(
            "/api/update_task",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": 0,
                "stats": {
                    "wins": n_wins,
                    "draws": n_draws,
                    "losses": n_losses,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [n_losses // 2, 0, n_draws // 2, 0, n_wins // 2],
                },
            },
        )
        self.assertFalse(response.json()["task_alive"])
        run = self.rundb.get_run(run_id)
        self.assertFalse(run["finished"])

        response = self.client.post(
            "/api/request_task",
            json=self._payload(password=self.password),
        )
        body = response.json()
        self.assertEqual(body["run"]["_id"], run_id)
        self.assertEqual(body["task_id"], 1)

        task2 = self.rundb.get_run(run_id)["tasks"][1]
        task_size2 = task2["num_games"]
        task_start2 = task2["start"]

        self.assertEqual(task_start2, task_size1)

        n_wins = 2 * ((task_size2 // 5) // 2)
        n_losses = 2 * ((task_size2 // 5) // 2)
        n_draws = task_size2 - n_wins - n_losses

        response = self.client.post(
            "/api/update_task",
            json={
                **self._payload(password=self.password),
                "run_id": run_id,
                "task_id": 1,
                "stats": {
                    "wins": n_wins,
                    "draws": n_draws,
                    "losses": n_losses,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": [n_losses // 2, 0, n_draws // 2, 0, n_wins // 2],
                },
            },
        )
        self.assertFalse(response.json()["task_alive"])

        run = self.rundb.get_run(run_id)
        self.assertTrue(run["finished"])
        self.assertTrue(all([not t["active"] for t in run["tasks"]]))

    def test_download_run_pgns_streaming_response(self):
        run_id = "testrun123"
        pgn_a = b"pgn-a"
        pgn_b = b"pgn-bb"
        self.rundb.upload_pgn(f"{run_id}-0", pgn_a)
        self.rundb.upload_pgn(f"{run_id}-1", pgn_b)

        response = self.client.get(f"/api/run_pgns/{run_id}.pgn.gz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("content-length"),
            str(len(pgn_a) + len(pgn_b)),
        )
        self.assertEqual(response.headers.get("content-type"), "application/gzip")
        self.assertEqual(len(response.content), len(pgn_a) + len(pgn_b))

    def test_download_pgn_streaming_response(self):
        run_id = "0123456789abcdef01234567-0"
        raw_pgn = b"pgn-bytes"
        pgn_bytes = gzip.compress(raw_pgn)
        self.rundb.upload_pgn(run_id, pgn_bytes)

        response = self.client.get(f"/api/pgn/{run_id}.pgn")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-encoding"), "gzip")
        self.assertEqual(response.headers.get("content-length"), str(len(pgn_bytes)))
        self.assertEqual(response.headers.get("content-type"), "application/gzip")
        self.assertEqual(response.content, raw_pgn)


if __name__ == "__main__":
    unittest.main()
