import unittest
from datetime import UTC, datetime

import util
from fishtest.api import WorkerApi
from fishtest.views import login, signup, user
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


class ApiKeyResetTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.username = "ApiKeyUser"
        self.password = "secret"
        self.rundb.userdb.create_user(
            self.username,
            self.password,
            "apikey@user.net",
            "https://github.com/official-stockfish/Stockfish",
        )
        user_data = self.rundb.userdb.get_user(self.username)
        user_data["pending"] = False
        self.rundb.userdb.save_user(user_data)
        self.config = testing.setUp()
        self.config.add_route("login", "/login")
        self.config.add_route("user", "/user")
        self.config.add_route("profile", "/user")
        self.config.testing_securitypolicy(userid=self.username)

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": self.username})
        self.rundb.userdb.user_cache.delete_many({"username": self.username})
        testing.tearDown()

    def test_api_key_reset_flow(self):
        old_api_key = self.rundb.userdb.get_user(self.username)["api_key"]
        session = testing.DummySession()
        params = {
            "user": self.username,
            "action": "api_key_reset",
            "old_password": self.password,
        }
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params=params,
            session=session,
            url="http://example.com/user",
            matchdict={},
        )
        response = user(request)
        self.assertEqual(response.code, 302)

        updated_user = self.rundb.userdb.get_user(self.username)
        new_api_key = updated_user["api_key"]
        self.assertNotEqual(old_api_key, new_api_key)
        self.assertTrue(new_api_key.startswith("ft_"))
        self.assertEqual(session.get("new_api_key"), new_api_key)

        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="GET",
            session=session,
            url="http://example.com/user",
            matchdict={},
        )
        response = user(request)
        self.assertEqual(response["new_api_key"], new_api_key)
        self.assertNotIn("new_api_key", session)

        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="GET",
            session=session,
            url="http://example.com/user",
            matchdict={},
        )
        response = user(request)
        self.assertIsNone(response["new_api_key"])

        api_request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            json_body={
                "api_key": new_api_key,
                "worker_info": {"username": self.username},
            },
        )
        api = WorkerApi(api_request)
        api.validate_auth()
        self.assertEqual(api._auth_method, "api_key")


if __name__ == "__main__":
    unittest.main()
