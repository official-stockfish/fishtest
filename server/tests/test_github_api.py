import json
import os
import re
import time
import unittest

import fishtest.github_api as gh
import requests
import util
from fishtest.schemas import books_schema
from fishtest.views import get_master_info
from vtjson import validate


class CreateGitHubApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = util.get_rundb()
        cls.actiondb = cls.rundb.actiondb
        gh.init(cls.rundb.kvstore, cls.rundb.actiondb)
        gh.clear_api_cache()

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
            self.assertTrue(rate_limit["limit"] == 5000)

    def test_kvstore(self):
        self.assertTrue(
            gh.official_master_sha == self.rundb.kvstore["official_master_sha"]
        )
        self.rundb.update_books()
        self.assertTrue(self.rundb.books == self.rundb.kvstore["books"])
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
        self.assertTrue(books == books1)

    def test_sha(self):
        sf10_sha = gh.get_commit(branch="sf_10")["sha"]
        # hard coded sha since the sf_10 tag is frozen forever
        self.assertTrue(sf10_sha == "b4c239b625285307c5871f1104dc3fb80aa6d5d2")

        master_sha = gh.get_commit()["sha"]
        self.assertTrue(master_sha == gh.official_master_sha)

        self.assertFalse(("compare_sha", sf10_sha, master_sha) in gh._lru_cache)
        self.assertFalse(("compare_sha", master_sha, sf10_sha) in gh._lru_cache)

        self.assertTrue(gh.is_ancestor(sha1=sf10_sha, sha2=master_sha))
        self.assertFalse(gh.is_ancestor(sha1=master_sha, sha2=sf10_sha))

        self.assertTrue(("compare_sha", sf10_sha, master_sha) in gh._lru_cache)
        self.assertTrue(("compare_sha", master_sha, sf10_sha) in gh._lru_cache)

        self.assertTrue(gh.is_master(master_sha))
        self.assertTrue(gh.is_master(sf10_sha))

    def test_github_not_found(self):
        dummy_sha = 40 * "f"
        with self.assertRaises(requests.HTTPError):
            gh.compare_sha(sha1=dummy_sha, sha2=dummy_sha)
        self.assertTrue(
            "__error__" in gh._lru_cache[("compare_sha", dummy_sha, dummy_sha)]
        )
        sf10_sha = "b4c239b625285307c5871f1104dc3fb80aa6d5d2"
        r = gh.compare_sha(sha1=sf10_sha, sha2=sf10_sha)
        self.assertFalse("__error__" in r)
        print(r)
        # Cheat!!
        gh._lru_cache[("compare_sha", sf10_sha, sf10_sha)] = {
            "__error__": True,
            "status": 404,
            "http_error": "404 Client Error: Not Found for url: https://api.github.com/repos/official-stockfish/Stockfish/compare/official-stockfish:b4c239b625285307c5871f1104dc3fb80aa6d5d2...official-stockfish:b4c239b625285307c5871f1104dc3fb80aa6d5d2",
            "url": "https://api.github.com/repos/official-stockfish/Stockfish/compare/official-stockfish:b4c239b625285307c5871f1104dc3fb80aa6d5d2...official-stockfish:b4c239b625285307c5871f1104dc3fb80aa6d5d2",
            "github_error": {
                "message": "Not Found",
                "documentation_url": "https://docs.github.com/rest/commits/commits#compare-two-commits",
                "status": "404",
            },
            "timestamp": time.time(),
        }
        r = gh.compare_sha(sha1=sf10_sha, sha2=sf10_sha)
        self.assertFalse("__error__" in r)
        a = list(self.actiondb.get_actions(username="fishtest.system")[0])[0]
        print(a)
        self.assertTrue("The previous attempt" in a["message"])
        self.assertTrue(r == gh._lru_cache[("compare_sha", sf10_sha, sf10_sha)])

    def tearDown(self):
        if hasattr(self.rundb, "books"):
            del self.rundb.books
        self.rundb.kvstore.pop("books", None)
        gh.clear_api_cache()

    @classmethod
    def tearDownClass(cls):
        cls.rundb.db.kvstore.drop()


if __name__ == "__main__":
    unittest.main()
