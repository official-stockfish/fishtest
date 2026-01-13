import unittest

from fastapi.responses import RedirectResponse

from fishtest.views import actions as actions_view


class _ActionDbStub:
    def __init__(self, return_count=0):
        self.last_kwargs = None
        self.return_count = return_count

    def get_actions(self, *args, **kwargs):
        self.last_kwargs = kwargs
        return [], self.return_count


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


class ActionsViewMaxActionsHttpTest(unittest.TestCase):
    def _last_kwargs(self, request):
        self.assertIsNotNone(request.actiondb.last_kwargs)
        assert request.actiondb.last_kwargs is not None
        return request.actiondb.last_kwargs

    def test_prev_link_preserves_max_actions_authenticated(self):
        request = _GlueRequestStub(
            params={"page": "20000", "max_actions": "500000"},
            authenticated_userid="JoeUser",
            return_count=500000,
        )
        result = actions_view(request)
        prev = result["pages"][0]
        self.assertEqual(prev["idx"], "Prev")
        self.assertIn("page=19999", prev["url"])
        self.assertIn("max_actions=500000", prev["url"])

    def test_prev_link_preserves_max_actions_anonymous_clamped(self):
        request = _GlueRequestStub(
            params={"page": "2", "max_actions": "999999"},
            authenticated_userid=None,
            return_count=5000,
        )
        result = actions_view(request)
        prev = result["pages"][0]
        self.assertEqual(prev["idx"], "Prev")
        self.assertIn("page=1", prev["url"])
        self.assertIn("max_actions=5000", prev["url"])

    def test_pagination_includes_last_page_link(self):
        request = _GlueRequestStub(
            params={"page": "2", "max_actions": "500000"},
            authenticated_userid="JoeUser",
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
            authenticated_userid="JoeUser",
            return_count=50000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, RedirectResponse)
        location = response.headers.get("location", "")
        self.assertIn("page=2000", location)
        self.assertIn("max_actions=50000", location)

    def test_out_of_range_page_redirects_to_last_page_anonymous_clamped(self):
        request = _GlueRequestStub(
            params={"page": "999999", "max_actions": "999999"},
            authenticated_userid=None,
            return_count=5000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, RedirectResponse)
        location = response.headers.get("location", "")
        self.assertIn("page=200", location)
        self.assertIn("max_actions=5000", location)

    def test_anon_default_hard_cap(self):
        request = _GlueRequestStub(params={})
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_actions"], 5000)

    def test_anon_clamps_user_max_actions(self):
        request = _GlueRequestStub(params={"max_actions": "999999"})
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_actions"], 5000)

    def test_authenticated_default_soft_cap_unfiltered(self):
        request = _GlueRequestStub(params={}, authenticated_userid="JoeUser")
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_actions"], 50000)

    def test_authenticated_allows_override_upward(self):
        request = _GlueRequestStub(
            params={"max_actions": "200000"},
            authenticated_userid="JoeUser",
        )
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertEqual(last_kwargs["max_actions"], 200000)

    def test_authenticated_filtered_no_default_cap(self):
        request = _GlueRequestStub(
            params={"user": "someone"},
            authenticated_userid="JoeUser",
        )
        actions_view(request)
        last_kwargs = self._last_kwargs(request)
        self.assertIsNone(last_kwargs["max_actions"])


if __name__ == "__main__":
    unittest.main()
