"""Test Open Graph metadata helpers."""

import unittest

from fishtest.http.open_graph import (
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
            host_url="https://example.org",
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
            host_url="https://example.org",
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
