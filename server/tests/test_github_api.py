import json
import os
import re
import unittest

import fishtest.github_api as gh
import util
from fishtest.schemas import books_schema
from fishtest.views import get_master_info
from vtjson import validate


class CreateGitHubApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rundb = util.get_rundb()
        gh.init(cls.rundb.kvstore)

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

    def tearDown(self):
        if hasattr(self.rundb, "books"):
            del self.rundb.books
        self.rundb.kvstore.pop("books", None)

    @classmethod
    def tearDownClass(cls):
        cls.rundb.db.kvstore.drop()


if __name__ == "__main__":
    unittest.main()
