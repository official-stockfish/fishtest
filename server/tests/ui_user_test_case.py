# ruff: noqa: ANN201, ANN206, D100, D101, D102, S105
"""Shared FastAPI UI test scaffolding for focused test modules."""

import unittest
from datetime import UTC, datetime

import test_support

from fishtest.run_cache import Prio


class UiUserTestCase(unittest.TestCase):
    username = "TestUiUser"
    password = "test-ui-password"
    signup_username = None
    signup_password = "CorrectHorseBatteryStaple123!"
    tests_repo = "https://github.com/official-stockfish/Stockfish"

    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        if cls.signup_username is None:
            cls.signup_username = f"{cls.username}Signup"

        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username, cls.signup_username],
            clear_runs=True,
            drop_runs=True,
            close_conn=False,
        )
        cls.rundb.userdb.create_user(
            cls.username,
            cls.password,
            f"{cls.username.lower()}@example.com",
            cls.tests_repo,
        )

    def setUp(self):
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )
        self._ensure_user_can_login()

    @classmethod
    def tearDownClass(cls):
        signup_username = cls.signup_username
        assert signup_username is not None

        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username, signup_username],
            clear_runs=True,
            drop_runs=True,
        )

    def _ensure_user_can_login(self):
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
        user["blocked"] = False
        self.rundb.userdb.save_user(user)

    def _login_user(self):
        self._ensure_user_can_login()

        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def _create_run(self, *, approved: bool = True) -> str:
        run_id = self.rundb.new_run(
            base_tag="master",
            new_tag="master",
            num_games=400,
            tc="10+0.01",
            new_tc="10+0.01",
            book="book.pgn",
            book_depth="10",
            threads=1,
            base_options="",
            new_options="",
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
            tests_repo=self.tests_repo,
            auto_purge=False,
            username=self.username,
            start_time=datetime.now(UTC),
            arch_filter="avx",
        )
        run = self.rundb.get_run(run_id)
        run["approved"] = approved
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return str(run_id)
