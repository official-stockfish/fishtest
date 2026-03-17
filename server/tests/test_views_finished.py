"""Test finished-runs search, pagination, and redirect helpers."""

import unittest
from datetime import UTC, datetime, timedelta

from fastapi.responses import RedirectResponse

from fishtest.http.settings import (
    FINISHED_FILTER_MAX_COUNT_ANON,
    FINISHED_FILTER_MAX_COUNT_AUTH,
)
from fishtest.views import get_paginated_finished_runs


class _CachedUsernamesStub:
    def __init__(self, usernames_versions):
        self._usernames_versions = [list(usernames) for usernames in usernames_versions]
        self._version_idx = 0
        self.cache_clear_calls = 0

    def __call__(self):
        return list(self._usernames_versions[self._version_idx])

    def cache_clear(self):
        self.cache_clear_calls += 1
        if self._version_idx < len(self._usernames_versions) - 1:
            self._version_idx += 1


class _FinishedRunsDbStub:
    def __init__(self):
        self.last_kwargs = None

    def get_finished_runs(self, **kwargs):
        self.last_kwargs = kwargs
        return [], 0


class _PriorityFinishedRunsDbStub(_FinishedRunsDbStub):
    def __init__(self, *, runs_by_username):
        super().__init__()
        self._runs_by_username = runs_by_username

    @staticmethod
    def _sort_timestamp(run):
        last_updated = run.get("last_updated")
        return 0.0 if last_updated is None else last_updated.timestamp()

    def get_finished_runs(self, **kwargs):
        self.last_kwargs = kwargs
        username = kwargs.get("username")
        usernames = kwargs.get("usernames")
        skip = kwargs.get("skip", 0)
        limit = kwargs.get("limit", 0)

        if usernames is not None:
            rows = []
            for matched_username in usernames:
                rows.extend(self._runs_by_username.get(matched_username, []))
            rows.sort(
                key=lambda run: (
                    self._sort_timestamp(run),
                    str(run.get("_id") or ""),
                ),
                reverse=True,
            )
            total = len(rows)
            return rows[skip : skip + limit], total

        if username is not None:
            rows = list(self._runs_by_username.get(username, []))
            total = len(rows)
            return rows[skip : skip + limit], total

        return [], 0


class _FinishedUsersStub:
    def __init__(self, usernames_versions):
        self.get_usernames = _CachedUsernamesStub(usernames_versions or [[]])


class _FinishedRunsRequestStub:
    def __init__(
        self,
        rundb,
        userdb,
        params=None,
        matchdict=None,
        authenticated_userid=None,
        host_url="http://localhost",
        path="/tests/finished",
    ):
        self.rundb = rundb
        self.userdb = userdb
        self.params = params or {}
        self.query_params = self.params
        self.matchdict = matchdict or {}
        self._authenticated_userid = authenticated_userid
        self.host_url = host_url
        self.path = path

    @property
    def authenticated_userid(self):
        return self._authenticated_userid

    @property
    def path_url(self):
        return f"{self.host_url}{self.path}"


