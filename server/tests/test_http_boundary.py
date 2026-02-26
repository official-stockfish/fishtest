# ruff: noqa: ANN201, ANN206, D100, D101, D102, E501, INP001, PLC0415, PT009

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, cast

import test_support
from fastapi import Depends, Request
from starlette.responses import Response


class TestHttpBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Skips cleanly if FastAPI/TestClient (and its deps like httpx) aren't available.
        _FastAPI, TestClient = test_support.require_fastapi()

        cls.rundb = test_support.get_rundb()
        cls.TestClient = TestClient

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
        )

    def _build_app(self, *, include_views: bool = False):
        return test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=include_views,
        )

    def test_request_shim_parity(self):
        from fishtest.http.boundary import ApiRequestShim
        from fishtest.http.cookie_session import CookieSession
        from fishtest.views import _RequestShim

        app = self._build_app()

        @app.get("/shim")
        async def _shim_probe(request: Request):
            session = CookieSession(data={})
            context = {
                "rundb": self.rundb,
                "userdb": self.rundb.userdb,
                "actiondb": self.rundb.actiondb,
                "workerdb": self.rundb.workerdb,
            }
            ui_shim = _RequestShim(request, session, None, {}, context=context)
            api_shim = ApiRequestShim(request)
            return {
                "api": {
                    "headers": dict(api_shim.headers),
                    "params": dict(api_shim.params),
                    "cookies": dict(api_shim.cookies),
                    "url": str(api_shim.url),
                    "host": api_shim.host,
                    "host_url": api_shim.host_url,
                    "remote_addr": api_shim.remote_addr,
                },
                "ui": {
                    "headers": dict(ui_shim.headers),
                    "params": dict(ui_shim.params),
                    "cookies": dict(ui_shim.cookies),
                    "url": str(ui_shim.url),
                    "host": ui_shim.host,
                    "host_url": ui_shim.host_url,
                    "remote_addr": ui_shim.remote_addr,
                },
            }

        client = self.TestClient(app)
        response = client.get(
            "/shim",
            params={"a": "1", "b": "2"},
            headers={"x-test-header": "hello"},
            cookies={"demo": "cookie"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["api"]["headers"].get("x-test-header"), "hello")
        self.assertEqual(data["ui"]["headers"].get("x-test-header"), "hello")
        self.assertEqual(data["api"]["params"], data["ui"]["params"])
        self.assertEqual(data["api"]["cookies"], data["ui"]["cookies"])
        self.assertEqual(data["api"]["url"], data["ui"]["url"])
        self.assertEqual(data["api"]["host"], data["ui"]["host"])
        self.assertEqual(data["api"]["host_url"], data["ui"]["host_url"])
        self.assertEqual(data["api"]["remote_addr"], data["ui"]["remote_addr"])
        self.assertTrue(data["api"]["remote_addr"])

    def test_json_parsing_errors(self):
        from fishtest.http.boundary import JsonBodyResult, get_json_body

        app = self._build_app()

        @app.post("/json")
        async def _json_probe(result: JsonBodyResult = Depends(get_json_body)):
            return {"error": result.error, "body": result.body}

        client = self.TestClient(app)
        response = client.post("/json", json={"ok": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error": False, "body": {"ok": True}})

        response = client.post(
            "/json",
            data=b"{",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["error"])
        self.assertIsNone(body["body"])

    def test_dispatch_view_204_has_no_body(self):
        from fishtest.views import _dispatch_view

        app = self._build_app()

        def _returns_204(shim):
            shim.response_status = 204
            return {"unused": True}

        @app.get("/dispatch-204")
        async def _dispatch_204_probe(request: Request):
            return await _dispatch_view(
                _returns_204,
                {"renderer": "login.html.j2"},
                request,
                {},
            )

        client = self.TestClient(app)
        response = client.get("/dispatch-204")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")

    def test_template_context_includes_helpers(self):
        from fishtest.http import jinja
        from fishtest.http.boundary import build_template_context
        from fishtest.http.cookie_session import CookieSession

        app = self._build_app()

        @app.get("/context")
        async def _context_probe(request: Request):
            session = CookieSession(data={"user": "TestUser"})
            session.flash("hello")
            context = build_template_context(request, session)
            self.assertTrue(hasattr(context["request"], "scope"))
            current_user = context.get("current_user")
            self.assertIsInstance(current_user, dict)
            typed_current_user = cast("dict[str, object]", current_user)
            username = typed_current_user.get("username")
            self.assertIsInstance(username, str)

            static_url = context.get("static_url")
            self.assertTrue(callable(static_url))
            typed_static_url = cast("Callable[[str], str]", static_url)

            flash = context.get("flash")
            self.assertIsInstance(flash, dict)
            typed_flash = cast("dict[str, object]", flash)
            return {
                "csrf": context["csrf_token"],
                "user": username,
                "flash": typed_flash,
                "static_url": typed_static_url("fishtest:static/css/site.css"),
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir) / "static"
            target = static_dir / "css" / "site.css"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("body{}", encoding="utf-8")

            original_dir = jinja._STATIC_DIR
            jinja._STATIC_DIR = static_dir
            jinja._static_file_token.cache_clear()
            try:
                client = self.TestClient(app)
                response = client.get("/context")
            finally:
                jinja._STATIC_DIR = original_dir
                jinja._static_file_token.cache_clear()

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["csrf"])
        self.assertEqual(data["user"], "TestUser")
        self.assertEqual(data["flash"]["info"], ["hello"])
        self.assertTrue(data["static_url"].startswith("/static/css/site.css"))
        self.assertIn("?x=", data["static_url"])

    def test_session_remember_commit_cookie(self):
        from fishtest.http.boundary import commit_session_response, remember
        from fishtest.http.cookie_session import load_session

        app = self._build_app()

        @app.get("/remember")
        async def _remember_probe(request: Request):
            session = load_session(request)
            shim = SimpleNamespace(session=session, _remember=False, _forget=False)
            remember(shim, "Tester", max_age=60)
            response = Response("ok")
            commit_session_response(request, session, shim, response)
            return response

        client = self.TestClient(app)
        response = client.get("/remember")
        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertIn("Max-Age=60", cookie)
        self.assertIn("Expires=", cookie)

    def test_session_forget_commit_cookie(self):
        from fishtest.http.boundary import commit_session_response, forget
        from fishtest.http.cookie_session import load_session

        app = self._build_app()

        @app.get("/forget")
        async def _forget_probe(request: Request):
            session = load_session(request)
            session.data["user"] = "Tester"
            shim = SimpleNamespace(session=session, _remember=False, _forget=False)
            forget(shim)
            response = Response("ok")
            commit_session_response(request, session, shim, response)
            return response

        client = self.TestClient(app)
        response = client.get("/forget")
        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        cookie_lower = cookie.lower()
        self.assertIn("max-age=0", cookie_lower)
        self.assertIn("expires=", cookie_lower)

    def test_session_forget_flags_force_cookie_clear(self):
        from fishtest.http.boundary import SessionCommitFlags, commit_session_flags
        from fishtest.http.cookie_session import load_session

        app = self._build_app()

        @app.get("/forget-flags")
        async def _forget_flags_probe(request: Request):
            session = load_session(request)
            session.data["user"] = "Tester"
            response = Response("ok")
            commit_session_flags(
                request,
                session,
                response,
                flags=SessionCommitFlags(remember=False, forget=True),
            )
            return response

        client = self.TestClient(app)
        response = client.get("/forget-flags")
        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("set-cookie", "").lower()
        self.assertIn("fishtest_session=null", cookie)

    def test_template_context_pending_users_count(self):
        from fishtest.http.boundary import build_template_context
        from fishtest.http.cookie_session import CookieSession

        username = "httpboundarypending"
        self.rundb.userdb.users.delete_many({"username": username})
        self.rundb.userdb.clear_cache()
        self.rundb.userdb.create_user(
            username,
            "pwd",
            f"{username}@example.com",
            "",
        )

        app = self._build_app()

        @app.get("/pending-count")
        async def _pending_count_probe(request: Request):
            context = build_template_context(request, CookieSession(data={}))
            return {"pending_users_count": context["pending_users_count"]}

        try:
            client = self.TestClient(app)
            response = client.get("/pending-count")
            self.assertEqual(response.status_code, 200)
            self.assertGreaterEqual(response.json()["pending_users_count"], 1)
        finally:
            self.rundb.userdb.users.delete_many({"username": username})
            self.rundb.userdb.clear_cache()

    def test_ui_home_redirect_status(self):
        app = self._build_app(include_views=True)
        client = self.TestClient(app)
        response = client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/tests"))


if __name__ == "__main__":
    unittest.main()
