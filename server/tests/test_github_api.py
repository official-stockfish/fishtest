import json
import os
import re
import unittest
from unittest import mock

import requests
import test_support
from vtjson import validate

import fishtest.github_api as gh
from fishtest.schemas import books_schema
from fishtest.views import get_master_info


class CreateGitHubApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = test_support.get_rundb()
        cls.actiondb = cls.rundb.actiondb
        gh.init(cls.rundb.kvstore, cls.rundb.actiondb)
        gh.clear_api_cache()
        cls.sf10_sha = gh.get_commit(branch="sf_10")["sha"]
        # cls.tools_sha = gh.get_commit(branch="tools")["sha"]
        # Hard coded because the tools branch may change
        cls.tools_sha = "9a4c7cf4e311f8d9526b79295b80c4d0464c07cf"
        cls.dummy_sha = 40 * "f"
        commits = gh.get_commits()
        assert commits[0]["sha"] == gh.official_master_sha
        cls.official_master_hat_sha = commits[1]["sha"]
        cls.official_master_hathat_sha = commits[2]["sha"]
        cls.saved_official_master_sha = gh.official_master_sha

    def test_get_bench(self):
        self.assertTrue(
            re.match(
                r"[1-9]\d{5,7}|None",
                str(
                    get_master_info(
                        user="official-stockfish",
                        repo="Stockfish",
                    )["bench"]
                ),
            )
        )

    def test_rate_limit(self):
        rate_limit = gh.rate_limit()
        # GH_TOKEN is set to GITHUB_TOKEN during ci.
        if "GH_TOKEN" in os.environ:
            self.assertEqual(rate_limit["limit"], 5000)

    def test_kvstore(self):
        self.assertEqual(
            gh.official_master_sha, self.rundb.kvstore["official_master_sha"]
        )
        self.rundb.update_books()
        self.assertEqual(self.rundb.books, self.rundb.kvstore["books"])
        # No need to manually delete kvstore or books; tearDown will handle restoration

    def test_download(self):
        books = json.loads(
            gh.download_from_github(
                "books.json",
                repo="books",
                method="api",
            ).decode()
        )
        # test passes if no exception is raised
        validate(
            books_schema,
            books,
            name="books",
        )
        books1 = json.loads(
            gh.download_from_github(
                "books.json",
                repo="books",
                method="raw",
            ).decode()
        )
        self.assertEqual(books, books1)

    def test_sha(self):
        def key(sha1, sha2):
            return gh.compare_sha.key(gh.compare_sha, (), {"sha1": sha1, "sha2": sha2})

        # hard coded sha since the sf_10 tag is frozen forever
        self.assertEqual(self.sf10_sha, "b4c239b625285307c5871f1104dc3fb80aa6d5d2")

        master_sha = gh.get_commit()["sha"]
        self.assertEqual(master_sha, gh.official_master_sha)

        self.assertNotIn(key(self.sf10_sha, master_sha), gh._lru_cache)
        self.assertNotIn(key(master_sha, self.sf10_sha), gh._lru_cache)

        self.assertTrue(gh.is_ancestor(sha1=self.sf10_sha, sha2=master_sha))
        self.assertFalse(gh.is_ancestor(sha1=master_sha, sha2=self.sf10_sha))

        self.assertIn(key(self.sf10_sha, master_sha), gh._lru_cache)
        self.assertIn(key(master_sha, self.sf10_sha), gh._lru_cache)

        self.assertTrue(gh.is_master(master_sha))
        self.assertTrue(gh.is_master(self.sf10_sha))

    def test_is_master(self):
        def key(sha):
            return gh._is_master.key(gh._is_master, (sha,), {})

        # fake official_master_sha
        gh.official_master_sha = self.official_master_hat_sha
        with self.assertRaises(requests.HTTPError):
            gh.get_merge_base_commit(sha1=self.dummy_sha, sha2=gh.official_master_sha)
        self.assertFalse(gh.is_master(self.dummy_sha))
        # dummy_sha "has been deleted"
        self.assertFalse(gh._lru_cache[key(self.dummy_sha)])

        self.assertTrue(gh.is_master(self.official_master_hathat_sha))
        # once master, forever master
        self.assertTrue(gh._lru_cache[key(self.official_master_hathat_sha)])

        # test passes if no exception is raised
        gh.get_merge_base_commit(sha1=self.tools_sha, sha2=gh.official_master_sha)
        self.assertFalse(gh.is_master(self.tools_sha))
        # tools_sha will never become master
        self.assertFalse(gh._lru_cache[key(self.tools_sha)])

        # note that we faked gh.official_master_sha above
        self.assertFalse(gh.is_master(self.saved_official_master_sha))
        # this one may still become "master"
        self.assertNotIn(key(self.saved_official_master_sha), gh._lru_cache)

    def tearDown(self):
        if hasattr(self.rundb, "books"):
            del self.rundb.books
        self.rundb.kvstore.pop("books", None)
        gh.clear_api_cache()
        gh.official_master_sha = self.saved_official_master_sha

    @classmethod
    def tearDownClass(cls):
        cls.rundb.db.kvstore.drop()


