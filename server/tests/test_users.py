# ruff: noqa: ANN201, ANN206, B904, D100, D101, D102, E501, EM102, INP001, PLC0415, PT009, S105, TRY003
"""Test auth, session, and shared user-facing smoke routes."""

from unittest.mock import patch
from urllib.parse import urlencode

import test_support
from ui_user_test_case import UiUserTestCase
from vtjson import ValidationError

from fishtest.http.settings import SESSION_REMEMBER_ME_MAX_AGE_SECONDS
from fishtest.util import PASSWORD_MAX_LENGTH


class TestUsers(UiUserTestCase):
    username = "TestAuthUser"

    def _assert_no_store_headers(self, response):
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.headers.get("Expires"), "0")

    def _check_auth_with_flag(self, field, expected_error, expected_code):
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

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/login",
            data={"username": self.username, "password": "wrong-test-password"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Please login", response.text)

    def test_login_invalid_password_renders_flash(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": "wrong-test-password",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid username or password.", response.text)

    def test_login_pending_then_success_redirects(self):
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

        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
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
        self.assertEqual(response.status_code, 302)
        self.assertIn("location", {k.lower() for k in response.headers})

    def test_signup_creates_user_and_redirects(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        self._assert_no_store_headers(response)
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
                    "email": "signup-test@user.net",
                    "tests_repo": self.tests_repo,
                    "g-recaptcha-response": "captcha-ok",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/login"))
        self._assert_no_store_headers(response)

    def test_signup_canonicalizes_tests_repo(self):
        signup_username = "TestCanonicalSignupUser"
        self.rundb.userdb.users.delete_many({"username": signup_username})
        self.rundb.userdb.clear_cache()
        self.addCleanup(
            self.rundb.userdb.users.delete_many,
            {"username": signup_username},
        )
        self.addCleanup(self.rundb.userdb.clear_cache)

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
                    "username": signup_username,
                    "password": self.signup_password,
                    "password2": self.signup_password,
                    "email": "canonical-signup-test@user.net",
                    "tests_repo": self.tests_repo + "/",
                    "g-recaptcha-response": "captcha-ok",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        created_user = self.rundb.userdb.get_user(signup_username)
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user["tests_repo"], self.tests_repo)

    def test_signup_rejects_too_long_password(self):
        long_password = "A1!a" * 20
        self.assertGreater(len(long_password), PASSWORD_MAX_LENGTH)
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        response = self.client.post(
            "/signup",
            data={
                "username": "TestLongPasswordUser",
                "password": long_password,
                "password2": long_password,
                "email": "long-password-test@user.net",
                "tests_repo": self.tests_repo,
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
        self._assert_no_store_headers(response)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_login_page_defaults_remember_me_checked(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="stay_logged_in" value="0"', response.text)
        self.assertIn('name="stay_logged_in"', response.text)
        self.assertIn('id="staylogged"', response.text)
        self.assertIn("checked", response.text)

    def test_login_default_sets_persistent_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self._assert_no_store_headers(response)
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
        self._assert_no_store_headers(response)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertIn(f"Max-Age={SESSION_REMEMBER_ME_MAX_AGE_SECONDS}", cookie)

    def test_login_duplicate_remember_fields_keep_persistent_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            content=urlencode(
                [
                    ("username", self.username),
                    ("password", self.password),
                    ("stay_logged_in", "0"),
                    ("stay_logged_in", "1"),
                    ("csrf_token", csrf),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertIn(f"Max-Age={SESSION_REMEMBER_ME_MAX_AGE_SECONDS}", cookie)

    def test_login_explicit_non_remember_sets_session_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "stay_logged_in": "0",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertNotIn("Max-Age=", cookie)

    def test_signup_page_has_csrf_meta(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        self._assert_no_store_headers(response)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_signup_requires_csrf(self):
        response = self.client.post(
            "/signup",
            data={
                "username": "TestNoCsrfUser",
                "password": "invalid-test-password",
                "password2": "invalid-test-password",
                "email": "no-csrf-test@user.net",
                "tests_repo": self.tests_repo,
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

    def test_user_profile_post_requires_csrf(self):
        original_user = self.rundb.userdb.get_user(self.username)
        original_email = original_user["email"]
        original_tests_repo = original_user["tests_repo"]

        self._login_user()

        response = self.client.post(
            "/user",
            data={
                "user": self.username,
                "old_password": self.password,
                "email": "updated-auth-user@example.com",
                "tests_repo": original_tests_repo,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)

        updated_user = self.rundb.userdb.get_user(self.username)
        self.assertEqual(updated_user["email"], original_email)
        self.assertEqual(updated_user["tests_repo"], original_tests_repo)

    def test_user_profile_post_canonicalizes_tests_repo(self):
        self._login_user()
        user = self.rundb.userdb.get_user(self.username)

        response = self.client.get("/user")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/user",
            data={
                "user": self.username,
                "old_password": self.password,
                "email": user["email"],
                "tests_repo": self.tests_repo + "/",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        updated_user = self.rundb.userdb.get_user(self.username)
        self.assertEqual(updated_user["tests_repo"], self.tests_repo)

    def test_user_admin_post_requires_csrf(self):
        target_username = self.signup_username
        self.rundb.userdb.users.delete_many({"username": target_username})
        self.rundb.userdb.clear_cache()

        created = self.rundb.userdb.create_user(
            target_username,
            "target-user-password",
            "target-user@example.com",
            self.tests_repo,
        )
        self.assertTrue(created)

        target_user = self.rundb.userdb.get_user(target_username)
        target_user["pending"] = False
        self.rundb.userdb.save_user(target_user)

        original_pending, original_groups = self._set_approver_state()
        try:
            self._login_user()

            response = self.client.post(
                f"/user/{target_username}",
                data={"user": target_username, "blocked": "1"},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 403)

            updated_target_user = self.rundb.userdb.get_user(target_username)
            self.assertFalse(updated_target_user["blocked"])
        finally:
            self._restore_approver_state(original_pending, original_groups)
            self.rundb.userdb.users.delete_many({"username": target_username})
            self.rundb.userdb.clear_cache()

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
        username = "TestGroupUser"
        self.rundb.userdb.create_user(
            username,
            "test-group-password",
            "test-group@example.com",
            "",
        )
        try:
            self.rundb.userdb.add_user_group(username, "approvers")
            self.rundb.userdb.add_user_group(username, "dummy")
            with self.assertRaises(ValidationError):
                self.rundb.userdb.add_user_group(username, "approvers")
        finally:
            self.rundb.userdb.users.delete_one({"username": username})
            self.rundb.userdb.user_cache.delete_one({"username": username})
            self.rundb.userdb.clear_cache()

    def test_authenticate_unknown_user(self):
        token = self.rundb.userdb.authenticate("MissingTestUser", "x")
        self.assertEqual(token["error"], "Invalid username or password.")
        self.assertEqual(token["error_code"], "invalid_credentials")

    def test_authenticate_blocked_user(self):
        self._check_auth_with_flag("blocked", "Your account is blocked.", "blocked")

    def test_authenticate_pending_user(self):
        self._check_auth_with_flag(
            "pending", "Your account is pending approval.", "pending"
        )
