"""Test game execution setup."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import games


class StopAfterEngineSetup(Exception):
    pass


class RunGamesTest(unittest.TestCase):
    def check_engine_setup(self, resolved_new, resolved_base, expected_calls):
        with tempfile.TemporaryDirectory() as tmp:
            worker_dir = Path(tmp)
            testing_dir = worker_dir / "testing"
            testing_dir.mkdir()

            book = testing_dir / "book.epd"
            book.write_text("test opening\n")
            book_sri = games.text_hash(book)

            run = {
                "_id": "test-run",
                "my_task": {"num_games": 2},
                "args": {
                    "book": "book.epd",
                    "book_depth": 1,
                    "book_sri": book_sri,
                    "new_options": "Hash=16",
                    "base_options": "Hash=16",
                    "threads": "1",
                    "resolved_new": resolved_new,
                    "resolved_base": resolved_base,
                },
            }

            worker_info = {
                "concurrency": 1,
                "compiler": "g++",
                "gcc_version": [1, 0, 0],
            }

            original_cwd = Path.cwd()
            try:
                with patch.object(
                    games,
                    "setup_engine",
                    side_effect=[
                        testing_dir / "new-engine",
                        testing_dir / "base-engine",
                    ],
                ) as setup_engine:
                    with patch.object(
                        games,
                        "required_nets",
                        side_effect=StopAfterEngineSetup,
                    ):
                        with self.assertRaises(StopAfterEngineSetup):
                            games.run_games(
                                worker_dir,
                                worker_info,
                                {},
                                "password",
                                "http://localhost",
                                run,
                                0,
                                {},
                                None,
                            )

                        self.assertEqual(setup_engine.call_count, expected_calls)
            finally:
                os.chdir(original_cwd)

    def test_identical_engine_shas_setup_once(self):
        self.check_engine_setup("same-sha", "same-sha", 1)

    def test_different_engine_shas_setup_twice(self):
        self.check_engine_setup("new-sha", "base-sha", 2)


if __name__ == "__main__":
    unittest.main()