class MasterInfoRobustnessTests(unittest.TestCase):
    def test_get_master_info_returns_stable_shape_on_exception(self):
        with mock.patch(
            "fishtest.views.gh.get_commits",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            info = get_master_info(ignore_rate_limit=True)
        self.assertIsInstance(info, dict)
        self.assertIn("bench", info)
        self.assertIn("message", info)
        self.assertIn("date", info)
        self.assertIsNone(info["bench"])

    def test_get_master_info_handles_unexpected_payload_shapes(self):
        for payload in ({"message": "API rate limit exceeded"}, [], None):
            with mock.patch("fishtest.views.gh.get_commits", return_value=payload):
                info = get_master_info(ignore_rate_limit=True)
            self.assertIsInstance(info, dict)
            self.assertIn("bench", info)
            self.assertIn("message", info)
            self.assertIn("date", info)

    def test_get_master_info_ignores_malformed_entries_in_commit_list(self):
        payload = [
            {
                "commit": {
                    "message": "Title without bench",
                    "committer": {"date": "2026-02-24T12:00:00Z"},
                }
            },
            {},  # malformed entry should be ignored
            {
                "commit": {
                    "message": "Some text\nBench 1234567",
                    "committer": {"date": "2026-02-24T12:05:00Z"},
                }
            },
        ]
        with mock.patch("fishtest.views.gh.get_commits", return_value=payload):
            info = get_master_info(ignore_rate_limit=True)

        self.assertEqual(info["bench"], "1234567")


class GitHubApiRetryTests(unittest.TestCase):
    def _run_call_with_side_effect(self, side_effect):
        old_initialized = gh._api_initialized
        try:
            gh._api_initialized = True
            with (
                mock.patch(
                    "fishtest.github_api.requests.request",
                    side_effect=side_effect,
                ) as req,
                mock.patch("fishtest.github_api.time.sleep") as _sleep,
            ):
                r = gh.call("https://api.github.com/rate_limit", timeout=0.01)
            return r, req.call_count
        finally:
            gh._api_initialized = old_initialized

    def test_call_retries_once_on_connection_error_for_get(self):
        ok_response = requests.Response()
        ok_response.status_code = 200
        ok_response._content = b"ok"
        ok_response.headers = {
            # Avoid mutating module-level rate-limit globals in this test.
            "X-RateLimit-Resource": "test",
        }

        r, call_count = self._run_call_with_side_effect(
            [requests.exceptions.ConnectionError("drop"), ok_response]
        )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(call_count, 2)

    def test_call_retries_once_on_transient_5xx_for_get(self):
        bad_response = requests.Response()
        bad_response.status_code = 502
        bad_response._content = b"bad gateway"
        bad_response.headers = {
            "X-RateLimit-Resource": "test",
        }

        ok_response = requests.Response()
        ok_response.status_code = 200
        ok_response._content = b"ok"
        ok_response.headers = {
            "X-RateLimit-Resource": "test",
        }

        r, call_count = self._run_call_with_side_effect([bad_response, ok_response])

        self.assertEqual(r.status_code, 200)
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
