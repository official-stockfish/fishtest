import re
import unittest

from fishtest.views import get_master_info


class CreateRunTest(unittest.TestCase):
    def test_10_get_bench(self):
        self.assertTrue(re.match("[0-9]{7}|None", str(get_master_info()["bench"])))


if __name__ == "__main__":
    unittest.main()
