# ruff: noqa: ANN201, ANN206, B025, B904, D100, D101, D102, E501, EM102, INP001, PLC0415, PT009, S105, TRY003

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import test_support
from vtjson import ValidationError

from fishtest.run_cache import Prio
from fishtest.util import PASSWORD_MAX_LENGTH


class TestHttpUsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()

        cls.username = "JoeUser"
        cls.password = "secret"
        cls.signup_username = "JoeUserSignup"
        cls.signup_password = "CorrectHorseBatteryStaple123!"

        # Create a user used by login tests.
        cls.rundb.userdb.create_user(
            cls.username,
            cls.password,
            "email@email.email",
            "https://github.com/official-stockfish/Stockfish",
        )

    def setUp(self):
        # New client per test to avoid cookie/session leakage between tests.
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

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username, cls.signup_username],
            clear_runs=True,
            drop_runs=True,
        )

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/login",
            data={"username": self.username, "password": "badsecret"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        # UI 403s are rendered as HTML (login page) by glue error handlers.
        self.assertIn("Please login", response.text)

    def test_login_invalid_password_renders_flash(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": "badsecret",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid username or password.", response.text)

    def test_login_pending_then_success_redirects(self):
        # Pending is the default for new users; ensure it is set for this test.
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = True
        self.rundb.userdb.save_user(user)

        response = self.client.get("/login")
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
        self.assertEqual(response.status_code, 200)
        self.assertIn("pending approval", response.text)
        self.assertIn("manually approve your new account", response.text)

        # Unblock, then user can log in successfully.
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
        self.rundb.userdb.save_user(user)

        # GET again to ensure CSRF token is tied to the current cookie state.
        response = self.client.get("/login")
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
        self.assertIn("location", {k.lower() for k in response.headers})

    def test_signup_creates_user_and_redirects(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        with (
            patch.dict(
                "os.environ",
                {"FISHTEST_CAPTCHA_SECRET": "test-secret"},
                clear=False,
            ),
            patch(
                "fishtest.views.requests.post",
                return_value=type(
                    "_CaptchaResponse",
                    (),
                    {"json": staticmethod(lambda: {"success": True})},
                )(),
            ),
        ):
            response = self.client.post(
                "/signup",
                data={
                    "username": self.signup_username,
                    "password": self.signup_password,
                    "password2": self.signup_password,
                    "email": "joe@user.net",
                    "tests_repo": "https://github.com/official-stockfish/Stockfish",
                    "g-recaptcha-response": "captcha-ok",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/login"))

    def test_signup_rejects_too_long_password(self):
        long_password = "A1!a" * 20
        self.assertGreater(len(long_password), PASSWORD_MAX_LENGTH)
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        response = self.client.post(
            "/signup",
            data={
                "username": "LongPasswordUser",
                "password": long_password,
                "password2": long_password,
                "email": "joe@user.net",
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"Error! Password too long (max {PASSWORD_MAX_LENGTH} characters)",
            response.text,
        )

    def test_login_page_has_csrf_meta(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_signup_page_has_csrf_meta(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_signup_requires_csrf(self):
        response = self.client.post(
            "/signup",
            data={
                "username": "nouser",
                "password": "badpass",
                "password2": "badpass",
                "email": "nouser@example.com",
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Register", response.text)

    def test_logout_redirects_and_clears_cookie(self):
        response = self.client.get("/login")
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

        response = self.client.post(
            "/logout",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("location", {k.lower() for k in response.headers})
        self.assertIn("set-cookie", {k.lower() for k in response.headers})

    def test_notfound_returns_html(self):
        response = self.client.get("/no-such-route")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Oops! Page not found.", response.text)

    def test_list_and_detail_pages_render(self):
        response = self.client.get("/contributors")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Contributors", response.text)

        run_id = self._create_run()
        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(run_id), response.text)

    def test_contributors_server_side_search_hx_fragment(self):
        hit_name = "HxSearchMatchUser"
        miss_name = "HxSearchMissUser"
        docs = [
            {
                "username": hit_name,
                "cpu_hours": 10,
                "games": 50,
                "tests": 2,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
            {
                "username": miss_name,
                "cpu_hours": 5,
                "games": 20,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get(
                "/contributors?search=matchuser",
                headers={"HX-Request": "true"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(hit_name, response.text)
            self.assertNotIn(miss_name, response.text)
            self.assertNotIn("<table", response.text)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$in": [hit_name, miss_name]}}
            )

    def test_workers_server_side_filter_hx_fragment(self):
        recent_worker = "hxrecent-1cores-abcd"
        old_worker = "hxold-1cores-abcd"

        self.rundb.workerdb.update_worker(recent_worker, blocked=True, message="recent")
        self.rundb.workerdb.update_worker(old_worker, blocked=True, message="old")
        self.rundb.workerdb.workers.update_one(
            {"worker_name": old_worker},
            {"$set": {"last_updated": datetime.now(UTC) - timedelta(days=10)}},
        )
        self.rundb.workerdb.workers.update_one(
            {"worker_name": recent_worker},
            {"$set": {"last_updated": datetime.now(UTC) - timedelta(days=1)}},
        )

        try:
            response = self.client.get(
                "/workers/show?filter=gt-5days",
                headers={"HX-Request": "true"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(old_worker, response.text)
            self.assertNotIn(recent_worker, response.text)
            self.assertNotIn("<table", response.text)
        finally:
            self.rundb.workerdb.workers.delete_many(
                {"worker_name": {"$in": [recent_worker, old_worker]}}
            )

    def test_user_management_lazy_group_hx_fragment(self):
        pending_user = "HxPendingGroupUser"
        blocked_user = "HxBlockedGroupUser"

        self.rundb.userdb.create_user(
            pending_user,
            "secret",
            "pending-group@example.com",
            "https://github.com/official-stockfish/Stockfish",
        )
        self.rundb.userdb.create_user(
            blocked_user,
            "secret",
            "blocked-group@example.com",
            "https://github.com/official-stockfish/Stockfish",
        )

        blocked_doc = self.rundb.userdb.get_user(blocked_user)
        blocked_doc["pending"] = False
        blocked_doc["blocked"] = True
        self.rundb.userdb.save_user(blocked_doc)

        approver = self.rundb.userdb.get_user(self.username)
        original_pending = approver.get("pending", False)
        original_groups = list(approver.get("groups", []))
        approver["pending"] = False
        if "group:approvers" not in approver["groups"]:
            approver["groups"].append("group:approvers")
        self.rundb.userdb.save_user(approver)

        try:
            response = self.client.get("/login")
            csrf = test_support.extract_csrf_token(response.text)
            login = self.client.post(
                "/login",
                data={
                    "username": self.username,
                    "password": self.password,
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
            self.assertEqual(login.status_code, 302)

            response = self.client.get(
                "/user_management?group=blocked",
                headers={"HX-Request": "true"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(blocked_user, response.text)
            self.assertNotIn(pending_user, response.text)
            self.assertNotIn("<table", response.text)
        finally:
            cleanup_approver = self.rundb.userdb.get_user(self.username)
            cleanup_approver["pending"] = original_pending
            cleanup_approver["groups"] = original_groups
            self.rundb.userdb.save_user(cleanup_approver)

            pending_doc = self.rundb.userdb.get_user(pending_user)
            if pending_doc is not None:
                self.rundb.userdb.remove_user(pending_doc, self.username)
            blocked_doc = self.rundb.userdb.get_user(blocked_user)
            if blocked_doc is not None:
                self.rundb.userdb.remove_user(blocked_doc, self.username)

    def test_add_user_group_raises_on_duplicate(self):
        """Ensure adding a duplicate group raises ValidationError from userdb."""
        username = "GroupTestUser"
        # create a fresh user for this test
        self.rundb.userdb.create_user(username, "pwd", "g@u.com", "")
        try:
            self.rundb.userdb.add_user_group(username, "approvers")
            self.rundb.userdb.add_user_group(username, "dummy")
            with self.assertRaises(ValidationError):
                self.rundb.userdb.add_user_group(username, "approvers")
        finally:
            # cleanup
            self.rundb.userdb.users.delete_one({"username": username})
            self.rundb.userdb.user_cache.delete_one({"username": username})
            self.rundb.userdb.clear_cache()

    def _check_auth_with_flag(self, field, expected_error, expected_code):
        """Set a user flag, verify authenticate() returns the expected error, restore."""
        user = self.rundb.userdb.get_user(self.username)
        original = user.get(field)
        user[field] = True
        self.rundb.userdb.save_user(user)
        try:
            token = self.rundb.userdb.authenticate(self.username, self.password)
            self.assertEqual(token["error"], expected_error)
            self.assertEqual(token["error_code"], expected_code)
        finally:
            user = self.rundb.userdb.get_user(self.username)
            user[field] = original
            self.rundb.userdb.save_user(user)

    def test_authenticate_unknown_user(self):
        token = self.rundb.userdb.authenticate("NoSuchUser", "x")
        self.assertEqual(token["error"], "Invalid username or password.")
        self.assertEqual(token["error_code"], "invalid_credentials")

    def test_authenticate_blocked_user(self):
        self._check_auth_with_flag("blocked", "Your account is blocked.", "blocked")

    def test_authenticate_pending_user(self):
        self._check_auth_with_flag(
            "pending", "Your account is pending approval.", "pending"
        )


if __name__ == "__main__":
    unittest.main()
