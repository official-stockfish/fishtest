import unittest
from datetime import datetime, timezone

from util import get_rundb
from vtjson import ValidationError


def show(mc):
    exception = mc.exception
    print(f"{exception.__class__.__name__}: {str(mc.exception)}")


class TestNN(unittest.TestCase):
    def setUp(self):
        self.rundb = get_rundb()
        self.name = "nn-0000000000a0.nnue"
        self.user = "user00"
        self.first_test = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.last_test = datetime(2024, 3, 24, tzinfo=timezone.utc)
        self.last_test_old = datetime(2023, 3, 24, tzinfo=timezone.utc)
        self.run_id = "64e74776a170cb1f26fa3930"

    def tearDown(self):
        self.rundb.nndb.delete_many({})

    def test_nn(self):
        self.rundb.upload_nn(self.user, self.name)
        net = self.rundb.get_nn(self.name)
        del net["_id"]
        self.assertEqual(net, {"user": self.user, "name": self.name, "downloads": 0})
        self.rundb.increment_nn_downloads(self.name)
        net = self.rundb.get_nn(self.name)
        del net["_id"]
        self.assertEqual(net, {"user": self.user, "name": self.name, "downloads": 1})
        with self.assertRaises(ValidationError) as mc:
            new_net = {
                "user": self.user,
                "name": self.name,
                "downloads": 0,
                "first_test": {"date": self.first_test, "id": self.run_id},
                "is_master": True,
            }
            self.rundb.update_nn(new_net)
        show(mc)
        with self.assertRaises(ValidationError) as mc:
            new_net = {
                "user": self.user,
                "name": self.name,
                "downloads": 0,
                "is_master": True,
            }
            self.rundb.update_nn(new_net)
        show(mc)
        with self.assertRaises(ValidationError) as mc:
            new_net = {
                "user": self.user,
                "name": self.name,
                "downloads": 0,
                "first_test": {"date": self.first_test, "id": self.run_id},
                "is_master": True,
                "last_test": {"date": self.last_test_old, "id": self.run_id},
            }
            self.rundb.update_nn(new_net)
        show(mc)
        new_net = {
            "user": self.user,
            "name": self.name,
            "downloads": 0,
            "first_test": {"date": self.first_test, "id": self.run_id},
            "is_master": True,
            "last_test": {"date": self.last_test, "id": self.run_id},
        }
        self.rundb.update_nn(new_net)
        net = self.rundb.get_nn(self.name)
        del net["_id"]
        new_net["downloads"] = 1
        self.assertEqual(net, new_net)
