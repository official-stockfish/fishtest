import unittest

from fishtest.views import actions as actions_view
from pyramid import testing
from pyramid.httpexceptions import HTTPFound


class _ActionDbStub:
    def __init__(self, return_count=0):
        self.last_kwargs = None
        self.return_count = return_count

    def get_actions(self, *args, **kwargs):
        self.last_kwargs = kwargs
        return [], self.return_count


class ActionsViewMaxActionsTest(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def _make_request(
        self, params=None, authenticated_userid=None, return_count=0, path="/actions"
    ):
        self.config.set_security_policy(
            testing.DummySecurityPolicy(userid=authenticated_userid)
        )
        actiondb = _ActionDbStub(return_count=return_count)
        request = testing.DummyRequest(
            params=params or {}, actiondb=actiondb, path=path
        )
        return request, actiondb

    def test_prev_link_preserves_max_actions_authenticated(self):
        request, _actiondb = self._make_request(
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
        request, _actiondb = self._make_request(
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
        request, _actiondb = self._make_request(
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
        request, _actiondb = self._make_request(
            params={"page": "999999"},
            authenticated_userid="JoeUser",
            return_count=50000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, HTTPFound)
        self.assertIn("page=2000", response.location)
        self.assertIn("max_actions=50000", response.location)

    def test_out_of_range_page_redirects_to_last_page_anonymous_clamped(self):
        request, _actiondb = self._make_request(
            params={"page": "999999", "max_actions": "999999"},
            authenticated_userid=None,
            return_count=5000,
        )
        response = actions_view(request)
        self.assertIsInstance(response, HTTPFound)
        self.assertIn("page=200", response.location)
        self.assertIn("max_actions=5000", response.location)

    def test_anon_default_hard_cap(self):
        request, actiondb = self._make_request(params={})
        actions_view(request)
        self.assertEqual(actiondb.last_kwargs["max_actions"], 5000)

    def test_anon_clamps_user_max_actions(self):
        request, actiondb = self._make_request(params={"max_actions": "999999"})
        actions_view(request)
        self.assertEqual(actiondb.last_kwargs["max_actions"], 5000)

    def test_authenticated_default_soft_cap_unfiltered(self):
        request, actiondb = self._make_request(
            params={}, authenticated_userid="JoeUser"
        )
        actions_view(request)
        self.assertEqual(actiondb.last_kwargs["max_actions"], 50000)

    def test_authenticated_allows_override_upward(self):
        request, actiondb = self._make_request(
            params={"max_actions": "200000"}, authenticated_userid="JoeUser"
        )
        actions_view(request)
        self.assertEqual(actiondb.last_kwargs["max_actions"], 200000)

    def test_authenticated_filtered_no_default_cap(self):
        request, actiondb = self._make_request(
            params={"user": "someone"}, authenticated_userid="JoeUser"
        )
        actions_view(request)
        self.assertIsNone(actiondb.last_kwargs["max_actions"])


if __name__ == "__main__":
    unittest.main()
