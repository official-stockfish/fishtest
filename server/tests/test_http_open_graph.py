"""Test Open Graph metadata helpers."""

import unittest
from datetime import UTC, datetime

from fishtest.http.open_graph import (
    build_actions_open_graph,
    build_tests_view_open_graph,
    canonical_page_url,
    default_open_graph,
)
from fishtest.util import format_results


class OpenGraphTests(unittest.TestCase):
    def test_canonical_page_url_drops_query_and_fragment(self):
        self.assertEqual(
            canonical_page_url("https://example.org/tests/view/123?follow=1#tasks"),
            "https://example.org/tests/view/123",
        )

    def test_default_open_graph_uses_defaults_and_canonical_url(self):
        open_graph = default_open_graph(
            "https://example.org/tests/view/123?follow=1#tasks",
        )

        self.assertEqual(open_graph["site_name"], "Stockfish Testing Framework")
        self.assertEqual(open_graph["type"], "website")
        self.assertEqual(open_graph["title"], "Stockfish Testing Framework")
        self.assertEqual(
            open_graph["description"],
            "Distributed testing framework for the Stockfish chess engine.",
        )
        self.assertEqual(open_graph["url"], "https://example.org/tests/view/123")

    def test_default_open_graph_can_preserve_query_for_shared_page_urls(self):
        open_graph = default_open_graph(
            "https://example.org/actions?max_count=1&before=1775675144.80333#fragment",
            keep_query=True,
        )

        self.assertEqual(
            open_graph["url"],
            "https://example.org/actions?max_count=1&before=1775675144.80333",
        )

    def test_build_tests_view_open_graph_uses_supplied_results_info(self):
        run = {
            "_id": "69d12ae19caf4559aa7ada3e",
            "args": {},
        }
        results_info = {
            "style": "yellow",
            "info": [
                "Synthetic ELO ± line",
                "Synthetic total",
            ],
        }

        open_graph, theme_color = build_tests_view_open_graph(
            page_url="https://example.org/tests/view/69d12ae19caf4559aa7ada3e",
            run=run,
            page_title="400 games - master vs master",
            results_info=results_info,
        )

        self.assertEqual(
            open_graph,
            {
                "site_name": "Stockfish Testing Framework",
                "type": "website",
                "title": "400 games - master vs master | Stockfish Testing",
                "description": "Synthetic ELO +/- line\nSynthetic total",
                "url": "https://example.org/tests/view/69d12ae19caf4559aa7ada3e",
            },
        )
        self.assertEqual(theme_color, "#FFFF00")

    def test_build_tests_view_open_graph_keeps_multiline_pentanomial_summary(
        self,
    ):
        run = {
            "_id": "69d12ae09caf4559aa7ada3c",
            "args": {},
            "results": {
                "wins": 22,
                "losses": 18,
                "draws": 20,
                "pentanomial": [3, 5, 14, 6, 2],
            },
        }

        open_graph, theme_color = build_tests_view_open_graph(
            page_url="https://example.org/tests/view/69d12ae09caf4559aa7ada3c",
            run=run,
            page_title="400 games - master vs master",
            results_info=format_results(run),
        )

        self.assertIn("Elo:", open_graph["description"])
        self.assertIn("nElo:", open_graph["description"])
        self.assertIn("+/-", open_graph["description"])
        self.assertNotIn("&plusmn;", open_graph["description"])
        self.assertIn("Ptnml(0-2):", open_graph["description"])
        self.assertIn("\n", open_graph["description"])
        self.assertNotIn("```", open_graph["description"])
        self.assertIsNone(theme_color)

    def test_build_actions_open_graph_preserves_query_and_describes_first_match(
        self,
    ):
        open_graph = build_actions_open_graph(
            page_url=(
                "https://example.org/actions?max_count=1&before=1775675144.80333"
                "#fragment"
            ),
            actions=[
                {
                    "time": datetime(2026, 4, 8, 19, 5, 44, tzinfo=UTC).timestamp(),
                    "event": "failed_task",
                    "agent_name": "maximmasiutin-12cores-d5026b78-d515",
                    "target_name": "mp-offense-56d4b82/315",
                    "message": "clang++ link failed after profile-build",
                },
                {
                    "time": datetime(2026, 4, 8, 19, 7, 44, tzinfo=UTC).timestamp(),
                    "event": "worker_log",
                    "agent_name": "another-worker",
                    "target_name": "other-run/1",
                    "message": "later event on a different page or sort order",
                },
            ],
            num_actions=2,
            filters={"action": "", "username": "", "text": "", "run_id": ""},
            run_id_filter="",
        )

        self.assertEqual(open_graph["site_name"], "Stockfish Testing Framework")
        self.assertEqual(open_graph["type"], "website")
        self.assertEqual(
            open_graph["title"],
            "failed_task on mp-offense-56d4b82/315 | Stockfish Testing",
        )
        self.assertEqual(
            open_graph["url"],
            "https://example.org/actions?max_count=1&before=1775675144.80333",
        )
        self.assertEqual(
            open_graph["description"],
            "1 of 2 matching actions.\n"
            "Time: 26-04-08 19:05:44\n"
            "Event: failed_task\n"
            "Source: maximmasiutin-12cores-d5026b78-d515\n"
            "Target: mp-offense-56d4b82/315\n"
            "Comment: clang++ link failed after profile-build",
        )
        self.assertNotIn("Most recent of", open_graph["description"])

    def test_build_actions_open_graph_no_results_mentions_active_filters(self):
        open_graph = build_actions_open_graph(
            page_url="https://example.org/actions?user=alice",
            actions=[],
            num_actions=0,
            filters={
                "action": "worker_log",
                "username": "alice",
                "text": "clang",
                "run_id": "",
            },
            run_id_filter="69d12ae19caf4559aa7ada3e",
        )

        self.assertEqual(open_graph["title"], "Events Log | Stockfish Testing")
        self.assertEqual(open_graph["url"], "https://example.org/actions?user=alice")
        self.assertIn(
            "No actions matched the current filters:", open_graph["description"]
        )
        self.assertIn("event=worker_log", open_graph["description"])
        self.assertIn("user=alice", open_graph["description"])
        self.assertIn("text=clang", open_graph["description"])
        self.assertIn("run=69d12ae19caf4559aa7ada3e", open_graph["description"])

    def test_build_actions_open_graph_formats_integer_timestamps(self):
        open_graph = build_actions_open_graph(
            page_url="https://example.org/actions?user=alice",
            actions=[
                {
                    "time": 1775675144,
                    "event": "worker_log",
                    "agent_name": "worker-a",
                    "target_name": "run-a/3",
                    "message": "integer timestamp from stored action data",
                }
            ],
            num_actions=1,
            filters={"action": "", "username": "", "text": "", "run_id": ""},
            run_id_filter="",
        )

        self.assertIn("Time: 26-04-08 19:05:44", open_graph["description"])
