import re
import unittest

from fishtest.views import get_master_info


class CreateRunTest(unittest.TestCase):
    def test_10_get_bench(self):
        master_commits_url = (
            "https://api.github.com/repos/official-monty/Monty/commits"
        )
        self.assertTrue(
            re.match(
                r"[1-9]\d{5,7}|None", str(get_master_info(master_commits_url)["bench"])
            )
        )


if __name__ == "__main__":
    unittest.main()
