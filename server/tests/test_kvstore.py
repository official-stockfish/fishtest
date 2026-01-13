import unittest

from fishtest.kvstore import KeyValueStore


class CreateKeyValueStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kvstore = KeyValueStore(db_name="fishtest_tests", collection="test_kvstore")

    def tearDown(self):
        self.kvstore.clear()

    def test_kvstore_invalid_invocation(self):
        with self.assertRaises(ValueError):
            KeyValueStore()

    def test_kvstore_persistence(self):
        kvstore_tmp = KeyValueStore(
            db_name="fishtest_tests",
            collection="test_kvstore_tmp",
        )
        kvstore_tmp["a"] = 1
        kvstore_tmp.close()
        # the actual exception is AttributeError, but that is not
        # relevant
        with self.assertRaises(Exception):
            kvstore_tmp["a"]
        kvstore_tmp = KeyValueStore(
            db_name="fishtest_tests",
            collection="test_kvstore_tmp",
        )
        self.assertEqual(kvstore_tmp["a"], 1)
        kvstore_tmp.drop()

    def test_kvstore_clear(self):
        self.kvstore["a"] = 1
        self.kvstore.clear()
        self.assertEqual(len(self.kvstore), 0)

    def test_kvstore_getsetitem(self):
        with self.assertRaises(KeyError):
            self.kvstore["a"]
        self.kvstore["a"] = 1
        self.assertEqual(self.kvstore["a"], 1)

    def test_kvstore_delitem(self):
        with self.assertRaises(KeyError):
            del self.kvstore["a"]
        self.kvstore["a"] = 1
        del self.kvstore["a"]
        with self.assertRaises(KeyError):
            del self.kvstore["a"]

    def test_kvstore_contains(self):
        self.assertNotIn("a", self.kvstore)
        self.kvstore["a"] = 1
        self.assertIn("a", self.kvstore)
        del self.kvstore["a"]
        self.assertNotIn("a", self.kvstore)

    def test_kvstore_len(self):
        self.assertEqual(len(self.kvstore), 0)
        self.kvstore["a"] = 1
        self.assertEqual(len(self.kvstore), 1)
        self.kvstore["b"] = 1
        self.assertEqual(len(self.kvstore), 2)

    def test_kvstore_get(self):
        with self.assertRaises(KeyError):
            self.kvstore["a"]
        self.assertEqual(self.kvstore.get("a", 10), 10)

    def test_kvstore_pop(self):
        with self.assertRaises(KeyError):
            self.kvstore.pop("a")
        x = self.kvstore.pop("a", 1)
        self.assertEqual(x, 1)

    def test_kvstore_popitem(self):
        with self.assertRaises(KeyError):
            self.kvstore.popitem()
        self.kvstore["a"] = 1
        self.kvstore["b"] = 2
        x = self.kvstore.popitem()
        self.assertIn(x, {("a", 1), ("b", 2)})
        self.assertNotIn(x, self.kvstore.items())

    def test_kvstore_iter(self):
        self.kvstore["a"] = 1
        self.kvstore["b"] = 2
        self.assertEqual(set(iter(self.kvstore)), {"a", "b"})

    def test_kvstore_keys(self):
        self.kvstore["a"] = 1
        self.kvstore["b"] = 2
        self.assertEqual(set(self.kvstore.keys()), {"a", "b"})

    def test_kvstore_values(self):
        self.kvstore["a"] = 1
        self.kvstore["b"] = 2
        self.assertEqual(set(self.kvstore.values()), {1, 2})

    def test_kvstore_items(self):
        self.kvstore["a"] = 1
        self.kvstore["b"] = 2
        self.assertEqual(set(self.kvstore.items()), {("a", 1), ("b", 2)})

    def test_kvstore_invalid_input(self):
        o = object()
        with self.assertRaisesRegex(ValueError, "not a string"):
            self.kvstore[o]
        with self.assertRaisesRegex(ValueError, "not a string"):
            self.kvstore[o] = "dummy"
        with self.assertRaisesRegex(ValueError, "cannot be converted to bson"):
            self.kvstore["dummy"] = o
        with self.assertRaisesRegex(ValueError, "not a string"):
            del self.kvstore[o]

    @classmethod
    def tearDownClass(cls):
        cls.kvstore.drop()
