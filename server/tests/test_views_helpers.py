"""Test views-layer helper contracts.

Cover parameter parsing, pagination, query-string building, HTMX request
detection, username matching, and heap-based merge behavior.
"""

import unittest
from datetime import UTC, datetime

from fishtest.util import tests_repo
from fishtest.views_helpers import (
    _build_query_string,
    _clamp_page_index,
    _float_param,
    _is_hx_request,
    _is_truthy_param,
    _merge_rows_by_username_priority,
    _nested_row_value,
    _normalize_sort_order,
    _normalize_view_mode,
    _page_index_from_params,
    _positive_int_param,
    _ranked_multi_username_merge,
    _sort_matched_usernames,
    _username_match_sort_key,
    _username_priority_map,
    pagination,
)


class IsTruthyParamTests(unittest.TestCase):
    def test_truthy_values(self):
        for value in ("1", "true", "on", "yes"):
            with self.subTest(value=value):
                self.assertTrue(_is_truthy_param(value))

    def test_truthy_case_insensitive(self):
        for value in ("True", "TRUE", "On", "YES", "Yes"):
            with self.subTest(value=value):
                self.assertTrue(_is_truthy_param(value))

    def test_truthy_with_whitespace(self):
        self.assertTrue(_is_truthy_param("  true  "))
        self.assertTrue(_is_truthy_param(" 1 "))

    def test_falsy_values(self):
        for value in ("0", "false", "off", "no", "", "maybe", "2"):
            with self.subTest(value=value):
                self.assertFalse(_is_truthy_param(value))

    def test_non_string_input(self):
        self.assertTrue(_is_truthy_param(1))
        self.assertFalse(_is_truthy_param(0))
        self.assertFalse(_is_truthy_param(None))


class PageIndexFromParamsTests(unittest.TestCase):
    def test_valid_page(self):
        self.assertEqual(_page_index_from_params({"page": "3"}), 2)

    def test_page_one(self):
        self.assertEqual(_page_index_from_params({"page": "1"}), 0)

    def test_missing_page(self):
        self.assertEqual(_page_index_from_params({}), 0)

    def test_non_numeric(self):
        self.assertEqual(_page_index_from_params({"page": "abc"}), 0)

    def test_zero_page(self):
        # "0".isdigit() is True, int("0") - 1 = -1, max(0, -1) = 0
        self.assertEqual(_page_index_from_params({"page": "0"}), 0)

    def test_custom_key(self):
        self.assertEqual(_page_index_from_params({"p": "5"}, key="p"), 4)

    def test_empty_string(self):
        self.assertEqual(_page_index_from_params({"page": ""}), 0)

    def test_negative_string(self):
        # "-1" is not digit, returns 0
        self.assertEqual(_page_index_from_params({"page": "-1"}), 0)


class NormalizeSortOrderTests(unittest.TestCase):
    def test_asc(self):
        self.assertEqual(
            _normalize_sort_order("asc", default_reverse=True), ("asc", False)
        )

    def test_desc(self):
        self.assertEqual(
            _normalize_sort_order("desc", default_reverse=False), ("desc", True)
        )

    def test_case_insensitive(self):
        self.assertEqual(
            _normalize_sort_order("ASC", default_reverse=True), ("asc", False)
        )
        self.assertEqual(
            _normalize_sort_order("Desc", default_reverse=False), ("desc", True)
        )

    def test_with_whitespace(self):
        self.assertEqual(
            _normalize_sort_order("  asc  ", default_reverse=True), ("asc", False)
        )

    def test_invalid_default_reverse_true(self):
        self.assertEqual(
            _normalize_sort_order("invalid", default_reverse=True), ("desc", True)
        )

    def test_invalid_default_reverse_false(self):
        self.assertEqual(
            _normalize_sort_order("bad", default_reverse=False), ("asc", False)
        )

    def test_empty_string(self):
        self.assertEqual(
            _normalize_sort_order("", default_reverse=True), ("desc", True)
        )


class NormalizeViewModeTests(unittest.TestCase):
    def test_paged(self):
        self.assertEqual(_normalize_view_mode("paged"), "paged")

    def test_all(self):
        self.assertEqual(_normalize_view_mode("all"), "all")

    def test_case_insensitive(self):
        self.assertEqual(_normalize_view_mode("Paged"), "paged")
        self.assertEqual(_normalize_view_mode("ALL"), "all")

    def test_with_whitespace(self):
        self.assertEqual(_normalize_view_mode("  all  "), "all")

    def test_invalid_defaults_to_paged(self):
        self.assertEqual(_normalize_view_mode("invalid"), "paged")
        self.assertEqual(_normalize_view_mode(""), "paged")


