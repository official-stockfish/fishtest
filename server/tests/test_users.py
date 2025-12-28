import secrets
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import util
from fishtest.views import forgot_password, login, reset_password, signup
from pyramid import testing


class Create10UsersTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.config = testing.setUp()
        self.config.add_route("login", "/login")
        self.config.add_route("signup", "/signup")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        testing.tearDown()

    def test_create_user(self):
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            remote_addr="127.0.0.1",
            params={
                "username": "JoeUser",
                "password": "secret",
                "password2": "secret",
                "email": "joe@user.net",
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
        )
        response = signup(request)
        self.assertTrue("The resource was found at", response)


class Create50LoginTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.rundb.userdb.create_user(
            "JoeUser",
            "secret",
            "email@email.email",
            "https://github.com/official-stockfish/Stockfish",
        )
        self.config = testing.setUp()
        self.config.add_route("login", "/login")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        testing.tearDown()

    def test_login(self):
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params={"username": "JoeUser", "password": "badsecret"},
        )
        response = login(request)
        self.assertTrue(
            "Invalid password for user: JoeUser" in request.session.pop_flash("error")
        )

        # Correct password, but still pending from logging in
        request.params["password"] = "secret"
        login(request)
        self.assertTrue(
            "Account pending for user: JoeUser" in request.session.pop_flash("error")[0]
        )

        # Unblock, then user can log in successfully
        user = self.rundb.userdb.get_user("JoeUser")
        user["pending"] = False
        self.rundb.userdb.save_user(user)
        response = login(request)
        self.assertEqual(response.code, 302)
        self.assertTrue("The resource was found at" in str(response))


class Create90APITest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.run_id = self.rundb.new_run(
            "master",
            "master",
            100000,
            "100+0.01",
            "100+0.01",
            "book",
            10,
            1,
            "",
            "",
            username="travis",
            tests_repo="travis",
            start_time=datetime.now(UTC),
        )
        self.rundb.userdb.user_cache.insert_one(
            {"username": "JoeUser", "cpu_hours": 12345}
        )
        self.config = testing.setUp()
        self.config.add_route("api_stop_run", "/api/stop_run")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        testing.tearDown()


class _DummyEmailSender:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent = []

    def send(self, to_email, subject, text, html=None, reply_to=None):
        if self.should_fail:
            raise Exception("boom")
        self.sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "text": text,
                "html": html,
                "reply_to": reply_to,
            }
        )
        return {"ok": True}


class ForgotResetPasswordTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.config = testing.setUp()
        self.config.add_route("forgot_password", "/forgot_password")
        self.config.add_route("reset_password", "/reset_password/{token}")
        self.config.add_route("login", "/login")
        self.test_user = {
            "username": "ResetUser",
            "password": "secret",
            "email": "reset@user.net",
            "tests_repo": "https://github.com/official-stockfish/Stockfish",
        }
        self.rundb.userdb.create_user(**self.test_user)

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": self.test_user["username"]})
        self.rundb.userdb.user_cache.delete_many(
            {"username": self.test_user["username"]}
        )
        testing.tearDown()

    def test_forgot_password_valid_email(self):
        email_sender = _DummyEmailSender()
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            email_sender=email_sender,
            method="POST",
            params={"email": self.test_user["email"]},
            remote_addr="127.0.0.1",
        )
        forgot_password(request)
        self.assertEqual(len(email_sender.sent), 1)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertIn("password_reset", user)
        self.assertIn("token", user["password_reset"])
        self.assertIn("expires_at", user["password_reset"])
        self.assertGreater(user["password_reset"]["expires_at"], datetime.now(UTC))
        self.assertIn(
            "If that email exists, a reset link has been sent.",
            request.session.pop_flash("info")[0],
        )

    def test_forgot_password_invalid_email(self):
        email_sender = _DummyEmailSender()
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            email_sender=email_sender,
            method="POST",
            params={"email": "not-an-email"},
            remote_addr="127.0.0.1",
        )
        forgot_password(request)
        self.assertEqual(len(email_sender.sent), 0)
        self.assertIn("Error! Invalid email:", request.session.pop_flash("error")[0])

    def test_forgot_password_nonexistent_email(self):
        email_sender = _DummyEmailSender()
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            email_sender=email_sender,
            method="POST",
            params={"email": "missing-user@example.net"},
            remote_addr="127.0.0.1",
        )
        with patch(
            "fishtest.views.email_valid",
            return_value=(True, "missing-user@example.net"),
        ):
            forgot_password(request)
        self.assertEqual(len(email_sender.sent), 0)
        self.assertIn(
            "If that email exists, a reset link has been sent.",
            request.session.pop_flash("info")[0],
        )

    def test_forgot_password_email_send_error(self):
        email_sender = _DummyEmailSender(should_fail=True)
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            email_sender=email_sender,
            method="POST",
            params={"email": self.test_user["email"]},
            remote_addr="127.0.0.1",
        )
        forgot_password(request)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertIn("password_reset", user)
        self.assertIn(
            "If that email exists, a reset link has been sent.",
            request.session.pop_flash("info")[0],
        )

    def test_reset_password_expired_token(self):
        token = secrets.token_urlsafe(32)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        expires_at = datetime.now(UTC) - timedelta(minutes=1)
        self.rundb.userdb.set_password_reset(user, token, expires_at)
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="GET",
            matchdict={"token": token},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response.location, request.route_url("forgot_password"))
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertNotIn("password_reset", user)
        self.assertIn(
            "Reset link has expired.",
            request.session.pop_flash("error")[0],
        )

    def test_reset_password_invalid_token(self):
        token = secrets.token_urlsafe(32)
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="GET",
            matchdict={"token": token},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response.location, request.route_url("login"))
        self.assertIn(
            "Invalid reset link. It may have been replaced by a newer reset request.",
            request.session.pop_flash("error")[0],
        )

    def test_reset_password_token_invalid_after_use(self):
        token = secrets.token_urlsafe(32)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        self.rundb.userdb.set_password_reset(user, token, expires_at)
        new_password = "CorrectHorseBatteryStaple123!@#"
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            matchdict={"token": token},
            params={"password": new_password, "password2": new_password},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response.location, request.route_url("login"))
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertNotIn("password_reset", user)
        self.assertEqual(user["password"], new_password)

        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="GET",
            matchdict={"token": token},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response.location, request.route_url("login"))
        self.assertIn(
            "Invalid reset link. It may have been replaced by a newer reset request.",
            request.session.pop_flash("error")[0],
        )

    def test_reset_password_weak_password(self):
        token = secrets.token_urlsafe(32)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        self.rundb.userdb.set_password_reset(user, token, expires_at)
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            matchdict={"token": token},
            params={"password": "short", "password2": "short"},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response, {"token": token})
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertIn("password_reset", user)
        self.assertIn("Error! Weak password:", request.session.pop_flash("error")[0])

    def test_reset_password_mismatch(self):
        token = secrets.token_urlsafe(32)
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        self.rundb.userdb.set_password_reset(user, token, expires_at)
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            matchdict={"token": token},
            params={"password": "MismatchPassword123!", "password2": "Different123!"},
            remote_addr="127.0.0.1",
        )
        response = reset_password(request)
        self.assertEqual(response, {"token": token})
        user = self.rundb.userdb.find_by_email(self.test_user["email"])
        self.assertNotEqual(user["password"], "MismatchPassword123!")
        self.assertIn(
            "Error! Matching verify password required",
            request.session.pop_flash("error")[0],
        )


if __name__ == "__main__":
    unittest.main()
