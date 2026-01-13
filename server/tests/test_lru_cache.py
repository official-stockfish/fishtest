import threading
import time
import unittest

from fishtest.lru_cache import LRUCache, lru_cache


class CreateLRUCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maxsize = 10
        cls.lru_cache = LRUCache()

    def setUp(self):
        self.lru_cache.maxsize = self.maxsize
        self.lru_cache.expiration = None
        self.lru_cache.refresh = True
        self.lru_cache.clear()

    def test_lru_cache_size(self):
        self.assertEqual(self.lru_cache.maxsize, self.maxsize)
        with self.assertRaises(ValueError):
            LRUCache(maxsize=-1)
        with self.assertRaises(ValueError):
            self.lru_cache.maxsize = -1
        self.lru_cache["a"] = 1
        self.lru_cache.maxsize = 0
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
        self.assertEqual(self.lru_cache.refresh, True)

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
        for i in range(self.maxsize + 1):
            self.lru_cache[str(i)] = i
        self.assertEqual(len(self.lru_cache), self.maxsize)
        self.assertEqual(
            list(self.lru_cache.values()),
            list(range(1, self.maxsize + 1)),
        )

    def test_lru_cache_reordering_get(self):
        for i in range(self.maxsize + 1):
            self.lru_cache[str(i)] = i
        self.lru_cache["5"]
        result = list(range(1, self.maxsize + 1))
        del result[4]
        result.append(5)
        self.assertEqual(list(self.lru_cache.values()), result)

    def test_lru_cache_reordering_set(self):
        for i in range(self.maxsize + 1):
            self.lru_cache[str(i)] = i
        self.lru_cache["5"] = 11
        result = list(range(1, self.maxsize + 1))
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
        self.lru_cache.maxsize = 1
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

    def test_lru_cache_invalid_release(self):
        with self.assertRaises(RuntimeError):
            self.lru_cache.lock.release()

    def test_lru_cache_invalid_release_threaded(self):
        self.lru_cache.lock.acquire()

        def worker():
            with self.assertRaises(RuntimeError):
                self.lru_cache.lock.release()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        self.lru_cache.lock.release()

    def test_lru_cache_reacquire(self):
        with self.lru_cache.lock, self.lru_cache.lock:
            pass

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

    def test_lru_cache_non_blocking(self):
        with self.lru_cache.lock:
            acquired = self.lru_cache.lock.acquire(blocking=False)
            self.assertTrue(acquired)
            self.lru_cache.lock.release()

    def test_lru_cache_non_blocking_threaded(self):
        def worker():
            acquired = self.lru_cache.lock.acquire(blocking=False)
            self.assertFalse(acquired)

        t = threading.Thread(target=worker)

        with self.lru_cache.lock:
            t.start()
            t.join()

    def test_lru_cache_timeout(self):
        with self.lru_cache.lock:
            acquired = self.lru_cache.lock.acquire(timeout=0.1)
            self.assertTrue(acquired)
            self.lru_cache.lock.release()

    def test_lru_cache_timeout_threaded(self):
        def worker1():
            acquired = self.lru_cache.lock.acquire(timeout=0.1)
            self.assertFalse(acquired)

        t = threading.Thread(target=worker1)

        with self.lru_cache.lock:
            t.start()
            t.join()

        worker_started = threading.Event()
        lock_acquired = threading.Event()

        def worker2():
            worker_started.set()
            acquired = self.lru_cache.lock.acquire(timeout=1.0)
            lock_acquired.set()
            self.assertTrue(acquired)
            self.lru_cache.lock.release()

        t = threading.Thread(target=worker2)

        self.lru_cache.acquire()
        t.start()
        worker_started.wait(timeout=1.0)
        time.sleep(0.1)
        self.assertFalse(lock_acquired.is_set())
        self.lru_cache.release()
        t.join()
        self.assertTrue(lock_acquired.is_set())

    def test_lru_cache_lock_timing(self):
        self.lru_cache.expiration = 0.1
        self.lru_cache["a"] = 1
        with self.lru_cache.lock:
            time.sleep(0.2)
            # the entry does not expire when we hold the lock
            self.assertIn("a", self.lru_cache)
        # the entry expires after releasing the lock
        self.assertNotIn("a", self.lru_cache)

    def test_lru_cache_refresh(self):
        self.lru_cache.refresh = False
        self.lru_cache["a"] = 1
        self.lru_cache["b"] = 2
        self.lru_cache["a"]
        self.assertEqual(list(self.lru_cache.keys()), ["a", "b"])

    def test_lru_cache_refresh_timing(self):
        self.lru_cache.expiration = 0.15
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is refreshed
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is still accessible

        self.lru_cache.clear()
        self.lru_cache.refresh = False
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache["a"]  # entry is not refreshed
        time.sleep(0.1)
        with self.assertRaises(KeyError):
            self.lru_cache["a"]  # entry is no longer accessible

        self.lru_cache.clear()
        self.lru_cache.refresh = True
        self.lru_cache["a"] = 1
        time.sleep(0.1)
        self.lru_cache.get("a", refresh=False)  # entry is not refreshed
        self.assertEqual(self.lru_cache.refresh, True)
        time.sleep(0.1)
        with self.assertRaises(KeyError):
            self.lru_cache["a"]  # entry is no longer accessible

    def test_lru_cache_decorator(self):
        @lru_cache(expiration=0.15)
        def worker1():
            return time.time()

        t0 = worker1()
        time.sleep(0.1)
        t1 = worker1()  # refreshes cache
        self.assertEqual(t0, t1)
        time.sleep(0.1)
        t2 = worker1()
        self.assertEqual(t2, t0)
        time.sleep(0.2)  # cache expires
        t3 = worker1()
        self.assertNotEqual(t3, t0)

        @lru_cache(expiration=0.15, refresh=False)
        def worker2():
            return time.time()

        t0 = worker2()
        time.sleep(0.1)
        t1 = worker2()  # does not refresh cache
        self.assertEqual(t0, t1)
        time.sleep(0.1)  # cache expires
        t2 = worker2()
        self.assertNotEqual(t2, t0)

    def test_lru_cache_decorator_ambiguous_arguments(self):
        with self.assertRaises(ValueError):

            @lru_cache(refresh=True, cache=self.lru_cache)
            def worker():
                pass

    def test_lru_cache_decorator_recycle(self):
        self.lru_cache.expiration = 0.15

        @lru_cache(cache=self.lru_cache)
        def worker1():
            return time.time()

        self.assertEqual(self.lru_cache, worker1.cache)

        t0 = worker1()
        time.sleep(0.1)
        t1 = worker1()  # refreshes cache
        self.assertEqual(t0, t1)
        time.sleep(0.1)
        t2 = worker1()
        self.assertEqual(t2, t0)
        time.sleep(0.2)  # cache expires
        t3 = worker1()
        self.assertNotEqual(t3, t0)

        self.lru_cache.refresh = False
        self.lru_cache.clear()

        @lru_cache(cache=self.lru_cache)
        def worker2():
            return time.time()

        self.assertEqual(self.lru_cache, worker2.cache)

        t0 = worker2()
        time.sleep(0.1)
        t1 = worker2()  # does not refresh cache
        self.assertEqual(t0, t1)
        time.sleep(0.1)  # cache expires
        t2 = worker2()
        self.assertNotEqual(t2, t0)

    def test_lru_cache_keyword_order(self):
        evaluated = False

        @lru_cache()
        def worker(a=None, b=None):
            nonlocal evaluated
            evaluated = True

        worker(a=1, b=1)
        self.assertTrue(evaluated)
        evaluated = False
        worker(a=1, b=1)
        self.assertFalse(evaluated)
        worker(a=1, b=1)
        self.assertFalse(evaluated)
        worker(b=1, a=1)
        self.assertFalse(evaluated)

    def test_lru_cache_decorator_filter(self):
        def simple_key(f, args, kw):
            return args[0]

        def no_negative_caching(f, args, kw, val):
            return val is not None

        @lru_cache(key=simple_key)
        def worker1(arg):
            if arg == "good":
                return "found"
            return None

        worker1("good")
        self.assertIn("good", worker1.cache)
        worker1("bad")
        self.assertIn("bad", worker1.cache)

        @lru_cache(key=simple_key, filter=no_negative_caching)
        def worker2(arg):
            if arg == "good":
                return "found"
            return None

        worker2("good")
        self.assertIn("good", worker2.cache)
        worker2("bad")
        self.assertNotIn("bad", worker2.cache)