class ClampPageIndexTests(unittest.TestCase):
    def test_within_bounds(self):
        self.assertEqual(_clamp_page_index(0, total_count=100, page_size=25), 0)

    def test_at_last_page(self):
        self.assertEqual(_clamp_page_index(3, total_count=100, page_size=25), 3)

    def test_beyond_last_page(self):
        self.assertEqual(_clamp_page_index(10, total_count=100, page_size=25), 3)

    def test_zero_count(self):
        self.assertEqual(_clamp_page_index(5, total_count=0, page_size=25), 0)

    def test_negative_count(self):
        self.assertEqual(_clamp_page_index(5, total_count=-1, page_size=25), 0)

    def test_single_item(self):
        self.assertEqual(_clamp_page_index(0, total_count=1, page_size=25), 0)
        self.assertEqual(_clamp_page_index(1, total_count=1, page_size=25), 0)

    def test_exact_page_boundary(self):
        # 50 items, page_size 25 -> last page index is 1
        self.assertEqual(_clamp_page_index(1, total_count=50, page_size=25), 1)
        self.assertEqual(_clamp_page_index(2, total_count=50, page_size=25), 1)


class BuildQueryStringTests(unittest.TestCase):
    def test_basic_pairs(self):
        result = _build_query_string([("a", "1"), ("b", "2")])
        self.assertEqual(result, "&a=1&b=2")

    def test_filters_none_values(self):
        result = _build_query_string([("a", "1"), ("b", None), ("c", "3")])
        self.assertEqual(result, "&a=1&c=3")

    def test_all_none(self):
        result = _build_query_string([("a", None), ("b", None)])
        self.assertEqual(result, "")

    def test_empty_pairs(self):
        result = _build_query_string([])
        self.assertEqual(result, "")

    def test_custom_leading(self):
        result = _build_query_string([("a", "1")], leading="?")
        self.assertEqual(result, "?a=1")

    def test_value_coercion_to_string(self):
        result = _build_query_string([("page", 3)])
        self.assertEqual(result, "&page=3")

    def test_url_encoding(self):
        result = _build_query_string([("q", "hello world")])
        self.assertIn("hello+world", result)


class PositiveIntParamTests(unittest.TestCase):
    def test_valid_positive(self):
        self.assertEqual(_positive_int_param("5"), 5)

    def test_valid_with_max(self):
        self.assertEqual(_positive_int_param("100", max_value=50), 50)

    def test_within_max(self):
        self.assertEqual(_positive_int_param("30", max_value=50), 30)

    def test_zero_returns_none(self):
        self.assertIsNone(_positive_int_param("0"))

    def test_negative_returns_none(self):
        self.assertIsNone(_positive_int_param("-5"))

    def test_none_input(self):
        self.assertIsNone(_positive_int_param(None))

    def test_empty_string(self):
        self.assertIsNone(_positive_int_param(""))

    def test_non_numeric(self):
        self.assertIsNone(_positive_int_param("abc"))

    def test_float_string(self):
        self.assertIsNone(_positive_int_param("3.5"))


class FloatParamTests(unittest.TestCase):
    def test_valid_float(self):
        self.assertEqual(_float_param("3.14"), 3.14)

    def test_valid_integer_string(self):
        self.assertEqual(_float_param("5"), 5.0)

    def test_none_input(self):
        self.assertIsNone(_float_param(None))

    def test_empty_string(self):
        self.assertIsNone(_float_param(""))

    def test_non_numeric(self):
        self.assertIsNone(_float_param("abc"))

    def test_negative_float(self):
        self.assertEqual(_float_param("-2.5"), -2.5)


class IsHxRequestTests(unittest.TestCase):
    def test_htmx_request(self):
        request = type("R", (), {"headers": {"HX-Request": "true"}})()
        self.assertTrue(_is_hx_request(request))

    def test_non_htmx_request(self):
        request = type("R", (), {"headers": {}})()
        self.assertFalse(_is_hx_request(request))

    def test_htmx_with_navigate_mode(self):
        request = type(
            "R", (), {"headers": {"HX-Request": "true", "Sec-Fetch-Mode": "navigate"}}
        )()
        self.assertFalse(_is_hx_request(request))

    def test_no_headers(self):
        request = type("R", (), {"headers": None})()
        self.assertFalse(_is_hx_request(request))

    def test_htmx_case_insensitive(self):
        request = type("R", (), {"headers": {"HX-Request": "True"}})()
        self.assertTrue(_is_hx_request(request))

    def test_htmx_with_cors_mode(self):
        request = type(
            "R", (), {"headers": {"HX-Request": "true", "Sec-Fetch-Mode": "cors"}}
        )()
        self.assertTrue(_is_hx_request(request))


