"""Test shared browser-readable UI cookie helpers."""

import unittest
from types import SimpleNamespace

from fishtest.http.ui_cookies import (
    append_ui_cookie,
    build_ui_cookie_header,
    read_cookie_bool,
    read_cookie_text,
    read_cookie_toggle_state,
)


class UiCookieHelperTests(unittest.TestCase):
    def test_build_ui_cookie_header_uses_shared_attrs_and_encoding(self):
        header = build_ui_cookie_header(
            "machines_q",
            "linux worker/1",
            max_age_seconds=10,
        )

        self.assertEqual(
            header,
            "machines_q=linux%20worker%2F1; path=/; max-age=10; SameSite=Lax",
        )

    def test_append_ui_cookie_preserves_duplicate_set_cookie_headers(self):
        request = SimpleNamespace(cookies={}, response_headerlist=[])

        append_ui_cookie(request, "theme", "dark", max_age_seconds=10)
        append_ui_cookie(request, "theme", "light", max_age_seconds=10)

        self.assertEqual(len(request.response_headerlist), 2)
        self.assertEqual(request.response_headerlist[0][0], "Set-Cookie")
        self.assertEqual(request.response_headerlist[1][0], "Set-Cookie")
        self.assertIn("theme=dark", request.response_headerlist[0][1])
        self.assertIn("theme=light", request.response_headerlist[1][1])

    def test_read_cookie_text_decodes_percent_escaped_values(self):
        self.assertEqual(
            read_cookie_text({"machines_q": "linux%20worker%2F1"}, "machines_q"),
            "linux worker/1",
        )

    def test_read_cookie_bool_uses_truthy_values_and_default(self):
        self.assertTrue(read_cookie_bool({"master_only": "yes"}, "master_only"))
        self.assertFalse(read_cookie_bool({"master_only": "off"}, "master_only"))
        self.assertTrue(read_cookie_bool({}, "master_only", default=True))

    def test_read_cookie_toggle_state_only_accepts_show_or_hide(self):
        self.assertEqual(
            read_cookie_toggle_state({"tasks_state": "Hide"}, "tasks_state"),
            "Hide",
        )
        self.assertEqual(
            read_cookie_toggle_state({"tasks_state": "hidden"}, "tasks_state"),
            "Show",
        )
