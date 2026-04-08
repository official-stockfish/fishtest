"""Test `/actions` view helper contracts."""

import unittest
from datetime import UTC, datetime
from html import unescape

import test_support
from fastapi.responses import RedirectResponse

from fishtest.http.settings import HTMX_INPUT_CHANGED_DELAY_MS
from fishtest.views import actions as actions_view


class _ActionDbStub:
    def __init__(self, return_count=0):
        self.last_kwargs = None
        self.return_count = return_count

    def get_actions(self, *args, **kwargs):
        self.last_kwargs = kwargs
        return [], self.return_count


class _CachedActionUsernamesStub:
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


class _RefreshingActionDbStub(_ActionDbStub):
    def __init__(self, *, usernames_versions, return_count=0):
        super().__init__(return_count=return_count)
        self.get_action_usernames = _CachedActionUsernamesStub(usernames_versions)


class _PriorityActionDbStub:
    def __init__(self, *, usernames, actions_by_username):
        self.get_action_usernames = _CachedActionUsernamesStub([usernames])
        self._actions_by_username = actions_by_username

    def get_actions(self, *args, **kwargs):
        username = kwargs.get("username")
        usernames = kwargs.get("usernames")
        action = kwargs.get("action")
        limit = kwargs.get("limit", 0)
        skip = kwargs.get("skip", 0)

        def _filtered_rows(rows):
            filtered_rows = list(rows)
            if action:
                filtered_rows = [
                    row for row in filtered_rows if row.get("action") == action
                ]
            return filtered_rows

        if username is not None:
            rows = _filtered_rows(self._actions_by_username.get(username, []))
            total = len(rows)
            return rows[skip : skip + limit], total

        if usernames is not None:
            rows = []
            for matched_username in usernames:
                rows.extend(
                    _filtered_rows(self._actions_by_username.get(matched_username, []))
                )
            rows.sort(
                key=lambda row: (
                    float(row.get("time") or 0),
                    str(row.get("_id") or ""),
                ),
                reverse=True,
            )
            total = len(rows)
            return rows[skip : skip + limit], total

        return [], 0


class _FakeStarletteRequest:
    def __init__(self, query_params):
        self.query_params = query_params


class _GlueRequestStub:
    def __init__(
        self,
        *,
        params=None,
        authenticated_userid=None,
        return_count=0,
        host_url="http://localhost",
        path="/actions",
        users=None,
    ):
        self.params = params or {}
        self._request = _FakeStarletteRequest(query_params=dict(self.params))
        self.actiondb = _ActionDbStub(return_count=return_count)
        self._authenticated_userid = authenticated_userid
        self.host_url = host_url
        self.path = path
        self.userdb = _FakeUserDb(users or [{"username": "anonymous"}])

    @property
    def authenticated_userid(self):
        return self._authenticated_userid

    @property
    def path_url(self):
        return f"{self.host_url}{self.path}"

    def has_permission(self, permission):
        if permission != "approve_run":
            return False
        return self._authenticated_userid is not None


class _FakeUserDb:
    def __init__(self, users):
        self._users = users

    def get_users(self):
        return list(self._users)