class TestsRepoHelperTests(unittest.TestCase):
    def test_tests_repo_returns_canonical_url_for_trailing_slash(self):
        run = {
            "args": {"tests_repo": "https://github.com/official-stockfish/Stockfish/"}
        }

        self.assertEqual(
            tests_repo(run),
            "https://github.com/official-stockfish/Stockfish",
        )

    def test_tests_repo_falls_back_for_empty_legacy_value(self):
        run = {"args": {"tests_repo": ""}}

        self.assertEqual(
            tests_repo(run),
            "https://github.com/official-stockfish/Stockfish",
        )


class PaginationTests(unittest.TestCase):
    def test_single_page(self):
        pages = pagination(0, 10, 25, "")
        # Should have Prev, page 1, Next
        self.assertEqual(pages[0]["idx"], "Prev")
        self.assertEqual(pages[0]["state"], "disabled")
        self.assertEqual(pages[-1]["idx"], "Next")
        self.assertEqual(pages[-1]["state"], "disabled")

    def test_multi_page_first(self):
        pages = pagination(0, 100, 25, "")
        self.assertEqual(pages[0]["state"], "disabled")  # Prev disabled
        self.assertNotEqual(pages[-1]["state"], "disabled")  # Next enabled

    def test_multi_page_last(self):
        pages = pagination(3, 100, 25, "")
        self.assertNotEqual(pages[0]["state"], "disabled")  # Prev enabled
        self.assertEqual(pages[-1]["state"], "disabled")  # Next disabled

    def test_zero_items(self):
        pages = pagination(0, 0, 25, "")
        self.assertEqual(pages[0]["idx"], "Prev")
        self.assertEqual(pages[-1]["idx"], "Next")
        # Both disabled at zero
        self.assertEqual(pages[0]["state"], "disabled")
        self.assertEqual(pages[-1]["state"], "disabled")

    def test_query_params_in_urls(self):
        pages = pagination(0, 100, 25, "&sort=asc")
        for page in pages:
            if page["url"]:
                self.assertIn("sort=asc", page["url"])

    def test_active_page_state(self):
        pages = pagination(2, 100, 25, "")
        active_pages = [p for p in pages if p.get("state") == "active"]
        self.assertEqual(len(active_pages), 1)
        self.assertEqual(active_pages[0]["idx"], 3)  # page 3 (1-based)


class UsernameMatchSortKeyTests(unittest.TestCase):
    def test_exact_prefix(self):
        key = _username_match_sort_key("john", "john_doe")
        self.assertEqual(key[0], 0)  # starts_with = 0

    def test_contains_not_prefix(self):
        key = _username_match_sort_key("doe", "john_doe")
        self.assertEqual(key[0], 1)  # starts_with = 1

    def test_sorting_order(self):
        usernames = ["doe_john", "john_doe", "john", "ajohn"]
        sorted_list = sorted(
            usernames,
            key=lambda u: _username_match_sort_key("john", u),
        )
        # "john" (exact prefix, idx 0) first, then "john_doe" (prefix, idx 0),
        # then "ajohn" (contains, idx 1), then "doe_john" (contains, idx 4)
        self.assertEqual(sorted_list[0], "john")
        self.assertEqual(sorted_list[1], "john_doe")

    def test_case_insensitive(self):
        key1 = _username_match_sort_key("JOHN", "John")
        key2 = _username_match_sort_key("john", "john")
        self.assertEqual(key1[0], key2[0])


class SortMatchedUsernamesTests(unittest.TestCase):
    def test_prefix_first(self):
        result = _sort_matched_usernames(["xjohn", "john_doe", "john"], "john")
        self.assertEqual(result[0], "john")
        self.assertEqual(result[1], "john_doe")

    def test_empty_list(self):
        self.assertEqual(_sort_matched_usernames([], "query"), [])


class UsernamePriorityMapTests(unittest.TestCase):
    def test_basic(self):
        result = _username_priority_map(["alice", "bob", "charlie"])
        self.assertEqual(result, {"alice": 0, "bob": 1, "charlie": 2})

    def test_empty(self):
        self.assertEqual(_username_priority_map([]), {})


