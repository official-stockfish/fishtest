# ruff: noqa: ANN201, ANN206, D100, D101, D102, INP001, PLC0415, PT009
"""Test the proof-of-work gate for anonymous UI traffic."""

import hashlib
import json
import re
import unittest
from itertools import count

import test_support

SECRET = "test-secret"
DIFFICULTY = 8


def _solve(challenge: str, difficulty: int) -> int:
    from fishtest.http.proof_of_work import _leading_zero_bits_ok

    for nonce in count():
        digest = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
        if _leading_zero_bits_ok(digest, difficulty):
            return nonce
    raise AssertionError  # unreachable


def _challenge_config(html: str) -> dict:
    match = re.search(r"var cfg = (\{.*?\});", html)
    assert match is not None
    return json.loads(match.group(1))


class TestProofOfWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.FastAPI, cls.TestClient = test_support.require_fastapi()

    def _make_client(self, *, difficulty: int = DIFFICULTY):
        from fastapi.responses import PlainTextResponse

        from fishtest.http.proof_of_work import ProofOfWorkMiddleware

        app = self.FastAPI()

        @app.get("/tests")
        def tests_page():
            return PlainTextResponse("tests page")

        @app.post("/login")
        def login():
            return PlainTextResponse("login ok")

        @app.get("/api/active_runs")
        def active_runs():
            return {"runs": []}

        @app.post("/api/request_task")
        def request_task():
            return {"task": None}

        app.add_middleware(
            ProofOfWorkMiddleware, secret_key=SECRET, difficulty=difficulty
        )

        class _FakeSession:
            """Stand-in for the session middleware: X-Test-User logs in."""

            def __init__(self, inner):
                self.inner = inner

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    headers = dict(scope["headers"])
                    user = headers.get(b"x-test-user", b"").decode()
                    scope["session"] = {"user": user} if user else {}
                await self.inner(scope, receive, send)

        app.add_middleware(_FakeSession)
        return self.TestClient(app)

    def _pass_challenge(self, client, path="/tests"):
        page = client.get(path)
        cfg = _challenge_config(page.text)
        nonce = _solve(cfg["challenge"], cfg["difficulty"])
        return client.post(
            "/__pow/verify",
            data={"challenge": cfg["challenge"], "nonce": nonce, "next": cfg["next"]},
            follow_redirects=False,
        )

    def test_anonymous_ui_request_gets_challenge(self):
        client = self._make_client()
        response = client.get("/tests?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("tests page", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        cfg = _challenge_config(response.text)
        self.assertEqual(cfg["difficulty"], DIFFICULTY)
        self.assertEqual(cfg["next"], "/tests?page=2")

    def test_authenticated_user_is_never_challenged(self):
        client = self._make_client()
        response = client.get("/tests", headers={"X-Test-User": "alice"})
        self.assertEqual(response.text, "tests page")
        response = client.post("/login", headers={"X-Test-User": "alice"})
        self.assertEqual(response.text, "login ok")

    def test_api_paths_are_exempt(self):
        client = self._make_client()
        self.assertEqual(client.get("/api/active_runs").json(), {"runs": []})
        self.assertEqual(client.post("/api/request_task").json(), {"task": None})

    def test_solved_challenge_grants_pass_cookie(self):
        from fishtest.http.proof_of_work import POW_COOKIE_NAME

        client = self._make_client()
        response = self._pass_challenge(client, "/tests?page=2")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/tests?page=2")
        self.assertIn(POW_COOKIE_NAME, response.cookies)
        self.assertIn("httponly", response.headers["set-cookie"].lower())

        self.assertEqual(client.get("/tests").text, "tests page")
        self.assertEqual(client.post("/login").text, "login ok")

    def test_wrong_nonce_is_rejected(self):
        from fishtest.http.proof_of_work import POW_COOKIE_NAME

        client = self._make_client(difficulty=20)
        cfg = _challenge_config(client.get("/tests").text)
        nonce = 0
        while True:  # find a nonce that does NOT satisfy the difficulty
            digest = hashlib.sha256(f"{cfg['challenge']}:{nonce}".encode()).digest()
            if digest[0] != 0:
                break
            nonce += 1
        response = client.post(
            "/__pow/verify",
            data={"challenge": cfg["challenge"], "nonce": nonce, "next": "/tests"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertNotIn(POW_COOKIE_NAME, response.cookies)
        self.assertNotEqual(client.get("/tests").text, "tests page")

    def test_forged_challenge_and_cookie_are_rejected(self):
        from fishtest.http.proof_of_work import POW_COOKIE_NAME

        client = self._make_client()
        forged = "deadbeef.1.0000000000000000.AAAA.BBBB"
        response = client.post(
            "/__pow/verify",
            data={"challenge": forged, "nonce": _solve(forged, 1), "next": "/tests"},
            follow_redirects=False,
        )
        self.assertNotIn(POW_COOKIE_NAME, response.cookies)

        client.cookies.set(POW_COOKIE_NAME, "garbage.value.sig")
        self.assertNotEqual(client.get("/tests").text, "tests page")

    def test_open_redirect_is_blocked(self):
        client = self._make_client()
        cfg = _challenge_config(client.get("/tests").text)
        nonce = _solve(cfg["challenge"], cfg["difficulty"])
        for evil in ("https://evil.example", "//evil.example", "/\\evil.example"):
            response = client.post(
                "/__pow/verify",
                data={"challenge": cfg["challenge"], "nonce": nonce, "next": evil},
                follow_redirects=False,
            )
            self.assertEqual(response.headers["location"], "/tests")

    def test_htmx_and_non_get_requests_are_not_served_the_page(self):
        client = self._make_client()
        response = client.get("/tests", headers={"HX-Request": "true"})
        self.assertEqual(response.headers.get("hx-refresh"), "true")
        self.assertEqual(response.text, "")
        response = client.post("/login")
        self.assertEqual(response.status_code, 403)

    def test_difficulty_zero_disables_gate(self):
        client = self._make_client(difficulty=0)
        self.assertEqual(client.get("/tests").text, "tests page")


if __name__ == "__main__":
    unittest.main()