class TestFinishedView(unittest.TestCase):
    def test_finished_view_username_filter_refreshes_cached_usernames_on_miss(self):
        rundb = _FinishedRunsDbStub()
        userdb = _FinishedUsersStub([["OlderFinisher"], ["FreshFinisher"]])
        request = _FinishedRunsRequestStub(
            rundb,
            userdb,
            params={"mode": "search", "user": "Fresh"},
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertIsNotNone(rundb.last_kwargs)
        self.assertEqual(rundb.last_kwargs["usernames"], ["FreshFinisher"])
        self.assertEqual(userdb.get_usernames.cache_clear_calls, 1)

    def test_finished_view_username_filter_uses_cached_usernames_for_exact_match(self):
        rundb = _FinishedRunsDbStub()
        userdb = _FinishedUsersStub([["OtherFinisher", "ExactFinisher"]])
        request = _FinishedRunsRequestStub(
            rundb,
            userdb,
            params={"mode": "search", "user": "ExactFinisher"},
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["usernames"], ["ExactFinisher"])
        self.assertEqual(userdb.get_usernames.cache_clear_calls, 0)

    def test_finished_view_passes_text_to_rundb(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["SearchUser"]]),
            params={"mode": "search", "text": '"branch search"'},
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["text"], '"branch search"')

    def test_finished_view_navigation_is_uncapped_for_anonymous_users(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AnonUser"]]),
        )

        get_paginated_finished_runs(request)

        self.assertIsNone(rundb.last_kwargs["max_count"])

    def test_finished_view_navigation_drops_stale_max_count(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AnonUser"]]),
            params={"max_count": "999999"},
        )

        response = get_paginated_finished_runs(request)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(
            response.headers.get("location"),
            "http://localhost/tests/finished?sort=time&order=desc",
        )

    def test_finished_view_authenticated_navigation_is_uncapped(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            authenticated_userid="AuthUser",
        )

        get_paginated_finished_runs(request)

        self.assertIsNone(rundb.last_kwargs["max_count"])

    def test_finished_view_navigation_redirects_filters_to_search_page(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            params={"user": "Auth", "text": "branch"},
        )

        response = get_paginated_finished_runs(request)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(
            response.headers.get("location"),
            "http://localhost/tests/finished?mode=search&sort=time&order=desc&user=Auth&text=branch",
        )

    def test_finished_search_anon_uses_default_cap_on_entry(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AnonUser"]]),
            params={"mode": "search"},
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["max_count"], FINISHED_FILTER_MAX_COUNT_ANON)

    def test_finished_search_authenticated_uses_default_cap_on_entry(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            params={"mode": "search"},
            authenticated_userid="AuthUser",
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["max_count"], FINISHED_FILTER_MAX_COUNT_AUTH)

    def test_finished_search_text_only_uses_default_cap(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            params={"mode": "search", "text": "ltc"},
            authenticated_userid="AuthUser",
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["text"], "ltc")
        self.assertEqual(rundb.last_kwargs["max_count"], FINISHED_FILTER_MAX_COUNT_AUTH)

    def test_finished_search_authenticated_allows_override_upward(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            params={"mode": "search", "user": "Auth", "max_count": "200000"},
            authenticated_userid="AuthUser",
        )

        get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(rundb.last_kwargs["max_count"], 200000)

    def test_finished_search_drops_status_tabs_from_canonical_url(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AuthUser"]]),
            params={"mode": "search", "success_only": "1", "user": "Auth"},
        )

        response = get_paginated_finished_runs(request, search_mode=True)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(
            response.headers.get("location"),
            "http://localhost/tests/finished?mode=search&sort=time&order=desc&user=Auth",
        )

    def test_finished_view_out_of_range_page_redirects_to_last_page(self):
        rundb = _FinishedRunsDbStub()
        rundb.get_finished_runs = lambda **kwargs: ([], 5000)
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AnonUser"]]),
            params={"page": "999999", "max_count": "999999"},
        )

        response = get_paginated_finished_runs(request)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(
            response.headers.get("location"),
            "http://localhost/tests/finished?sort=time&order=desc&page=999999",
        )

    def test_finished_view_navigation_mode_redirects_stale_max_count_for_anon(self):
        rundb = _FinishedRunsDbStub()
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["AnonUser"]]),
            params={"success_only": "1", "max_count": "1000"},
        )

        response = get_paginated_finished_runs(request)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(
            response.headers.get("location"),
            "http://localhost/tests/finished?sort=time&order=desc&success_only=1",
        )

    def test_finished_view_username_filter_ranks_prefix_matches_before_inner_substrings(
        self,
    ):
        now = datetime.now(UTC)
        rundb = _PriorityFinishedRunsDbStub(
            runs_by_username={
                "Disservin": [
                    {
                        "_id": "disservin-1",
                        "args": {
                            "username": "Disservin",
                            "info": "inner substring match",
                        },
                        "last_updated": now,
                    }
                ],
                "vincenegri": [
                    {
                        "_id": "vincenegri-1",
                        "args": {"username": "vincenegri", "info": "prefix match"},
                        "last_updated": now - timedelta(seconds=1),
                    }
                ],
            },
        )
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["Disservin", "vincenegri"]]),
            params={"mode": "search", "user": "vin"},
            authenticated_userid="AuthUser",
        )

        result = get_paginated_finished_runs(request, search_mode=True)

        self.assertEqual(
            [run["args"]["username"] for run in result["finished_runs"]],
            ["vincenegri", "Disservin"],
        )
        self.assertEqual(result["visible_finished_runs"], 2)
        self.assertEqual(result["num_finished_runs"], 2)

    def test_finished_view_multi_user_fallback_preserves_username_priority_order(self):
        """When the ranked merge budget is exceeded, the fallback must still
        group results by username priority (prefix first) instead of
        interleaving them by time."""
        now = datetime.now(UTC)
        # Build enough runs so that on a deep page the budget check
        # (len(usernames) * merge_window > 600) forces the fallback.
        # With 2 usernames and page 13 (skip=300, limit=25),
        # merge_window = 325, 2*325 = 650 > 600 → fallback.
        vince_runs = [
            {
                "_id": f"vince-{i}",
                "args": {"username": "vince", "info": ""},
                "last_updated": now - timedelta(hours=i),
            }
            for i in range(125)
        ]
        disservin_runs = [
            {
                "_id": f"disservin-{i}",
                "args": {"username": "Disservin", "info": ""},
                "last_updated": now - timedelta(hours=i, minutes=30),
            }
            for i in range(200)
        ]
        rundb = _PriorityFinishedRunsDbStub(
            runs_by_username={"vince": vince_runs, "Disservin": disservin_runs},
        )
        # Page 13 → skip=300, merge_window=325. 2*325=650 > 600 → fallback.
        request = _FinishedRunsRequestStub(
            rundb,
            _FinishedUsersStub([["vince", "Disservin"]]),
            params={"mode": "search", "user": "vin", "page": "13"},
            authenticated_userid="AuthUser",
        )

        result = get_paginated_finished_runs(request, search_mode=True)

        usernames_on_page = [run["args"]["username"] for run in result["finished_runs"]]
        # All vince runs (125 total) must appear before any Disservin runs.
        # Page 13 (rows 300-324) should be entirely Disservin.
        self.assertTrue(
            all(u == "Disservin" for u in usernames_on_page),
            f"Expected all Disservin on page 13 but got: {usernames_on_page}",
        )
        self.assertEqual(result["num_finished_runs"], 325)


if __name__ == "__main__":
    unittest.main()
