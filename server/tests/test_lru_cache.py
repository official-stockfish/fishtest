import threading
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
        self.assertIs(self.lru_cache.get("a"), None)
        self.assertEqual(self.lru_cache.get("a", 10), 10)
        with self.assertRaises(TypeError):
            self.lru_cache.get("a", refresh=False, invalid_option="dummy")
        self.assertEqual(self.lru_cache.refresh_on_access, True)

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
        self.assertEqual(list(self.lru_cache.keys()), ["a", "b"])
        self.lru_cache["a"]
        self.assertEqual(list(self.lru_cache.keys()), ["b", "a"])
        self.lru_cache.get("b", refresh=False)
        self.assertEqual(list(self.lru_cache.keys()), ["b", "a"])
        self.lru_cache.get("b", refresh=True)
        self.assertEqual(list(self.lru_cache.keys()), ["a", "b"])

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

    def test_lru_cache_lock(self):
        self.lru_cache.size = 1
        self.lru_cache["a"] = 1
        with self.lru_cache.lock:
            self.lru_cache["b"] = 2
            # the entry does not expire when we hold the lock
            self.assertIn("a", self.lru_cache)
        # the entry expires after releasing the lock
        self.assertNotIn("a", self.lru_cache)

    def test_lru_cache_lock_atomicity(self):
        delete_started = threading.Event()

        def worker():
            # Signal that the worker is about to attempt deletion.
            delete_started.set()
            del self.lru_cache["a"]

        with self.lru_cache.lock:
            self.lru_cache["a"] = 1
            t = threading.Thread(target=worker)
            t.start()
            # Wait until the worker has started and is about to delete.
            delete_started.wait(timeout=1.0)
            time.sleep(0.1)
            # not deleted by other thread since the object is locked
            self.assertIn("a", self.lru_cache)
        # now the other thread got a chance to run after the lock is released
        t.join()
        self.assertNotIn("a", self.lru_cache)
        # redo test without locking
        delete_started.clear()
        self.lru_cache["a"] = 1
        t = threading.Thread(target=worker)
        t.start()
        # wait for deletion to complete
        t.join()
        # now deleted by other thread
        self.assertNotIn("a", self.lru_cache)

    def test_lru_cache_reacquire(self):
        with self.lru_cache.lock:
            with self.assertRaises(RuntimeError):
                self.lru_cache.lock.acquire()

    def test_lru_cache_reacquire_threaded(self):
        worker_started = threading.Event()
        worker_has_run = threading.Event()

        def worker():
            worker_started.set()
            with self.lru_cache.lock:
                worker_has_run.set()

        t = threading.Thread(target=worker)
        with self.lru_cache.lock:
            t.start()
            # Wait for the worker to start and attempt to acquire the lock.
            self.assertTrue(worker_started.wait(timeout=1.0))
            time.sleep(0.1)
            # Worker should be blocked on the lock and not have run yet.
            self.assertFalse(worker_has_run.is_set())
        # After releasing the lock, the worker should acquire it and run.
        self.assertTrue(worker_has_run.wait(timeout=1.0))
        t.join()

    def test_lru_cache_lock_timing(self):
        self.lru_cache.expiration = 0.1
        self.lru_cache["a"] = 1
        with self.lru_cache.lock:
            time.sleep(0.2)
            # the entry does not expire when we hold the lock
            self.assertIn("a", self.lru_cache)
        # the entry expires after releasing the lock
        self.assertNotIn("a", self.lru_cache)

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

        self.lru_cache.clear()
        self.lru_cache.refresh_on_access = True
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache.get("a", refresh=False)  # entry is not refreshed
        self.assertEqual(self.lru_cache.refresh_on_access, True)
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
