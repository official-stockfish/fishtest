# ruff: noqa: ANN201, ANN206, D100, D101, D102, INP001, PLC0415, PT009

import os
import unittest
from typing import Any

import test_support


class _UserDbStub:
    def __init__(self, *, blocked_username: str | None = None):
        self._blocked_username = blocked_username

    def get_blocked(self):
        if self._blocked_username:
            return [{"username": self._blocked_username, "blocked": True}]
        return []


class _RunDbStub:
    def __init__(
        self,
        *,
        userdb: Any | None = None,
        shutdown: bool = False,
        is_primary: bool = True,
    ) -> None:
        self.userdb = userdb
        self.actiondb = None
        self.workerdb = None
        self._shutdown = shutdown
        self._base_url_set = True
        self.base_url = None
        self._is_primary = is_primary

    def is_primary_instance(self) -> bool:
        return self._is_primary


class TestHttpMiddleware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.FastAPI, cls.TestClient = test_support.require_fastapi()

    def test_shutdown_guard_returns_503(self):
        rundb = _RunDbStub(shutdown=True)
        app = test_support.build_test_app(
            rundb=rundb,
            include_api=False,
            include_views=False,
        )

        @app.get("/ping")
        async def _ping():
            return {"ok": True}

        client = self.TestClient(app)
        response = client.get("/ping")
        self.assertEqual(response.status_code, 503)

    def test_attach_request_state_sets_base_url(self):
        from fastapi import Request

        rundb = _RunDbStub()
        rundb._base_url_set = False
        app = test_support.build_test_app(
            rundb=rundb,
            include_api=False,
            include_views=False,
        )

        @app.get("/state")
        async def _state(request: Request):
            return {
                "has_rundb": request.state.rundb is rundb,
                "has_started_at": hasattr(request.state, "request_started_at"),
                "base_url": rundb.base_url,
            }

        client = self.TestClient(app)
        response = client.get("/state", headers={"host": "example.com"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_rundb"])
        self.assertTrue(payload["has_started_at"])
        self.assertEqual(payload["base_url"], "http://example.com")

    def test_reject_non_primary_worker_api(self):
        from fishtest.http.middleware import RejectNonPrimaryWorkerApiMiddleware

        app = self.FastAPI()
        app.add_middleware(RejectNonPrimaryWorkerApiMiddleware)
        app.state.rundb = _RunDbStub(is_primary=False)

        @app.post("/api/request_task")
        async def _request_task():
            return {"ok": True}

        client = self.TestClient(app)
        response = client.post("/api/request_task", json={})
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIn("error", body)
        self.assertIn("/api/request_task", body["error"])

    def test_redirect_blocked_ui_users(self):
        import json
        from base64 import b64encode

        from itsdangerous import TimestampSigner

        from fishtest.http.cookie_session import SESSION_COOKIE_NAME, session_secret_key

        os.environ.setdefault("FISHTEST_AUTHENTICATION_SECRET", "test-secret")

        userdb = _UserDbStub(blocked_username="blocked_user")
        rundb = _RunDbStub(userdb=userdb)

        app = test_support.build_test_app(
            rundb=rundb,
            include_api=False,
            include_views=False,
        )

        @app.get("/tests")
        async def _tests():
            return {"ok": True}

        client = self.TestClient(app)
        signer = TimestampSigner(session_secret_key())
        data = b64encode(json.dumps({"user": "blocked_user"}).encode("utf-8"))
        cookie_value = signer.sign(data).decode("utf-8")
        client.cookies.set(SESSION_COOKIE_NAME, cookie_value)
        response = client.get("/tests", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/tests", response.headers.get("location", ""))
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)

    def test_head_method_returns_200_with_empty_body(self):
        from fishtest.http.middleware import HeadMethodMiddleware

        app = self.FastAPI()
        app.add_middleware(HeadMethodMiddleware)

        @app.get("/ping")
        async def _ping():
            return {"ok": True}

        client = self.TestClient(app)
        response = client.head("/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_head_method_preserves_content_type(self):
        from fastapi.responses import HTMLResponse

        from fishtest.http.middleware import HeadMethodMiddleware

        app = self.FastAPI()
        app.add_middleware(HeadMethodMiddleware)

        @app.get("/page")
        async def _page():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = self.TestClient(app)
        response = client.head("/page")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertEqual(response.content, b"")

    def test_head_on_post_only_route_returns_405(self):
        from fishtest.http.middleware import HeadMethodMiddleware

        app = self.FastAPI()
        app.add_middleware(HeadMethodMiddleware)

        @app.post("/submit")
        async def _submit():
            return {"ok": True}

        client = self.TestClient(app)
        response = client.head("/submit")
        self.assertEqual(response.status_code, 405)


class TestHttpMiddlewareMongo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.FastAPI, cls.TestClient = test_support.require_fastapi()

        cls.rundb = test_support.get_rundb()

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_users_regex="^httpmw",
            close_conn=True,
        )

    def _session_cookie(self, username: str) -> str:
        import json
        from base64 import b64encode

        from itsdangerous import TimestampSigner

        from fishtest.http.cookie_session import session_secret_key

        signer = TimestampSigner(session_secret_key())
        data = b64encode(json.dumps({"user": username}).encode("utf-8"))
        return signer.sign(data).decode("utf-8")

    def test_redirect_blocked_ui_users_with_real_userdb(self):
        from fishtest.http.cookie_session import SESSION_COOKIE_NAME
        from fishtest.http.middleware import _blocked_cache

        username = "httpmwblocked"
        self.rundb.userdb.users.delete_many({"username": username})
        self.rundb.userdb.clear_cache()
        _blocked_cache.timestamp = None
        _blocked_cache.value = None

        self.rundb.userdb.create_user(username, "pwd", f"{username}@example.com", "")
        user = self.rundb.userdb.get_user(username)
        user["pending"] = False
        user["blocked"] = True
        self.rundb.userdb.save_user(user)

        app = test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=False,
        )

        @app.get("/tests")
        async def _tests():
            return {"ok": True}

        client = self.TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, self._session_cookie(username))
        response = client.get("/tests", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/tests"))
        set_cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn(f"{SESSION_COOKIE_NAME}=null", set_cookie)

    def test_allows_non_blocked_ui_user_with_real_userdb(self):
        from fishtest.http.cookie_session import SESSION_COOKIE_NAME
        from fishtest.http.middleware import _blocked_cache

        username = "httpmwallowed"
        self.rundb.userdb.users.delete_many({"username": username})
        self.rundb.userdb.clear_cache()
        _blocked_cache.timestamp = None
        _blocked_cache.value = None

        self.rundb.userdb.create_user(username, "pwd", f"{username}@example.com", "")
        user = self.rundb.userdb.get_user(username)
        user["pending"] = False
        user["blocked"] = False
        self.rundb.userdb.save_user(user)

        app = test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=False,
        )

        @app.get("/tests")
        async def _tests():
            return {"ok": True}

        client = self.TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, self._session_cookie(username))
        response = client.get("/tests")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
