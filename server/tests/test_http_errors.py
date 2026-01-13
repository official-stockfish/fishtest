# ruff: noqa: ANN201, ANN206, D100, D101, D102, E501, INP001, PLC0415, PT009

import unittest

import test_support


class TestHttpErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Skips cleanly if FastAPI/TestClient (and its deps like httpx) aren't available.
        FastAPI, TestClient = test_support.require_fastapi()

        cls.rundb = test_support.get_rundb()
        cls.FastAPI = FastAPI
        cls.TestClient = TestClient

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_pgndb=True,
            clear_runs=True,
            drop_runs=True,
        )

    def test_ui_404_is_html(self):
        client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )

        response = client.get("/this-ui-route-does-not-exist")
        self.assertEqual(response.status_code, 404)

        content_type = response.headers.get("content-type", "")
        self.assertTrue(
            content_type.startswith("text/html"),
            msg=f"expected text/html content-type, got {content_type}",
        )

    def test_api_404_is_json(self):
        client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=True,
            include_views=False,
        )

        response = client.get("/api/this-api-route-does-not-exist")
        self.assertEqual(response.status_code, 404)

        content_type = response.headers.get("content-type", "")
        self.assertTrue(
            content_type.startswith("application/json"),
            msg=f"expected application/json content-type, got {content_type}",
        )
        self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_worker_validation_error_is_shaped(self):
        from pydantic import BaseModel

        app = test_support.build_test_app(
            rundb=self.rundb,
            include_api=False,
            include_views=False,
        )

        class Body(BaseModel):
            required_field: int

        @app.post("/api/request_task")
        def _worker_validation_probe(body: Body):
            _ = body
            return {"ok": True}

        client = self.TestClient(app)
        response = client.post("/api/request_task", json={})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body.get("error"), "/api/request_task: invalid request")
        self.assertTrue(isinstance(body.get("duration"), (int, float)))


if __name__ == "__main__":
    unittest.main()