class NestedRowValueTests(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(_nested_row_value({"a": 1}, "a"), 1)

    def test_nested_key(self):
        self.assertEqual(_nested_row_value({"a": {"b": 2}}, "a.b"), 2)

    def test_missing_key(self):
        self.assertIsNone(_nested_row_value({"a": 1}, "b"))

    def test_missing_nested_key(self):
        self.assertIsNone(_nested_row_value({"a": {"b": 2}}, "a.c"))

    def test_default_value(self):
        self.assertEqual(_nested_row_value({"a": 1}, "b", default="N/A"), "N/A")

    def test_non_dict_intermediate(self):
        self.assertIsNone(_nested_row_value({"a": "string"}, "a.b"))


class MergeRowsByUsernamePriorityTests(unittest.TestCase):
    def _make_row(self, username, time_val, row_id):
        return {
            "args": {"username": username},
            "last_updated": datetime.fromtimestamp(time_val, UTC) if time_val else None,
            "_id": row_id,
        }

    def test_single_list(self):
        rows = [
            self._make_row("alice", 100, "a1"),
            self._make_row("alice", 90, "a2"),
        ]
        result = _merge_rows_by_username_priority(
            [rows],
            username_priority={"alice": 0},
            username_field="args.username",
            time_field="last_updated",
            id_field="_id",
            skip=0,
            limit=10,
        )
        self.assertEqual(len(result), 2)

    def test_two_lists_by_priority(self):
        alice_rows = [self._make_row("alice", 100, "a1")]
        bob_rows = [self._make_row("bob", 200, "b1")]
        result = _merge_rows_by_username_priority(
            [bob_rows, alice_rows],
            username_priority={"alice": 0, "bob": 1},
            username_field="args.username",
            time_field="last_updated",
            id_field="_id",
            skip=0,
            limit=10,
        )
        # Alice has higher priority (0 < 1)
        self.assertEqual(result[0]["_id"], "a1")
        self.assertEqual(result[1]["_id"], "b1")

    def test_skip(self):
        rows = [
            self._make_row("alice", 100, "a1"),
            self._make_row("alice", 90, "a2"),
            self._make_row("alice", 80, "a3"),
        ]
        result = _merge_rows_by_username_priority(
            [rows],
            username_priority={"alice": 0},
            username_field="args.username",
            time_field="last_updated",
            id_field="_id",
            skip=1,
            limit=1,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["_id"], "a2")

    def test_empty_lists(self):
        result = _merge_rows_by_username_priority(
            [[], []],
            username_priority={},
            username_field="args.username",
            time_field="last_updated",
            id_field="_id",
            skip=0,
            limit=10,
        )
        self.assertEqual(result, [])


class RankedMultiUsernameMergeTests(unittest.TestCase):
    def test_basic_merge(self):
        def fetch_fn(username, window, cap):
            data = {
                "alice": (
                    [
                        {
                            "_id": "a1",
                            "args": {"username": "alice"},
                            "last_updated": datetime(2026, 1, 2, tzinfo=UTC),
                        }
                    ],
                    1,
                ),
                "bob": (
                    [
                        {
                            "_id": "b1",
                            "args": {"username": "bob"},
                            "last_updated": datetime(2026, 1, 1, tzinfo=UTC),
                        }
                    ],
                    1,
                ),
            }
            return data.get(username, ([], 0))

        result = _ranked_multi_username_merge(
            usernames=["alice", "bob"],
            fetch_fn=fetch_fn,
            username_field="args.username",
            time_field="last_updated",
            skip=0,
            limit=10,
            max_count=None,
        )
        self.assertIsNotNone(result)
        rows, count = result
        self.assertEqual(count, 2)
        self.assertEqual(len(rows), 2)
        # alice first by priority
        self.assertEqual(rows[0]["_id"], "a1")

    def test_too_many_usernames_returns_none(self):
        # With many usernames and large window, should bail out (> 600)
        usernames = [f"user_{i}" for i in range(100)]
        result = _ranked_multi_username_merge(
            usernames=usernames,
            fetch_fn=lambda u, w, c: ([], 0),
            username_field="args.username",
            time_field="last_updated",
            skip=0,
            limit=25,
            max_count=None,
        )
        self.assertIsNone(result)

    def test_max_count_cap(self):
        call_log = []

        def fetch_fn(username, window, cap):
            call_log.append((username, cap))
            return (
                [
                    {
                        "_id": f"{username[0]}1",
                        "args": {"username": username},
                        "last_updated": datetime(2026, 1, 1, tzinfo=UTC),
                    }
                ],
                1,
            )

        result = _ranked_multi_username_merge(
            usernames=["alice", "bob"],
            fetch_fn=fetch_fn,
            username_field="args.username",
            time_field="last_updated",
            skip=0,
            limit=10,
            max_count=1,
        )
        self.assertIsNotNone(result)
        rows, count = result
        # max_count=1, so total capped at 1
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
