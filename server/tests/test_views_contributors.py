# ruff: noqa: ANN201, ANN206, D100, D101, D102, E501, INP001, PT009
"""Test `/contributors` HTTP contracts."""

from datetime import UTC, datetime
from pathlib import Path

from ui_user_test_case import UiUserTestCase

from fishtest.http.settings import HTMX_INPUT_CHANGED_DELAY_MS


class TestViewsContributors(UiUserTestCase):
    username = "TestContributorsUser"

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
                "tests_repo": self.tests_repo,
            },
            {
                "username": miss_name,
                "cpu_hours": 5,
                "games": 20,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": self.tests_repo,
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
                    "tests_repo": self.tests_repo,
                }
            )

        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            response_page_1 = self.client.get(
                "/contributors?search=MissingContributorUser"
            )
            self.assertEqual(response_page_1.status_code, 200)
            self.assertIn("?page=2", response_page_1.text)
            self.assertNotIn(
                "search=MissingContributorUser",
                response_page_1.text,
            )
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
                "tests_repo": self.tests_repo,
            },
            {
                "username": "SortAAAUser",
                "cpu_hours": 20,
                "games": 10,
                "tests": 1,
                "games_per_hour": 1,
                "last_updated": datetime.now(UTC),
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
            }
        )
        self.rundb.userdb.user_cache.insert_many(docs)
        try:
            self._login_user()
            response = self.client.get("/contributors?findme=1", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("location", "")
            self.assertIn(f"highlight={self.username}", location)
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
            self.assertIn(f"highlight={self.username}", location)
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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
            self.assertIn(f"highlight={self.username}", location)
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
        self.assertIn('data-findme-cookie-name="contributors_findme"', response.text)
        self.assertIn('data-findme-cookie-max-age="', response.text)
        self.assertIn("static/js/contributors.js", response.text)
        self.assertNotIn('const FINDME_COOKIE = "contributors_findme"', response.text)

    def test_contributors_sort_headers_use_hx_get_with_push_url(self):
        response = self.client.get("/contributors?sort=username&order=asc")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="contributors_table"', response.text)
        self.assertIn('aria-sort="ascending"', response.text)
        self.assertIn(
            'hx-get="/contributors?sort=cpu_hours&order=asc&view=paged"',
            response.text,
        )
        self.assertIn('hx-target="#contributors-content"', response.text)
        self.assertIn('hx-push-url="true"', response.text)

    def test_contributors_hx_fragment_syncs_outer_hidden_sort_state(self):
        response = self.client.get(
            "/contributors?sort=username&order=asc&view=all",
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'id="contributors_sort" name="sort" value="username" hx-swap-oob="true"',
            response.text,
        )
        self.assertIn(
            'id="contributors_order" name="order" value="asc" hx-swap-oob="true"',
            response.text,
        )
        self.assertIn(
            'id="contributors_view" name="view" value="all" hx-swap-oob="true"',
            response.text,
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
                "tests_repo": self.tests_repo,
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
                "tests_repo": self.tests_repo,
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

    def test_contributors_js_uses_single_root_path_cookie(self):
        js_path = (
            Path(__file__).resolve().parents[1]
            / "fishtest"
            / "static"
            / "js"
            / "contributors.js"
        )
        js_source = js_path.read_text(encoding="utf-8")

        self.assertIn("path=/; max-age=${cookieMaxAge}; SameSite=Lax", js_source)
        self.assertNotIn(
            "path=/contributors; max-age=${cookieMaxAge}; SameSite=Lax",
            js_source,
        )
        self.assertNotIn("getLatestCookie", js_source)
