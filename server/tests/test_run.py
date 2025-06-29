import re
import unittest

from fishtest.views import get_master_info


class CreateRunTest(unittest.TestCase):
    def test_10_get_bench(self):
        self.assertTrue(
            re.match(
                r"[1-9]\d{5,7}|None",
                str(
                    get_master_info(
                        user="official-stockfish",
                        repo="Stockfish",
                        ignore_rate_limit=True,
                    )["bench"]
                ),
            )
        )


if __name__ == "__main__":
    unittest.main()
