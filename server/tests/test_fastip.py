import unittest

import ipaddress

from utils.fastip import query_by_ip

class FastIPQueryTest(unittest.TestCase):
    def test_10_query_correct(self):
        entry = query_by_ip('8.8.8.8')
        self.assertEqual(entry.country_en, 'United\xa0States')
        self.assertEqual(entry.country_code, 'US')

    def test_10_query_incorrect(self):
        self.assertRaises(ipaddress.AddressValueError, query_by_ip, 'incorrectip')

if __name__ == "__main__":
    unittest.main()