# ruff: noqa: ANN201, ANN206, D100, D101, D102, INP001, PT009
"""Test UI route HTTP method contracts."""

import unittest

import test_support

_GET_ONLY_ROUTES = {
    "/",
    "/actions",
    "/contributors",
    "/contributors/monthly",
    "/nns",
    "/rate_limits",
    "/rate_limits/server",
    "/sprt_calc",
    "/tests",
    "/tests/finished",
    "/tests/live_elo/{id}",
    "/tests/live_elo_update/{id}",
    "/tests/machines",
    "/tests/stats/{id}",
    "/tests/tasks/{id}",
    "/tests/user/{username}",
    "/tests/view/{id}",
    "/tests/view/{id}/detail",
    "/user_management",
    "/user_management/pending_count",
}

_DUAL_METHOD_ROUTES = {
    "/login",
    "/signup",
    "/tests/run",
    "/upload",
    "/user",
    "/user/{username}",
    "/workers/{worker_name}",
}

_POST_ONLY_ROUTES = {
    "/logout",
    "/tests/approve",
    "/tests/delete",
    "/tests/modify",
    "/tests/purge",
    "/tests/stop",
}


class TestViewRouteMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_support.require_fastapi()
        try:
            from fastapi.routing import APIRoute, iter_route_contexts

            from fishtest.views import _VIEW_ROUTES
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise unittest.SkipTest(
                f"Server dependencies missing ({exc.name}); skipping FastAPI HTTP tests",
            )

        cls.APIRoute = APIRoute
        # FastAPI 0.137.0 stores included routers as a tree in ``app.routes``;
        # ``iter_route_contexts`` is the supported way to walk it back to the
        # underlying routes.
        cls.iter_route_contexts = staticmethod(iter_route_contexts)
        cls.declared_view_paths = {path for _fn, path, _cfg in _VIEW_ROUTES}
        cls.rundb = test_support.get_rundb()

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(cls.rundb)

    def _build_client(self):
        return test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )

    def _route_methods(self):
        app = test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )
        route_methods = {
            ctx.path: set(ctx.methods or set())
            for ctx in self.iter_route_contexts(app.routes)
            if isinstance(ctx.original_route, self.APIRoute)
            and ctx.path in self.declared_view_paths
        }
        self.assertSetEqual(set(route_methods), self.declared_view_paths)
        return route_methods

    def test_registered_ui_route_methods_match_contract(self):
        expected_paths = _GET_ONLY_ROUTES | _DUAL_METHOD_ROUTES | _POST_ONLY_ROUTES
        expected = {path: {"GET"} for path in _GET_ONLY_ROUTES}
        expected.update({path: {"GET", "POST"} for path in _DUAL_METHOD_ROUTES})
        expected.update({path: {"POST"} for path in _POST_ONLY_ROUTES})

        self.assertSetEqual(self.declared_view_paths, expected_paths)
        self.assertEqual(self._route_methods(), expected)

    def test_get_only_ui_route_rejects_post(self):
        client = self._build_client()

        response = client.post("/tests")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.get("allow"), "GET")

    def test_get_only_ui_route_still_accepts_head(self):
        client = self._build_client()

        response = client.head("/tests")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    def test_options_is_not_part_of_ui_route_contract(self):
        client = self._build_client()

        response = client.options("/tests")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.get("allow"), "GET")

    def test_login_route_still_accepts_post(self):
        client = self._build_client()

        response = client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = client.post(
            "/login",
            data={
                "username": "route-method-user",
                "password": "wrong-password",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid username or password.", response.text)
