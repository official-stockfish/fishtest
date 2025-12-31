import time
import unittest

from fishtest.lru_cache import LRUCache
from vtjson import ValidationError, validate
from vtjson import filter as filter_


class CreateLRUCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.size = 10
        cls.lru_cache = LRUCache()

    def setUp(self):
        self.lru_cache.size = self.size
        self.lru_cache.expiration = None
        self.lru_cache.refresh_on_access = True
        self.lru_cache.clear()

    def test_lru_cache_size(self):
        self.assertEqual(self.lru_cache.size, self.size)
        with self.assertRaises(ValueError):
            LRUCache(size=-1)
        with self.assertRaises(ValueError):
            self.lru_cache.size = -1
        self.lru_cache["a"] = 1
        self.lru_cache.size = 0
        self.assertEqual(len(self.lru_cache), 0)

    def test_lru_cache_clear(self):
        self.lru_cache["a"] = 1
        self.lru_cache.clear()
        self.assertEqual(len(self.lru_cache), 0)

    def test_lru_cache_getsetitem(self):
        with self.assertRaises(KeyError):
            self.lru_cache["a"]
        self.lru_cache["a"] = 1
        self.assertEqual(self.lru_cache["a"], 1)

    def test_lru_cache_delitem(self):
        with self.assertRaises(KeyError):
            del self.lru_cache["a"]
        self.lru_cache["a"] = 1
        del self.lru_cache["a"]
        with self.assertRaises(KeyError):
            del self.lru_cache["a"]

    def test_lru_cache_contains(self):
        self.assertNotIn("a", self.lru_cache)
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.assertIn("a", self.lru_cache)
        self.assertEqual(list(self.lru_cache.keys()), ["a", "b"])
        del self.lru_cache["a"]
        self.assertNotIn("a", self.lru_cache)

    def test_lru_cache_len(self):
        self.assertEqual(len(self.lru_cache), 0)
        self.lru_cache["a"] = 1
        self.assertEqual(len(self.lru_cache), 1)
        self.lru_cache["b"] = 1
        self.assertEqual(len(self.lru_cache), 2)

    def test_lru_cache_get(self):
        with self.assertRaises(KeyError):
            self.lru_cache["a"]
        self.assertEqual(self.lru_cache.get("a", 10), 10)
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.lru_cache["a"]
        self.assertEqual(list(self.lru_cache.keys()), ["b", "a"])

    def test_lru_cache_pop(self):
        with self.assertRaises(KeyError):
            self.lru_cache.pop("a")
        x = self.lru_cache.pop("a", 1)
        self.assertEqual(x, 1)

    def test_lru_cache_popitem(self):
        with self.assertRaises(KeyError):
            self.lru_cache.popitem()
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        x = self.lru_cache.popitem()
        self.assertIn(x, {("a", 1), ("b", 2)})
        self.assertNotIn(x, self.lru_cache.items())

    def test_lru_cache_iter(self):
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.assertEqual(set(iter(self.lru_cache)), {"a", "b"})

    def test_lru_cache_keys(self):
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.assertEqual(set(self.lru_cache.keys()), {"a", "b"})

    def test_lru_cache_values(self):
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.assertEqual(set(self.lru_cache.values()), {1, 2})

    def test_lru_cache_items(self):
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.assertEqual(set(self.lru_cache.items()), {("a", 1), ("b", 2)})

    def test_lru_cache_insertion(self):
        for i in range(0, self.size + 1):
            self.lru_cache[str(i)] = i
        self.assertEqual(len(self.lru_cache), self.size)
        self.assertEqual(list(self.lru_cache.values()), list(range(1, self.size + 1)))

    def test_lru_cache_reordering_get(self):
        for i in range(0, self.size + 1):
            self.lru_cache[str(i)] = i
        self.lru_cache["5"]
        result = list(range(1, self.size + 1))
        del result[4]
        result.append(5)
        self.assertEqual(list(self.lru_cache.values()), result)

    def test_lru_cache_reordering_set(self):
        for i in range(0, self.size + 1):
            self.lru_cache[str(i)] = i
        self.lru_cache["5"] = 11
        result = list(range(1, self.size + 1))
        del result[4]
        result.append(11)
        self.assertEqual(list(self.lru_cache.values()), result)

    def test_lru_cache_expiration(self):
        self.lru_cache.expiration = -1
        self.lru_cache["a"] = 1
        self.assertNotIn("a", self.lru_cache)
        self.assertEqual(len(self.lru_cache), 0)
        self.lru_cache.expiration = 10
        self.assertNotIn("a", self.lru_cache)
        self.assertEqual(len(self.lru_cache), 0)
        self.lru_cache["a"] = 1
        self.assertIn("a", self.lru_cache)
        self.assertEqual(len(self.lru_cache), 1)
        self.lru_cache.expiration = -1
        self.assertNotIn("a", self.lru_cache)
        self.assertEqual(len(self.lru_cache), 0)

    def test_lru_cache_expiration_timing(self):
        self.lru_cache.expiration = 0.1
        self.lru_cache["a"] = 1
        time.sleep(0.2)
        self.lru_cache["b"] = 2
        self.lru_cache["c"] = 3
        self.assertEqual(list(self.lru_cache.items()), [("b", 2), ("c", 3)])
        time.sleep(0.2)
        self.assertEqual(list(self.lru_cache.items()), [])

    def test_lru_cache_expiration_get(self):
        self.lru_cache.expiration = 0.1
        self.lru_cache["a"] = 1
        self.lru_cache["a"]
        time.sleep(0.2)
        with self.assertRaises(KeyError):
            self.lru_cache["a"]

    def test_lru_cache_refresh_on_access(self):
        self.lru_cache.refresh_on_access = False
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.lru_cache["a"]
        self.assertEqual(list(self.lru_cache.keys()), ["a", "b"])

    def test_lru_cache_refresh_on_access_timing(self):
        self.lru_cache.expiration = 0.15
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is refreshed
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is still accessible

        self.lru_cache.clear()
        self.lru_cache.refresh_on_access = False
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is not refreshed
        time.sleep(0.1)
        with self.assertRaises(KeyError):
            self.lru_cache["a"]  # entry is no longer accessible

    def test_lru_cache_validation(self):
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        schema = filter_(dict, {str: int})
        validate(schema, self.lru_cache, "lru_cache")
        self.lru_cache["c"] = "3"
        with self.assertRaises(ValidationError):
            validate(schema, self.lru_cache, "lru_cache")
