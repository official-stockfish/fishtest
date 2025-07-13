import re
import unittest

import fishtest.github_api as gh
import util
from fishtest.views import get_master_info


class CreateRunTest(unittest.TestCase):
    def test_10_get_bench(self):
        rundb = util.get_rundb()
        gh.init(rundb.kvstore)
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


if __name__ == "__main__":
    unittest.main()
