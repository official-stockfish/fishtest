import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_support
from starlette.responses import Response

from fishtest.api import WORKER_API_PATHS
from fishtest.app import _require_single_worker_on_primary
from fishtest.http import cookie_session, jinja
from fishtest.http.errors import _WORKER_API_PATHS
from fishtest.http.middleware import _get_blocked_cached
from fishtest.http.settings import AppSettings
from fishtest.http.ui_pipeline import apply_http_cache


class TemplateRequestStaticUrlTests(unittest.TestCase):
    def test_static_url_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir) / "static"
            static_dir.mkdir(parents=True, exist_ok=True)

            outside = Path(tmpdir) / "secret.txt"
            outside.write_text("nope", encoding="utf-8")

            original_dir = jinja._STATIC_DIR
            jinja._STATIC_DIR = static_dir
            jinja._static_file_token.cache_clear()
            try:
                url = jinja.static_url("fishtest:static/../secret.txt")
                self.assertTrue(url.startswith("/static/"))
                self.assertNotIn("?x=", url)
            finally:
                jinja._STATIC_DIR = original_dir
                jinja._static_file_token.cache_clear()

    def test_static_url_token_is_urlsafe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir) / "static"
            static_dir.mkdir(parents=True, exist_ok=True)
            target = static_dir / "css" / "site.css"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("body{}", encoding="utf-8")

            original_dir = jinja._STATIC_DIR
            jinja._STATIC_DIR = static_dir
            jinja._static_file_token.cache_clear()
            try:
                url = jinja.static_url("fishtest:static/css/site.css")
                self.assertIn("?x=", url)
                token = url.split("?x=", 1)[1]
                self.assertRegex(token, r"^[A-Za-z0-9_-]+$")
                self.assertNotIn("=", token)
            finally:
                jinja._STATIC_DIR = original_dir
                jinja._static_file_token.cache_clear()

    def test_static_token_cache_eviction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir) / "static"
            static_dir.mkdir(parents=True, exist_ok=True)
            (static_dir / "a.txt").write_text("a", encoding="utf-8")
            (static_dir / "b.txt").write_text("b", encoding="utf-8")

            original_dir = jinja._STATIC_DIR
            jinja._STATIC_DIR = static_dir
            jinja._static_file_token.cache_clear()
            try:
                jinja._static_file_token("a.txt")
                jinja._static_file_token("b.txt")
                cache_info = jinja._static_file_token.cache_info()
                currsize = cache_info.currsize
                maxsize = cache_info.maxsize
                self.assertIsNotNone(maxsize)
                assert maxsize is not None
                self.assertLessEqual(
                    currsize,
                    maxsize,
                )
            finally:
                jinja._STATIC_DIR = original_dir
                jinja._static_file_token.cache_clear()


