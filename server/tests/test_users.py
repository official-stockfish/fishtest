import datetime
import unittest

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
        self.rundb.userdb.user_cache.delete_many({"username": "JoeUser"})
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
            },
        )
        response = signup(request)
        self.assertTrue("The resource was found at", response)


class Create50LoginTest(unittest.TestCase):
    def setUp(self):
        self.rundb = util.get_rundb()
        self.rundb.userdb.create_user("JoeUser", "secret", "email@email.email")
        self.rundb.userdb.create_user("JoeUser2", "$argon2id$v=19$m=65536,t=3,p=4$o0+5HBZzsgybGzJJllBGcQ$r0gw53V64bPEE4dLxKxrFHNqtQOTRy2nE1OHu1MBkBs", "email2@email.email")
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
        # blocked user, wrong password
        request = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params={"username": "JoeUser", "password": "badsecret"},
        )
        response = login(request)
        self.assertTrue(
            "Account blocked for user: JoeUser" in request.session.pop_flash("error")[0]
        )

        # blocked user, correct password
        request.params["password"] = "secret"
        response = login(request)
        self.assertTrue(
            "Account blocked for user: JoeUser" in request.session.pop_flash("error")[0]
        )

        # allowed user, wrong password
        user = self.rundb.userdb.get_user("JoeUser")
        user["blocked"] = False
        self.rundb.userdb.save_user(user)
        request.params["password"] = "badsecret"
        response = login(request)
        self.assertTrue(
            "Invalid password" in request.session.pop_flash("error")
        )

        # allowed user, correct password
        request.params["password"] = "secret"
        response = login(request)
        self.assertEqual(response.code, 302)
        self.assertTrue("The resource was found at" in str(response))

        # allowed user2, wrong hashed password
        user2 = self.rundb.userdb.get_user("JoeUser2")
        user2["blocked"] = False
        self.rundb.userdb.save_user(user2)

        request2 = testing.DummyRequest(
            userdb=self.rundb.userdb,
            method="POST",
            params={"username": "JoeUser2", "password": "badsecret"},
        )
        response2 = login(request2)
        self.assertTrue(
            "Invalid password" in request2.session.pop_flash("error")
        )

        # allowed user2, correct hashed password
        request2.params["password"] = "secret"
        response2 = login(request2)
        self.assertEqual(response2.code, 302)
        self.assertTrue("The resource was found at" in str(response2))


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
            start_time=datetime.datetime.utcnow(),
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
