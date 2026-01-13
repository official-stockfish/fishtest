# ruff: noqa: ANN201, ANN206, D100, D101, D102, E501, INP001, PLC0415, PT009

import unittest

import test_support


class TestHttpUiSessionSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_support.require_fastapi()

        cls.rundb = test_support.get_rundb()

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
        )

    def test_ui_404_commits_session_cookie(self):
        from fishtest.http.cookie_session import SESSION_COOKIE_NAME

        client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=False,
        )

        response = client.get("/this-ui-route-does-not-exist")
        self.assertEqual(response.status_code, 404)

        # base.html.j2 calls request.session.get_csrf_token(), so the session becomes dirty
        # and must be committed even on UI error pages.
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)

    def test_csrf_failure_is_ui_403_not_json(self):
        from fastapi import Request
        from fastapi.responses import HTMLResponse

        from fishtest.http.cookie_session import SESSION_COOKIE_NAME, load_session
        from fishtest.http.csrf import csrf_or_403, csrf_token_from_form

        _FastAPI, TestClient = test_support.require_fastapi()

        app = test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=False,
        )

        @app.post("/csrf-probe")
        async def _csrf_probe(request: Request):
            session = load_session(request)
            form = await request.form()
            csrf_or_403(
                request=request,
                session=session,
                form_token=csrf_token_from_form(form),
            )
            return HTMLResponse("ok")

        client = TestClient(app)
        response = client.post("/csrf-probe", data={})

        self.assertEqual(response.status_code, 403)
        content_type = response.headers.get("content-type", "")
        self.assertTrue(content_type.startswith("text/html"))
        self.assertNotIn("application/json", content_type)

        # UI 403 rendering flashes + includes CSRF meta token, so session should be committed.
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn(f"{SESSION_COOKIE_NAME}=", set_cookie)


if __name__ == "__main__":
    unittest.main()