class CookieSessionTests(unittest.TestCase):
    def test_secret_missing_requires_opt_in(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                cookie_session._secret_key()

    def test_insecure_dev_fallback(self):
        with mock.patch.dict(
            os.environ,
            {cookie_session.INSECURE_DEV_ENV: "1"},
            clear=True,
        ):
            self.assertEqual(cookie_session._secret_key(), "insecure-dev-secret")

    def test_session_middleware_trims_flashes(self):
        with mock.patch.dict(
            os.environ,
            {"FISHTEST_AUTHENTICATION_SECRET": "test-secret"},
            clear=True,
        ):
            _FastAPI, TestClient = test_support.require_fastapi()
            app = _FastAPI()

            from fishtest.http.cookie_session import MAX_COOKIE_BYTES, load_session
            from fishtest.http.session_middleware import FishtestSessionMiddleware

            app.add_middleware(
                FishtestSessionMiddleware,
                secret_key=cookie_session.session_secret_key,
                session_cookie=cookie_session.SESSION_COOKIE_NAME,
                max_age=None,
                same_site=cookie_session.DEFAULT_SAMESITE,
                https_only=False,
            )

            from fastapi import Request

            @app.get("/flash")
            async def _flash(request: Request):
                session = load_session(request)
                for i in range(1000):
                    session.flash(f"msg-{i}")
                return Response("ok")

            client = TestClient(app)
            response = client.get("/flash")
            self.assertEqual(response.status_code, 200)
            set_cookie = response.headers.get("set-cookie")
            self.assertIsNotNone(set_cookie)
            cookie_value = set_cookie.split("fishtest_session=", 1)[1].split(
                ";",
                1,
            )[0]
            self.assertLessEqual(len(cookie_value.encode("utf-8")), MAX_COOKIE_BYTES)


class SettingsTests(unittest.TestCase):
    def test_primary_when_port_unknown(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = AppSettings.from_env()
        self.assertTrue(settings.is_primary_instance)

    def test_primary_when_primary_port_unknown(self):
        with mock.patch.dict(os.environ, {"FISHTEST_PORT": "8000"}, clear=True):
            settings = AppSettings.from_env()
        self.assertTrue(settings.is_primary_instance)

    def test_primary_when_ports_match(self):
        with mock.patch.dict(
            os.environ,
            {"FISHTEST_PORT": "8000", "FISHTEST_PRIMARY_PORT": "8000"},
            clear=True,
        ):
            settings = AppSettings.from_env()
        self.assertTrue(settings.is_primary_instance)

    def test_secondary_when_ports_differ(self):
        with mock.patch.dict(
            os.environ,
            {"FISHTEST_PORT": "8001", "FISHTEST_PRIMARY_PORT": "8000"},
            clear=True,
        ):
            settings = AppSettings.from_env()
        self.assertFalse(settings.is_primary_instance)


class RuntimeInvariantTests(unittest.TestCase):
    def test_primary_requires_single_worker_uvicorn(self):
        settings = AppSettings(port=8000, primary_port=8000, is_primary_instance=True)
        with mock.patch.dict(os.environ, {"UVICORN_WORKERS": "2"}, clear=True):
            with self.assertRaises(RuntimeError):
                _require_single_worker_on_primary(settings)

    def test_primary_requires_single_worker_web_concurrency(self):
        settings = AppSettings(port=8000, primary_port=8000, is_primary_instance=True)
        with mock.patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}, clear=True):
            with self.assertRaises(RuntimeError):
                _require_single_worker_on_primary(settings)

    def test_secondary_ignores_worker_settings(self):
        settings = AppSettings(port=8001, primary_port=8000, is_primary_instance=False)
        with mock.patch.dict(os.environ, {"UVICORN_WORKERS": "4"}, clear=True):
            _require_single_worker_on_primary(settings)


class ErrorHandlerWorkerPathsTests(unittest.TestCase):
    def test_worker_paths_source_of_truth(self):
        self.assertEqual(set(WORKER_API_PATHS), set(_WORKER_API_PATHS))


class BlockedUserCacheTests(unittest.TestCase):
    def test_blocked_cache_uses_ttl(self):
        class FakeUserDb:
            def __init__(self):
                self.calls = 0

            def get_blocked(self):
                self.calls += 1
                return [{"username": "u", "blocked": True}]

        userdb = FakeUserDb()

        with mock.patch("time.monotonic", side_effect=[1.0, 1.5, 5.0]):
            first = _get_blocked_cached(userdb)
            second = _get_blocked_cached(userdb)
            third = _get_blocked_cached(userdb)

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(userdb.calls, 2)


class HttpCacheHeaderTests(unittest.TestCase):
    def test_sets_header_when_missing_and_numeric(self):
        response = Response()
        result = apply_http_cache(response, {"http_cache": 60})
        self.assertIs(result, response)
        self.assertEqual(response.headers.get("Cache-Control"), "max-age=60")

    def test_preserves_existing_cache_control(self):
        response = Response(headers={"Cache-Control": "no-store"})
        apply_http_cache(response, {"http_cache": 60})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_ignores_non_int_coercible_value(self):
        response = Response()
        apply_http_cache(response, {"http_cache": "not-a-number"})
        self.assertIsNone(response.headers.get("Cache-Control"))