class TestActionsViewMaxCount(unittest.TestCase):
    def _last_kwargs(self, request):
        self.assertIsNotNone(request.actiondb.last_kwargs)
        assert request.actiondb.last_kwargs is not None
        return request.actiondb.last_kwargs

    def test_prev_link_preserves_max_count_authenticated(self):
        request = _GlueRequestStub(
            params={"page": "20000", "max_count": "500000"},
            authenticated_userid="TestActionsViewer",
            return_count=500000,
        )
        result = actions_view(request)
        prev = result["pages"][0]
        self.assertEqual(prev["idx"], "Prev")
        self.assertIn("page=19999", prev["url"])
        self.assertIn("max_count=500000", prev["url"])

    def test_prev_link_preserves_max_count_anonymous_clamped(self):
        request = _GlueRequestStub(
            params={"page": "2", "max_count": "999999"},
            authenticated_userid=None,
            return_count=5000,
        )
        result = actions_view(request)
        prev = result["pages"][0]
        self.assertEqual(prev["idx"], "Prev")
        self.assertIn("page=1", prev["url"])
        self.assertIn("max_count=5000", prev["url"])

    def test_pagination_includes_last_page_link(self):
        request = _GlueRequestStub(
            params={"page": "2", "max_count": "500000"},
            authenticated_userid="TestActionsViewer",
            return_count=500000,
        )
        result = actions_view(request)
        last_page = max(p["idx"] for p in result["pages"] if isinstance(p["idx"], int))
        self.assertEqual(last_page, 20000)
        self.assertIn(
            "page=20000",
            " ".join(p["url"] for p in result["pages"] if p.get("url")),
        )

    def test_out_of_range_page_redirects_to_last_page_authenticated(self):
        request = _GlueRequestStub(
            params={"page": "999999"},
            authenticated_userid="TestActionsViewer",
            return_count=50000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, RedirectResponse)
        location = response.headers.get("location", "")
        self.assertIn("page=2000", location)
        self.assertIn("max_count=50000", location)

    def test_out_of_range_page_redirects_to_last_page_anonymous_clamped(self):
        request = _GlueRequestStub(
            params={"page": "999999", "max_count": "999999"},
            authenticated_userid=None,
            return_count=5000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, RedirectResponse)
        location = response.headers.get("location", "")
        self.assertIn("page=200", location)
        self.assertIn("max_count=5000", location)

    def test_anon_default_hard_cap(self):
        request = _GlueRequestStub(params={})
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 5000)

    def test_anon_clamps_user_max_count(self):
        request = _GlueRequestStub(params={"max_count": "999999"})
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 5000)

    def test_authenticated_default_soft_cap_unfiltered(self):
        request = _GlueRequestStub(
            params={},
            authenticated_userid="TestActionsViewer",
        )
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 50000)

    def test_authenticated_allows_override_upward(self):
        request = _GlueRequestStub(
            params={"max_count": "200000"},
            authenticated_userid="TestActionsViewer",
        )
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 200000)

    def test_authenticated_filtered_defaults_to_soft_cap(self):
        request = _GlueRequestStub(
            params={"user": "someone"},
            authenticated_userid="TestActionsViewer",
        )
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 50000)

    def test_authenticated_huge_max_count_is_clamped_to_mongo_int64(self):
        request = _GlueRequestStub(
            params={"max_count": "500000000000000000000000"},
            authenticated_userid="TestActionsViewer",
        )

        actions_view(request)

        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_count"], 2**63 - 1)

    def test_actions_username_filter_refreshes_cached_usernames_on_miss(self):
        request = _GlueRequestStub(
            params={"user": "TestFreshActionUser"},
            authenticated_userid="TestActionsViewer",
            return_count=1,
        )
        request.actiondb = _RefreshingActionDbStub(
            usernames_versions=[["TestOlderActionUser"], ["TestFreshActionUser"]],
            return_count=1,
        )

        actions_view(request)

        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["usernames"], ["TestFreshActionUser"])
        self.assertEqual(request.actiondb.get_action_usernames.cache_clear_calls, 1)


