# ruff: noqa: ANN201, ANN206, B025, B904, D100, D101, D102, E501, EM102, INP001, PLC0415, PT009, S105, TRY003

import unittest
from datetime import UTC, datetime
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


class ApiKeyResetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        cls.username = "ApiKeyUser"
        cls.password = "secret"
        cls.rundb.userdb.create_user(
            cls.username,
            cls.password,
            "apikey@user.net",
            "https://github.com/official-stockfish/Stockfish",
        )
        user_data = cls.rundb.userdb.get_user(cls.username)
        user_data["pending"] = False
        cls.rundb.userdb.save_user(user_data)

    def setUp(self):
        # New client per test to avoid cookie/session leakage between tests.
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=True,
            include_views=True,
        )

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username],
            clear_runs=False,
            drop_runs=False,
        )

    def _login(self):
        """Helper to log in the test user and return CSRF token."""
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
        return csrf

    def test_api_key_reset_flow(self):
        # Get old API key
        old_api_key = self.rundb.userdb.get_user(self.username)["api_key"]

        # Log in first
        csrf = self._login()

        # Reset API key via profile page
        response = self.client.post(
            "/user",
            data={
                "user": self.username,
                "action": "api_key_reset",
                "old_password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/user"))

        # Verify API key was changed in database
        updated_user = self.rundb.userdb.get_user(self.username)
        new_api_key = updated_user["api_key"]
        self.assertNotEqual(old_api_key, new_api_key)
        self.assertTrue(new_api_key.startswith("ft_"))

        # Get the profile page to see the new API key displayed
        response = self.client.get("/user")
        self.assertEqual(response.status_code, 200)
        self.assertIn(new_api_key, response.text)
        self.assertIn("Success! API key reset", response.text)

        # Verify the new API key works for API authentication
        api_response = self.client.post(
            "/api/request_version",
            json={
                "api_key": new_api_key,
                "worker_info": {"username": self.username},
            },
        )
        self.assertEqual(api_response.status_code, 200)

        # Verify old API key no longer works
        api_response = self.client.post(
            "/api/request_version",
            json={
                "api_key": old_api_key,
                "worker_info": {"username": self.username},
            },
        )
        self.assertEqual(api_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
