import unittest

from fishtest.util import _keys, optional_key, union, validate


class TestValidation(unittest.TestCase):
    def test_keys(self):
        schema = {optional_key("a"): 1, "b": 2, optional_key("c"): 3}
        keys = _keys(schema)
        self.assertEqual(keys, {"a", "b", "c"})

    def test_strict(self):
        schema = {optional_key("a"): 1, "b": 2}
        name = "my_object"
        object = {"b": 2, "c": 3}
        valid = validate(schema, object, name, strict=True)
        self.assertFalse(valid == "")

        object = {"a": 1, "c": 3}
        valid = validate(schema, object, name, strict=True)
        self.assertFalse(valid == "")

        object = {"a": 1, "b": 2}
        valid = validate(schema, object, name, strict=True)
        self.assertTrue(valid == "")

        object = {"b": 2}
        valid = validate(schema, object, name, strict=True)
        self.assertTrue(valid == "")

    def test_missing_keys(self):
        schema = {optional_key("a"): 1, "b": 2}
        name = "my_object"
        object = {"b": 2, "c": 3}
        valid = validate(schema, object, name, strict=False)
        self.assertTrue(valid == "")

        object = {"a": 1, "c": 3}
        valid = validate(schema, object, name, strict=False)
        self.assertFalse(valid == "")

        object = {"a": 1, "b": 2}
        valid = validate(schema, object, name, strict=False)
        self.assertTrue(valid == "")

        object = {"b": 2}
        valid = validate(schema, object, name, strict=False)
        self.assertTrue(valid == "")

    def test_union(self):
        schema = {optional_key("a"): 1, "b": union(2, 3)}
        name = "my_object"
        object = {"b": 2, "c": 3}
        valid = validate(schema, object, name, strict=False)
        self.assertTrue(valid == "")

        object = {"b": 4, "c": 3}
        valid = validate(schema, object, name, strict=False)
        self.assertFalse(valid == "")

    def test_validate(self):
        class lower_case_string:
            @staticmethod
            def __validate__(object, name, strict=False):
                if not isinstance(object, str):
                    return f"{name} is not a string"
                for c in object:
                    if not ("a" <= c <= "z"):
                        return f"{c}, contained in the string {name}, is not a lower case letter"
                return ""

        schema = lower_case_string
        object = 1
        name = "my_object"
        valid = validate(schema, object, name, strict=True)
        self.assertFalse(valid == "")

        object = "aA"
        valid = validate(schema, object, name, strict=True)
        self.assertFalse(valid == "")

        object = "ab"
        valid = validate(schema, object, name, strict=True)
        self.assertTrue(valid == "")

        schema = {"a": lower_case_string}
        object = {"a": "ab"}
        valid = validate(schema, object, name, strict=True)
        self.assertTrue(valid == "")

        object = {"a": "AA"}
        valid = validate(schema, object, name, strict=True)
        self.assertFalse(valid == "")


if __name__ == "__main__":
    unittest.main()
