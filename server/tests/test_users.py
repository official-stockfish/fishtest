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
        self.assertIn("Invalid password for user", response.text)

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
        self.assertIn("Account pending for user:", response.text)

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


if __name__ == "__main__":
    unittest.main()
