import unittest
from datetime import datetime, timezone

import util
from fishtest.views import login, signup
from pyramid import testing


class Create10UsersTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.config = testing.setUp()
        self.config.add_route("login", "/login")
        self.config.add_route("signup", "/signup")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.users.delete_many({"username": "JoeUser2"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser2"})
        self.rundb.stop()
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

        request2 = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            remote_addr="127.0.0.1",
            params={
                "username": "JoeUser2",
                "password": "secret2",
                "password2": "secret2",
                "email": "joe2@user.net",
                "tests_repo": "https://github.com/official-stockfish/Stockfish2",
            },
        )
        response2 = signup(request2)
        self.assertTrue("The resource was found at", response2)


class Create50LoginTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.rundb.userdb.create_user(
            "JoeUser",
            "secret",
            "email@email.email",
            "https://github.com/official-stockfish/Stockfish",
        )
        self.rundb.userdb.create_user(
            "JoeUser2",
            "$argon2id$v=19$m=12288,t=3,p=1$9tW9uRY6ijZ0PEiOcldWoQ$f5YCuVMP77x8Wlrcue0Jn7JGjCmgKy76WQynuIfitdA",
            "email2@email.email",
            "https://github.com/official-stockfish/Stockfish2",
        )
        self.config = testing.setUp()
        self.config.add_route("login", "/login")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.users.delete_many({"username": "JoeUser2"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser2"})
        self.rundb.stop()
        testing.tearDown()

    def test_login(self):
        # Pending user, wrong password
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params={"username": "JoeUser", "password": "badsecret"},
        )
        response = login(request)
        self.assertTrue(
            "Invalid password for user: JoeUser" in request.session.pop_flash("error")
        )

        # Pending user, correct password
        request.params["password"] = "secret"
        login(request)
        self.assertTrue(
            "Account pending for user: JoeUser" in request.session.pop_flash("error")[0]
        )

        # Approved user, wrong password
        user = self.rundb.userdb.get_user("JoeUser")
        user["pending"] = False
        self.rundb.userdb.save_user(user)
        request.params["password"] = "badsecret"
        response = login(request)
        self.assertTrue(
            "Invalid password for user: JoeUser" in request.session.pop_flash("error")
        )

        # Approved user, correct password
        request.params["password"] = "secret"
        response = login(request)
        self.assertEqual(response.code, 302)
        self.assertTrue("The resource was found at" in str(response))

        # User is blocked, correct password
        user["blocked"] = True
        self.rundb.userdb.save_user(user)
        response = login(request)
        self.assertTrue(
            "Account blocked for user: JoeUser" in request.session.pop_flash("error")[0]
        )

        # User is unblocked, correct password
        user["blocked"] = False
        self.rundb.userdb.save_user(user)
        response = login(request)
        self.assertEqual(response.code, 302)
        self.assertTrue("The resource was found at" in str(response))

        # Invalid username, correct password
        request.params["username"] = "UserJoe"
        response = login(request)
        self.assertTrue(
            "Invalid username: UserJoe" in request.session.pop_flash("error")[0]
        )

        # Pending user2, wrong password
        request2 = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params={"username": "JoeUser2", "password": "badsecret2"},
        )
        response2 = login(request2)
        self.assertTrue(
            "Invalid password for user: JoeUser2" in request2.session.pop_flash("error")
        )

        # Pending user2, correct password
        request2.params["password"] = "secret2"
        login(request2)
        self.assertTrue(
            "Account pending for user: JoeUser2"
            in request2.session.pop_flash("error")[0]
        )

        # Approved user2, wrong password
        user2 = self.rundb.userdb.get_user("JoeUser2")
        user2["pending"] = False
        self.rundb.userdb.save_user(user2)
        request2.params["password"] = "badsecret2"
        response2 = login(request2)
        self.assertTrue(
            "Invalid password for user: JoeUser2" in request2.session.pop_flash("error")
        )

        # Approved user2, correct password
        request2.params["password"] = "secret2"
        response2 = login(request2)
        self.assertEqual(response2.code, 302)
        self.assertTrue("The resource was found at" in str(response2))

        # User2 is blocked, correct password
        user2["blocked"] = True
        self.rundb.userdb.save_user(user2)
        response2 = login(request2)
        self.assertTrue(
            "Account blocked for user: JoeUser2"
            in request2.session.pop_flash("error")[0]
        )

        # User2 is unblocked, correct password
        user2["blocked"] = False
        self.rundb.userdb.save_user(user2)
        response2 = login(request2)
        self.assertEqual(response2.code, 302)
        self.assertTrue("The resource was found at" in str(response2))

        # Invalid username, correct password
        request2.params["username"] = "UserJoe2"
        response2 = login(request2)
        self.assertTrue(
            "Invalid username: UserJoe2" in request2.session.pop_flash("error")[0]
        )


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
            start_time=datetime.now(timezone.utc),
        )
        self.rundb.userdb.user_cache.insert_one(
            {"username": "JoeUser", "cpu_hours": 12345}
        )
        self.config = testing.setUp()
        self.config.add_route("api_stop_run", "/api/stop_run")

    def tearDown(self):
        self.rundb.userdb.users.delete_many({"username": "JoeUser"})
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
        self.rundb.stop()
        testing.tearDown()


if __name__ == "__main__":
    unittest.main()
