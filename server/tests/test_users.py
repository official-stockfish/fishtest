# ruff: noqa: ANN201, ANN206, B025, B904, D100, D101, D102, E501, EM102, INP001, PLC0415, PT009, S105, TRY003

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

import test_support
from vtjson import ValidationError

from fishtest.http.cookie_session import REMEMBER_MAX_AGE_SECONDS
from fishtest.http.settings import HTMX_INPUT_CHANGED_DELAY_MS
from fishtest.run_cache import Prio
from fishtest.util import PASSWORD_MAX_LENGTH


class TestHttpUsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()

        cls.username = "JoeUser"
        cls.password = "secret"
        cls.signup_username = "JoeUserSignup"
        cls.signup_password = "CorrectHorseBatteryStaple123!"

        # Create a user used by login tests.
        cls.rundb.userdb.create_user(
            cls.username,
            cls.password,
            "email@email.email",
            "https://github.com/official-stockfish/Stockfish",
        )

    def setUp(self):
        # New client per test to avoid cookie/session leakage between tests.
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )
        # Keep login tests order-independent when other tests toggle flags.
        self._ensure_user_can_login()

    def _create_run(self) -> str:
        run_id = self.rundb.new_run(
            "master",
            "master",
            400,
            "10+0.01",
            "10+0.01",
            "book.pgn",
            "10",
            1,
            "",
            "",
            info="UI test run",
            resolved_base="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            resolved_new="347d613b0e2c47f90cbf1c5a5affe97303f1ac3d",
            msg_base="Base",
            msg_new="New",
            base_signature="123456",
            new_signature="654321",
            base_nets=["nn-0000000000a0.nnue"],
            new_nets=["nn-0000000000a0.nnue"],
            rescheduled_from="653db116cc309ae839563103",
            tests_repo="https://github.com/official-stockfish/Stockfish",
            auto_purge=False,
            username=self.username,
            start_time=datetime.now(UTC),
            arch_filter="avx",
        )
        run = self.rundb.get_run(run_id)
        run["approved"] = True
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)
        return str(run_id)

    def _login_user(self):
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
        self.rundb.userdb.save_user(user)

        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    @classmethod
    def tearDownClass(cls):
        test_support.cleanup_test_rundb(
            cls.rundb,
            clear_usernames=[cls.username, cls.signup_username],
            clear_runs=True,
            drop_runs=True,
        )

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/login",
            data={"username": self.username, "password": "badsecret"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        # UI 403s are rendered as HTML (login page) by glue error handlers.
        self.assertIn("Please login", response.text)

    def test_login_invalid_password_renders_flash(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": "badsecret",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid username or password.", response.text)

    def test_login_pending_then_success_redirects(self):
        # Pending is the default for new users; ensure it is set for this test.
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = True
        self.rundb.userdb.save_user(user)

        response = self.client.get("/login")
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pending approval", response.text)
        self.assertIn("manually approve your new account", response.text)

        # Unblock, then user can log in successfully.
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
        self.rundb.userdb.save_user(user)

        # GET again to ensure CSRF token is tied to the current cookie state.
        response = self.client.get("/login")
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("location", {k.lower() for k in response.headers})

    def test_signup_creates_user_and_redirects(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        with (
            patch.dict(
                "os.environ",
                {"FISHTEST_CAPTCHA_SECRET": "test-secret"},
                clear=False,
            ),
            patch(
                "fishtest.views.requests.post",
                return_value=type(
                    "_CaptchaResponse",
                    (),
                    {"json": staticmethod(lambda: {"success": True})},
                )(),
            ),
        ):
            response = self.client.post(
                "/signup",
                data={
                    "username": self.signup_username,
                    "password": self.signup_password,
                    "password2": self.signup_password,
                    "email": "joe@user.net",
                    "tests_repo": "https://github.com/official-stockfish/Stockfish",
                    "g-recaptcha-response": "captcha-ok",
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers.get("location", "").endswith("/login"))

    def test_signup_rejects_too_long_password(self):
        long_password = "A1!a" * 20
        self.assertGreater(len(long_password), PASSWORD_MAX_LENGTH)
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        response = self.client.post(
            "/signup",
            data={
                "username": "LongPasswordUser",
                "password": long_password,
                "password2": long_password,
                "email": "joe@user.net",
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f"Error! Password too long (max {PASSWORD_MAX_LENGTH} characters)",
            response.text,
        )

    def test_login_page_has_csrf_meta(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_login_page_defaults_remember_me_checked(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="stay_logged_in" value="0"', response.text)
        self.assertIn('name="stay_logged_in"', response.text)
        self.assertIn('id="staylogged"', response.text)
        self.assertIn("checked", response.text)

    def test_login_default_sets_persistent_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertIn(f"Max-Age={REMEMBER_MAX_AGE_SECONDS}", cookie)

    def test_login_duplicate_remember_fields_keep_persistent_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            content=urlencode(
                [
                    ("username", self.username),
                    ("password", self.password),
                    ("stay_logged_in", "0"),
                    ("stay_logged_in", "1"),
                    ("csrf_token", csrf),
                ]
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertIn(f"Max-Age={REMEMBER_MAX_AGE_SECONDS}", cookie)

    def test_login_explicit_non_remember_sets_session_cookie(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "stay_logged_in": "0",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("set-cookie", "")
        self.assertIn("fishtest_session=", cookie)
        self.assertNotIn("Max-Age=", cookie)

    def test_signup_page_has_csrf_meta(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)
        self.assertTrue(csrf)

    def test_signup_requires_csrf(self):
        response = self.client.post(
            "/signup",
            data={
                "username": "nouser",
                "password": "badpass",
                "password2": "badpass",
                "email": "nouser@example.com",
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Register", response.text)

    def test_logout_redirects_and_clears_cookie(self):
        response = self.client.get("/login")
        csrf = test_support.extract_csrf_token(response.text)
        response = self.client.post(
            "/login",
            data={
                "username": self.username,
                "password": self.password,
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            "/logout",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("location", {k.lower() for k in response.headers})
        self.assertIn("set-cookie", {k.lower() for k in response.headers})

    def test_notfound_returns_html(self):
        response = self.client.get("/no-such-route")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Oops! Page not found.", response.text)

    def test_list_and_detail_pages_render(self):
        response = self.client.get("/contributors")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Contributors", response.text)

        run_id = self._create_run()
        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(run_id), response.text)

    def test_contributors_search_goto_redirects_to_best_match(self):
        hit_name = "HxSearchMatchUser"
        miss_name = "HxSearchMissUser"
        docs = [
            {
                "username": hit_name,
                "cpu_hours": 10,
                "games": 50,
                "tests": 2,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
            {
                "username": miss_name,
                "cpu_hours": 5,
                "games": 20,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get(
                "/contributors?search=matchuser",
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn("highlight=HxSearchMatchUser", location)
            self.assertIn("#me", location)
            self.assertNotIn("search=", location)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$in": [hit_name, miss_name]}}
            )

    def test_contributors_pagination_drops_search_param(self):
        docs = []
        for idx in range(120):
            docs.append(
                {
                    "username": f"H13PageUser{idx:03d}",
                    "cpu_hours": 1000 - idx,
                    "games": 100 + idx,
                    "tests": 1,
                    "games_per_hour": 1,
                    "last_updated": datetime.now(UTC),
                    "tests_repo": "https://github.com/official-stockfish/Stockfish",
                }
            )

        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response_page_1 = self.client.get("/contributors?search=NoSuchUser")
            self.assertEqual(response_page_1.status_code, 200)
            self.assertIn("?page=2", response_page_1.text)
            self.assertNotIn("search=NoSuchUser", response_page_1.text)
            self.assertIn("H13PageUser000", response_page_1.text)
            self.assertNotIn("H13PageUser119", response_page_1.text)

            response_page_2 = self.client.get("/contributors?page=2")
            self.assertEqual(response_page_2.status_code, 200)
            self.assertIn("H13PageUser119", response_page_2.text)
            self.assertNotIn("H13PageUser000", response_page_2.text)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^H13PageUser"}}
            )

    def test_contributors_sort_by_username_asc(self):
        docs = [
            {
                "username": "SortZZZUser",
                "cpu_hours": 10,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
            {
                "username": "SortAAAUser",
                "cpu_hours": 20,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            },
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get("/contributors?sort=username&order=asc")
            self.assertEqual(response.status_code, 200)
            self.assertLess(
                response.text.index("SortAAAUser"),
                response.text.index("SortZZZUser"),
            )
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$in": ["SortZZZUser", "SortAAAUser"]}}
            )

    def test_contributors_sort_by_tests_repo_asc(self):
        docs = [
            {
                "username": "SortRepoAAUser",
                "cpu_hours": 10,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/zeta-org/repo",
            },
            {
                "username": "SortRepoZZUser",
                "cpu_hours": 20,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/alpha-org/repo",
            },
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get("/contributors?sort=tests_repo&order=asc")
            self.assertEqual(response.status_code, 200)
            self.assertLess(
                response.text.index("SortRepoZZUser"),
                response.text.index("SortRepoAAUser"),
            )
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$in": ["SortRepoAAUser", "SortRepoZZUser"]}}
            )

    def test_contributors_invalid_sort_falls_back(self):
        response = self.client.get("/contributors?sort=__proto__")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Contributors", response.text)

    def test_contributors_rank_is_global_on_page_two(self):
        docs = [
            {
                "username": f"RankUser{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(110)
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get("/contributors?page=2")
            self.assertEqual(response.status_code, 200)
            self.assertIn('data-sort-value="101"', response.text)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^RankUser"}}
            )

    def test_contributors_findme_redirects_to_page(self):
        docs = [
            {
                "username": f"FindMeFiller{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(105)
        ]
        docs.append(
            {
                "username": self.username,
                "cpu_hours": 1,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
        )
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            self._login_user()
            response = self.client.get("/contributors?findme=1", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn("highlight=JoeUser", location)
            self.assertIn("#me", location)
            self.assertIn("page=2", location)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^FindMeFiller"}}
            )
            self.rundb.userdb.user_cache.delete_one({"username": self.username})

    def test_contributors_findme_overrides_search_goto(self):
        docs = [
            {
                "username": f"FindMeSearchFiller{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(105)
        ]
        docs.append(
            {
                "username": self.username,
                "cpu_hours": 1,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
        )
        docs.append(
            {
                "username": "DissMatchUser",
                "cpu_hours": 3000,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
        )
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            self._login_user()
            response = self.client.get(
                "/contributors?findme=1&search=diss",
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn("highlight=JoeUser", location)
            self.assertIn("findme=1", location)
            self.assertNotIn("highlight=DissMatchUser", location)
            self.assertNotIn("search=", location)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^(FindMeSearchFiller|DissMatchUser)"}}
            )
            self.rundb.userdb.user_cache.delete_one({"username": self.username})

    def test_contributors_findme_unauthenticated_no_redirect(self):
        response = self.client.get("/contributors?findme=1")
        self.assertEqual(response.status_code, 200)

    def test_contributors_search_goto_redirects_in_view_all(self):
        hit_name = "ViewAllSearchTarget"
        docs = [
            {
                "username": f"ViewAllSearchFiller{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(105)
        ]
        docs.append(
            {
                "username": hit_name,
                "cpu_hours": 1,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
        )
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get(
                "/contributors?view=all&search=target",
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn("view=all", location)
            self.assertIn(f"highlight={hit_name}", location)
            self.assertIn("#me", location)
            self.assertNotIn("search=", location)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^(ViewAllSearchFiller|ViewAllSearchTarget)"}}
            )

    def test_contributors_findme_redirects_in_view_all(self):
        docs = [
            {
                "username": f"ViewAllFindMeFiller{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(105)
        ]
        docs.append(
            {
                "username": self.username,
                "cpu_hours": 1,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
        )
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            self._login_user()
            response = self.client.get(
                "/contributors?view=all&findme=1",
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn("view=all", location)
            self.assertIn("highlight=JoeUser", location)
            self.assertIn("findme=1", location)
            self.assertIn("#me", location)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^ViewAllFindMeFiller"}}
            )
            self.rundb.userdb.user_cache.delete_one({"username": self.username})

    def test_contributors_search_form_uses_htmx_keystroke_goto(self):
        response = self.client.get("/contributors")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="search_contributors_form"', response.text)
        expected_trigger = (
            'hx-trigger="submit, input changed delay:'
            f"{HTMX_INPUT_CHANGED_DELAY_MS}ms from:#search_contributors"
        )
        self.assertIn(expected_trigger, response.text)
        self.assertNotIn("Typing filters current page instantly", response.text)
        self.assertNotIn("Jump to my rank</a>", response.text)
        self.assertIn('type="search"', response.text)
        self.assertIn('const FINDME_COOKIE = "contributors_findme"', response.text)
        self.assertIn("if (findme.checked) {", response.text)
        self.assertIn('search.value = "";', response.text)
        self.assertIn(
            'search.addEventListener("input", clearFindmeOnSearchInput);', response.text
        )
        self.assertIn(
            'const findmeFromUrl = params.get("findme") === "1";', response.text
        )
        self.assertIn('if (remembered === "false") {', response.text)
        self.assertIn('setCookie(FINDME_COOKIE, "true");', response.text)
        self.assertIn(
            'const highlightedRow = document.getElementById("me");', response.text
        )
        self.assertIn("const hasRenderedHighlight =", response.text)
        self.assertIn('form && typeof form.requestSubmit === "function"', response.text)
        self.assertIn(
            "requestAnimationFrame(() => form.requestSubmit());", response.text
        )

    def test_contributors_view_all_hides_pagination(self):
        docs = [
            {
                "username": f"ViewAllUser{idx:04d}",
                "cpu_hours": 5000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(150)
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get("/contributors?view=all")
            self.assertEqual(response.status_code, 200)
            self.assertIn("ViewAllUser0120", response.text)
            self.assertNotIn("?page=2", response.text)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^ViewAllUser"}}
            )

    def test_contributors_cpu_bar_removed(self):
        docs = [
            {
                "username": f"CueUser{idx:04d}",
                "cpu_hours": 3000 - idx,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": "https://github.com/official-stockfish/Stockfish",
            }
            for idx in range(120)
        ]
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response = self.client.get("/contributors?view=all")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('class="cpu-bar"', response.text)
        finally:
            self.rundb.userdb.user_cache.delete_many(
                {"username": {"$regex": "^CueUser"}}
            )

    def test_workers_server_side_filter_hx_fragment(self):
        recent_worker = "hxrecent-1cores-abcd"
        old_worker = "hxold-1cores-abcd"

        self.rundb.workerdb.update_worker(recent_worker, blocked=True, message="recent")
        self.rundb.workerdb.update_worker(old_worker, blocked=True, message="old")
        self.rundb.workerdb.workers.update_one(
            {"worker_name": old_worker},
            {"$set": {"last_updated": datetime.now(UTC) - timedelta(days=10)}},
        )
        self.rundb.workerdb.workers.update_one(
            {"worker_name": recent_worker},
            {"$set": {"last_updated": datetime.now(UTC) - timedelta(days=1)}},
        )

        try:
            response = self.client.get(
                "/workers/show?filter=gt-5days",
                headers={"HX-Request": "true"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(old_worker, response.text)
            self.assertNotIn(recent_worker, response.text)
            self.assertIn("<template>", response.text)
            self.assertIn('id="workers-table-toggle"', response.text)
            self.assertIn('hx-swap-oob="true"', response.text)
            self.assertIn("Modified &gt; 5 days ago", response.text)
            self.assertNotIn("<table", response.text)
        finally:
            self.rundb.workerdb.workers.delete_many(
                {"worker_name": {"$in": [recent_worker, old_worker]}}
            )

    def test_workers_hx_empty_state_fragment_renders_placeholder_row(self):
        with patch.object(self.rundb.workerdb, "get_blocked_workers", return_value=[]):
            response = self.client.get(
                "/workers/show?filter=all-workers",
                headers={"HX-Request": "true"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("No blocked workers", response.text)
        self.assertIn('colspan="3"', response.text)
        self.assertNotIn("<table", response.text)

    def test_user_management_hx_empty_state_fragment_renders_placeholder_row(self):
        user = self.rundb.userdb.get_user(self.username)
        original_pending = user.get("pending", False)
        original_groups = list(user.get("groups", []))
        user["pending"] = False
        if "group:approvers" not in user["groups"]:
            user["groups"].append("group:approvers")
        self.rundb.userdb.save_user(user)

        try:
            self._login_user()

            with patch.object(self.rundb.userdb, "get_users", return_value=[]):
                response = self.client.get(
                    "/user_management?group=blocked",
                    headers={"HX-Request": "true"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertIn("No blocked users", response.text)
            self.assertIn('colspan="20"', response.text)
            self.assertNotIn("<table", response.text)
        finally:
            cleanup_user = self.rundb.userdb.get_user(self.username)
            cleanup_user["pending"] = original_pending
            cleanup_user["groups"] = original_groups
            self.rundb.userdb.save_user(cleanup_user)

    def test_sorting_js_guards_irregular_rows(self):
        js_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "js"
            / "application.js"
        )
        js_source = js_path.read_text(encoding="utf-8")

        # Guardrail assertions for E2 sorter hardening.
        self.assertIn('row.dataset.noSort === "true"', js_source)
        self.assertIn("columnIndex >= row.children.length", js_source)
        self.assertIn("const cell = tr?.children?.[idx];", js_source)
        self.assertIn("if (!cell)", js_source)

    def test_tests_stop_hx_detail_redirects_home(self):
        self._login_user()
        run_id = self._create_run()

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/tests/stop",
            data={
                "run-id": run_id,
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_delete_hx_redirects_home(self):
        self._login_user()
        run_id = self._create_run()

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/tests/delete",
            data={
                "run-id": run_id,
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_purge_hx_detail_redirects_home(self):
        self._login_user()
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        self.rundb.set_inactive_run(run)

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/tests/purge",
            data={
                "run-id": run_id,
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_stop_hx_detail_error_redirects_home(self):
        """HX request hitting can_modify_run failure follows regular redirect flow."""
        # Create a run owned by a different user, then try to stop it.
        self._login_user()
        run_id = self._create_run()
        # Change run ownership so can_modify_run fails.
        run = self.rundb.get_run(run_id)
        run["args"]["username"] = "some_other_user"
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/tests/stop",
            data={
                "run-id": run_id,
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_delete_hx_error_redirects_home(self):
        """HX request hitting can_modify_run failure on delete follows redirect flow."""
        self._login_user()
        run_id = self._create_run()
        run = self.rundb.get_run(run_id)
        run["args"]["username"] = "some_other_user"
        self.rundb.buffer(run, priority=Prio.SAVE_NOW)

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        response = self.client.post(
            "/tests/delete",
            data={
                "run-id": run_id,
                "csrf_token": csrf,
            },
            headers={"HX-Request": "true"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_modify_sends_csrf_token(self):
        """Modify form includes CSRF token and submission succeeds."""
        self._login_user()
        run_id = self._create_run()

        response = self.client.get(f"/tests/view/{run_id}")
        self.assertEqual(response.status_code, 200)
        csrf = test_support.extract_csrf_token(response.text)

        run = self.rundb.get_run(run_id)
        response = self.client.post(
            "/tests/modify",
            data={
                "run": run_id,
                "num-games": str(run["args"]["num_games"]),
                "priority": str(run["args"]["priority"]),
                "throughput": str(run["args"].get("throughput", 1000)),
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("location"), "/tests")

    def test_tests_modify_without_csrf_returns_403(self):
        """Modify form without CSRF token is rejected with 403."""
        self._login_user()
        run_id = self._create_run()

        response = self.client.post(
            "/tests/modify",
            data={
                "run": run_id,
                "num-games": "20000",
                "priority": "0",
                "throughput": "1000",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 403)

    def test_tests_user_hx_filter_fragment_keeps_notification_and_toggle_hooks(self):
        self._create_run()

        response = self.client.get(
            f"/tests/user/{self.username}?success_only=1",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="tests-user-filters"', response.text)
        self.assertIn('id="notification_', response.text)
        self.assertIn('data-toggle-cookie-name="', response.text)
        self.assertIn('data-toggle-cookie-max-age="', response.text)

    def test_notifications_js_reinitializes_after_htmx_swaps(self):
        js_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "js"
            / "notifications.js"
        )
        js_source = js_path.read_text(encoding="utf-8")

        self.assertIn('document.addEventListener("htmx:afterSwap"', js_source)
        self.assertIn('document.addEventListener("htmx:load"', js_source)
        self.assertIn("initializeNotificationButtons(target)", js_source)

    def test_user_management_lazy_group_hx_fragment(self):
        pending_user = "HxPendingGroupUser"
        blocked_user = "HxBlockedGroupUser"

        self.rundb.userdb.create_user(
            pending_user,
            "secret",
            "pending-group@example.com",
            "https://github.com/official-stockfish/Stockfish",
        )
        self.rundb.userdb.create_user(
            blocked_user,
            "secret",
            "blocked-group@example.com",
            "https://github.com/official-stockfish/Stockfish",
        )

        blocked_doc = self.rundb.userdb.get_user(blocked_user)
        blocked_doc["pending"] = False
        blocked_doc["blocked"] = True
        self.rundb.userdb.save_user(blocked_doc)

        approver = self.rundb.userdb.get_user(self.username)
        original_pending = approver.get("pending", False)
        original_groups = list(approver.get("groups", []))
        approver["pending"] = False
        if "group:approvers" not in approver["groups"]:
            approver["groups"].append("group:approvers")
        self.rundb.userdb.save_user(approver)

        try:
            response = self.client.get("/login")
            csrf = test_support.extract_csrf_token(response.text)
            login = self.client.post(
                "/login",
                data={
                    "username": self.username,
                    "password": self.password,
                    "csrf_token": csrf,
                },
                follow_redirects=False,
            )
            self.assertEqual(login.status_code, 302)

            response = self.client.get(
                "/user_management?group=blocked",
                headers={"HX-Request": "true"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(blocked_user, response.text)
            self.assertNotIn(pending_user, response.text)
            self.assertIn("<template>", response.text)
            self.assertIn('id="users-table-toggle"', response.text)
            self.assertIn('hx-swap-oob="true"', response.text)
            self.assertIn(">Blocked</button>", response.text)
            self.assertNotIn("<table", response.text)
        finally:
            cleanup_approver = self.rundb.userdb.get_user(self.username)
            cleanup_approver["pending"] = original_pending
            cleanup_approver["groups"] = original_groups
            self.rundb.userdb.save_user(cleanup_approver)

            pending_doc = self.rundb.userdb.get_user(pending_user)
            if pending_doc is not None:
                self.rundb.userdb.remove_user(pending_doc, self.username)
            blocked_doc = self.rundb.userdb.get_user(blocked_user)
            if blocked_doc is not None:
                self.rundb.userdb.remove_user(blocked_doc, self.username)

    @patch("fishtest.views.gh.rate_limit")
    def test_rate_limits_full_page_and_hx_fragment(self, mock_rate_limit):
        mock_rate_limit.return_value = {
            "remaining": 4321,
            "reset": 1700000000,
        }

        full_response = self.client.get("/rate_limits")
        self.assertEqual(full_response.status_code, 200)
        self.assertIn("<!doctype html>", full_response.text.lower())
        self.assertIn("<th>Server</th>", full_response.text)
        self.assertIn("<th>Client</th>", full_response.text)
        self.assertIn('id="server_rate_limit"', full_response.text)
        self.assertIn('id="client_rate_limit"', full_response.text)
        self.assertIn('hx-trigger="load, every ', full_response.text)

        fragment_response = self.client.get("/rate_limits/server")
        self.assertEqual(fragment_response.status_code, 200)
        self.assertNotIn("<!doctype html>", fragment_response.text.lower())
        self.assertIn("4321", fragment_response.text)
        self.assertIn(
            'id="server_reset" hx-swap-oob="innerHTML"', fragment_response.text
        )

    @patch("fishtest.views.gh.rate_limit")
    def test_rate_limits_hx_header_still_returns_full_page(self, mock_rate_limit):
        mock_rate_limit.return_value = {
            "remaining": 123,
            "reset": 1700000000,
        }
        response = self.client.get(
            "/rate_limits",
            headers={"HX-Request": "true", "Sec-Fetch-Mode": "navigate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("<!doctype html>", response.text.lower())

    def test_add_user_group_raises_on_duplicate(self):
        """Ensure adding a duplicate group raises ValidationError from userdb."""
        username = "GroupTestUser"
        # create a fresh user for this test
        self.rundb.userdb.create_user(username, "pwd", "g@u.com", "")
        try:
            self.rundb.userdb.add_user_group(username, "approvers")
            self.rundb.userdb.add_user_group(username, "dummy")
            with self.assertRaises(ValidationError):
                self.rundb.userdb.add_user_group(username, "approvers")
        finally:
            # cleanup
            self.rundb.userdb.users.delete_one({"username": username})
            self.rundb.userdb.user_cache.delete_one({"username": username})
            self.rundb.userdb.clear_cache()

    def _check_auth_with_flag(self, field, expected_error, expected_code):
        """Set a user flag, verify authenticate() returns the expected error, restore."""
        user = self.rundb.userdb.get_user(self.username)
        original = user.get(field)
        user[field] = True
        self.rundb.userdb.save_user(user)
        try:
            token = self.rundb.userdb.authenticate(self.username, self.password)
            self.assertEqual(token["error"], expected_error)
            self.assertEqual(token["error_code"], expected_code)
        finally:
            user = self.rundb.userdb.get_user(self.username)
            user[field] = original
            self.rundb.userdb.save_user(user)

    def _ensure_user_can_login(self):
        user = self.rundb.userdb.get_user(self.username)
        user["pending"] = False
        user["blocked"] = False
        self.rundb.userdb.save_user(user)

    def test_authenticate_unknown_user(self):
        token = self.rundb.userdb.authenticate("NoSuchUser", "x")
        self.assertEqual(token["error"], "Invalid username or password.")
        self.assertEqual(token["error_code"], "invalid_credentials")

    def test_authenticate_blocked_user(self):
        self._check_auth_with_flag("blocked", "Your account is blocked.", "blocked")

    def test_authenticate_pending_user(self):
        self._check_auth_with_flag(
            "pending", "Your account is pending approval.", "pending"
        )


if __name__ == "__main__":
    unittest.main()