class TestActionsViews(unittest.TestCase):
    def setUp(self):
        self.rundb = test_support.get_rundb()
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )
        self.run_id = "64e74776a170cb1f26fa3930"

    def tearDown(self):
        self.rundb.actiondb.actions.delete_many(
            {
                "$or": [
                    {
                        "username": {
                            "$in": [
                                "TestActionsRouteUser",
                                "TestOtherActionUser",
                                "TestSortActionUser",
                            ]
                        }
                    },
                    {"run_id": self.run_id},
                ]
            }
        )

    def test_actions_form_uses_htmx_triggered_search_and_preserves_url_state(self):
        response = self.client.get(
            f"/actions?run_id={self.run_id}&sort=event&order=asc"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="actions-filters"', response.text)
        self.assertIn('id="actions-page"', response.text)
        expected_trigger = (
            'hx-trigger="submit, input changed delay:'
            f"{HTMX_INPUT_CHANGED_DELAY_MS}ms from:#actions_user"
        )
        self.assertIn(expected_trigger, response.text)
        self.assertIn('type="search"', response.text)
        self.assertIn('aria-label="Show free text search help"', response.text)
        self.assertIn('data-bs-target="#autoselect-modal"', response.text)
        self.assertIn("MongoDB <i>$text</i> search", response.text)
        self.assertIn('target="_blank"', response.text)
        self.assertIn('rel="noopener noreferrer"', response.text)
        self.assertNotIn("<datalist", response.text)
        self.assertNotIn('role="combobox"', response.text)
        self.assertNotIn("actions-user-suggestions", response.text)
        self.assertIn(
            f'<input type="hidden" name="run_id" value="{self.run_id}">',
            response.text,
        )
        self.assertIn('name="max_count" value="5000"', response.text)
        self.assertIn('name="sort" value="event"', response.text)
        self.assertIn('name="order" value="asc"', response.text)

    def test_actions_hx_fragment_renders_summary_and_accessible_table(self):
        self.rundb.actiondb.insert_action(
            action="new_run",
            username="TestActionsRouteUser",
            run_id=self.run_id,
            run="h23-actions-run-abcdef0",
            message="H23 route contract hit",
        )
        self.rundb.actiondb.insert_action(
            action="upload_nn",
            username="TestOtherActionUser",
            nn="nn-123456789abc.nnue",
        )

        response = self.client.get(
            f"/actions?user=TestActionsRouteUser&run_id={self.run_id}",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<!doctype html>", response.text.lower())
        self.assertIn('id="actions_table"', response.text)
        self.assertIn('<caption class="visually-hidden">', response.text)
        self.assertIn('class="sort-indicator"', response.text)
        self.assertIn(
            "Showing 1 of 1 matching action on page 1 of 1.",
            response.text,
        )
        self.assertIn(f"/tests/view/{self.run_id}", response.text)
        self.assertIn("H23 route contract hit", response.text)
        self.assertNotIn("nn-123456789abc.nnue", response.text)

    def test_actions_worker_log_renders_task_target_link(self):
        self.rundb.actiondb.insert_action(
            action="worker_log",
            username="TestActionsRouteUser",
            worker="h23-worker-16cores-zz-1a2b",
            run_id=self.run_id,
            run="h23-actions-run-abcdef0",
            task_id=7,
            message="Bestmove does not match beginning of last PV",
        )

        response = self.client.get(
            f"/actions?run_id={self.run_id}",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("worker_log", response.text)
        self.assertIn("/workers/h23-worker-16cores", response.text)
        self.assertIn("h23-worker-16cores-zz-1a2b", response.text)
        self.assertIn(
            f"/tests/view/{self.run_id}?show_task=7",
            response.text,
        )
        self.assertIn("h23-actions-run-abcdef0/7", response.text)

    def test_actions_form_offers_worker_log_filter_and_filters_results(self):
        self.rundb.actiondb.insert_action(
            action="worker_log",
            username="TestActionsRouteUser",
            worker="h23-worker-16cores-zz-1a2b",
            run_id=self.run_id,
            run="h23-actions-run-abcdef0",
            task_id=7,
            message="Bestmove warning",
        )
        self.rundb.actiondb.insert_action(
            action="log_message",
            username="TestActionsRouteUser",
            message="Generic server log",
        )

        page_response = self.client.get(
            f"/actions?action=worker_log&run_id={self.run_id}"
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('option value="worker_log" selected', page_response.text)
        self.assertIn("Worker Logs", page_response.text)

        fragment_response = self.client.get(
            f"/actions?action=worker_log&run_id={self.run_id}",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(fragment_response.status_code, 200)
        self.assertIn("Bestmove warning", fragment_response.text)
        self.assertNotIn("Generic server log", fragment_response.text)

    def test_actions_full_page_renders_query_preserving_open_graph_preview(self):
        event_time = datetime(2026, 4, 8, 19, 5, 44, tzinfo=UTC).timestamp()
        self.rundb.actiondb.actions.insert_one(
            {
                "action": "failed_task",
                "username": "TestActionsRouteUser",
                "worker": "h23-worker-16cores-zz-1a2b",
                "run_id": self.run_id,
                "run": "h23-actions-run-abcdef0",
                "task_id": 7,
                "message": "clang++ link failed after profile-build",
                "time": event_time,
            },
        )
        self.rundb.actiondb.actions.insert_one(
            {
                "action": "failed_task",
                "username": "TestActionsRouteUser",
                "worker": "h23-worker-16cores-zz-1a2b",
                "run_id": self.run_id,
                "run": "h23-actions-run-abcdef0",
                "task_id": 8,
                "message": "second matching action",
                "time": event_time - 60,
            },
        )

        response = self.client.get(
            f"/actions?user=TestActionsRouteUser&action=failed_task&run_id={self.run_id}&max_count=2"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            test_support.extract_meta_content(
                response.text,
                property_name="og:title",
            ),
            "failed_task on h23-actions-run-abcdef0/7 | Stockfish Testing",
        )
        self.assertEqual(
            unescape(
                test_support.extract_meta_content(
                    response.text,
                    property_name="og:url",
                ),
            ),
            "http://testserver/actions?user=TestActionsRouteUser&action=failed_task"
            f"&run_id={self.run_id}&max_count=2",
        )

        og_description = test_support.extract_meta_content(
            response.text,
            property_name="og:description",
        )
        self.assertNotIn("Most recent of", og_description)
        self.assertIn("1 of 2 matching actions.", og_description)
        self.assertIn("Time: 26-04-08 19:05:44", og_description)
        self.assertIn("Event: failed_task", og_description)
        self.assertIn("Source: h23-worker-16cores-zz-1a2b", og_description)
        self.assertIn("Target: h23-actions-run-abcdef0/7", og_description)
        self.assertIn(
            "Comment: clang++ link failed after profile-build", og_description
        )

    def test_actions_username_filter_matches_partial_substrings(self):
        self.rundb.actiondb.insert_action(
            action="new_run",
            username="TestActionsRouteUser",
            run_id=self.run_id,
            run="h23-actions-run-abcdef0",
            message="Partial username hit",
        )
        self.rundb.actiondb.insert_action(
            action="upload_nn",
            username="TestOtherActionUser",
            nn="nn-123456789abc.nnue",
        )

        response = self.client.get(
            "/actions?user=tionsRoute",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Partial username hit", response.text)
        self.assertNotIn("nn-123456789abc.nnue", response.text)

    def test_actions_username_filter_ranks_prefix_matches_before_inner_substrings(self):
        now = datetime.now(UTC).timestamp()
        request = _GlueRequestStub(
            params={"user": "vin"},
            authenticated_userid="TestActionsViewer",
        )
        request.actiondb = _PriorityActionDbStub(
            usernames=["mauvin-agent", "vin-prefix-agent"],
            actions_by_username={
                "mauvin-agent": [
                    {
                        "_id": "mauvin-agent-1",
                        "action": "upload_nn",
                        "username": "mauvin-agent",
                        "nn": "nn-mauvin-agent.nnue",
                        "message": "inner substring match",
                        "time": now,
                    }
                ],
                "vin-prefix-agent": [
                    {
                        "_id": "vin-prefix-agent-1",
                        "action": "new_run",
                        "username": "vin-prefix-agent",
                        "run_id": "64e74776a170cb1f26fa3930",
                        "run": "ranked-prefix-run",
                        "message": "prefix match",
                        "time": now - 60,
                    }
                ],
            },
        )

        result = actions_view(request)

        self.assertEqual(
            [row["agent_name"] for row in result["actions"]],
            ["vin-prefix-agent", "mauvin-agent"],
        )
        self.assertEqual(result["visible_actions"], 2)
        self.assertEqual(result["num_actions"], 2)

    def test_actions_username_filter_keeps_substring_expansion_for_exact_term(self):
        now = datetime.now(UTC).timestamp()
        request = _GlueRequestStub(
            params={"user": "mockuser"},
            authenticated_userid="TestActionsViewer",
        )
        request.actiondb = _PriorityActionDbStub(
            usernames=["mockuser", "mockuser-alt"],
            actions_by_username={
                "mockuser": [
                    {
                        "_id": "mockuser-1",
                        "action": "new_run",
                        "username": "mockuser",
                        "run_id": "64e74776a170cb1f26fa3930",
                        "run": "mockuser-exact-run",
                        "message": "exact username still expands",
                        "time": now,
                    }
                ],
                "mockuser-alt": [
                    {
                        "_id": "mockuser-alt-1",
                        "action": "upload_nn",
                        "username": "mockuser-alt",
                        "nn": "nn-mockuser-alt.nnue",
                        "message": "substring expansion stays enabled",
                        "time": now - 60,
                    }
                ],
            },
        )

        result = actions_view(request)

        self.assertEqual(
            [row["agent_name"] for row in result["actions"]],
            ["mockuser", "mockuser-alt"],
        )
        self.assertEqual(result["visible_actions"], 2)
        self.assertEqual(result["num_actions"], 2)

    def test_actions_ranked_username_merge_preserves_action_filter(self):
        now = datetime.now(UTC).timestamp()
        request = _GlueRequestStub(
            params={"user": "mockuser", "action": "upload_nn"},
            authenticated_userid="TestActionsViewer",
        )
        request.actiondb = _PriorityActionDbStub(
            usernames=["mockuser", "mockuser-alt"],
            actions_by_username={
                "mockuser": [
                    {
                        "_id": "mockuser-1",
                        "action": "new_run",
                        "username": "mockuser",
                        "run_id": "64e74776a170cb1f26fa3930",
                        "run": "mockuser-new-run",
                        "message": "wrong action for exact user",
                        "time": now,
                    }
                ],
                "mockuser-alt": [
                    {
                        "_id": "mockuser-alt-1",
                        "action": "upload_nn",
                        "username": "mockuser-alt",
                        "nn": "nn-mockuser-alt.nnue",
                        "message": "matching action survives",
                        "time": now - 60,
                    }
                ],
            },
        )

        result = actions_view(request)

        self.assertEqual([row["event"] for row in result["actions"]], ["upload_nn"])
        self.assertEqual(
            [row["agent_name"] for row in result["actions"]],
            ["mockuser-alt"],
        )
        self.assertEqual(result["visible_actions"], 1)
        self.assertEqual(result["num_actions"], 1)

    def test_actions_event_sort_applies_to_the_full_capped_result_set(self):
        actions = []
        for index in range(26):
            action_name = "new_run" if index == 25 else "upload_nn"
            actions.append(
                {
                    "action": action_name,
                    "username": "TestSortActionUser",
                    "time": float(2000 - index),
                    "message": f"message-{index:02d}",
                }
            )

        self.rundb.actiondb.actions.insert_many(actions)

        response = self.client.get(
            "/actions?user=TestSortActionUser&sort=event&order=asc",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sorted by Event ascending", response.text)
        self.assertIn("new_run", response.text)
        self.assertLess(
            response.text.index("new_run"),
            response.text.index("upload_nn"),
        )

    def test_actions_empty_state_uses_real_column_span(self):
        response = self.client.get(
            "/actions?user=MissingActionsUser",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('colspan="5">No actions available</td>', response.text)


if __name__ == "__main__":
    unittest.main()
