import unittest
from datetime import UTC, datetime

import test_support
from vtjson import ValidationError

from fishtest.http.settings import HTMX_INPUT_CHANGED_DELAY_MS


def show(mc):
    exception = mc.exception
    print(f"{exception.__class__.__name__}: {mc.exception!s}")


class TestNN(unittest.TestCase):
    def setUp(self):
        self.rundb = test_support.get_rundb()
        self.name = "nn-0000000000a0.nnue"
        self.user = "user00"
        self.first_test = datetime(2024, 1, 1, tzinfo=UTC)
        self.last_test = datetime(2024, 3, 24, tzinfo=UTC)
        self.last_test_old = datetime(2023, 3, 24, tzinfo=UTC)
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


class TestNNHttp(unittest.TestCase):
    def setUp(self):
        self.rundb = test_support.get_rundb()
        self.client = test_support.make_test_client(
            rundb=self.rundb,
            include_api=False,
            include_views=True,
        )

    def tearDown(self):
        self.rundb.nndb.delete_many({"name": {"$regex": "^nn-h16-"}})

    def test_nns_form_uses_htmx_triggered_search_without_script_block(self):
        response = self.client.get("/nns")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="search_nn"', response.text)
        expected_trigger = (
            'hx-trigger="submit, input changed delay:'
            f"{HTMX_INPUT_CHANGED_DELAY_MS}ms from:#network_name"
        )
        self.assertIn(
            expected_trigger,
            response.text,
        )
        self.assertNotIn(">Search</button>", response.text)
        self.assertIn('type="search"', response.text)
        self.assertIn("hx-on::before-request", response.text)
        self.assertIn("path=/;", response.text)
        self.assertNotIn('getElementById("search_nn").addEventListener', response.text)

    def test_nns_server_side_search_hx_fragment(self):
        hit_name = "nn-h16-hit.nnue"
        miss_name = "nn-h16-miss.nnue"
        docs = [
            {
                "name": hit_name,
                "user": "H16Uploader",
                "downloads": 8,
                "is_master": True,
            },
            {
                "name": miss_name,
                "user": "OtherUploader",
                "downloads": 1,
                "is_master": False,
            },
        ]
        self.rundb.nndb.insert_many(docs)
        response = self.client.get(
            "/nns?network_name=h16-hit&user=h16uploader&master_only=1",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(hit_name, response.text)
        self.assertNotIn(miss_name, response.text)
        self.assertNotIn("<!doctype html>", response.text.lower())

    def test_nns_view_all_hides_pagination_and_shows_switch_back(self):
        docs = [
            {
                "name": f"nn-h16-view-all-{idx:03d}.nnue",
                "user": "H16ViewAll",
                "downloads": idx,
                "is_master": idx % 2 == 0,
            }
            for idx in range(60)
        ]
        self.rundb.nndb.insert_many(docs)
        response = self.client.get("/nns?view=all")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Show paginated", response.text)
        self.assertNotIn("?page=2", response.text)

    def test_nns_table_has_server_sortable_headers_and_active_arrow(self):
        response = self.client.get("/nns?sort=time&order=desc")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="nns_table"', response.text)
        self.assertIn('aria-sort="descending"', response.text)
        self.assertIn('class="sort-indicator"', response.text)
        self.assertIn("?sort=name&order=asc", response.text)

    def test_nns_sort_by_downloads_asc(self):
        docs = [
            {
                "name": "nn-h16-sort-a.nnue",
                "user": "SortUser",
                "downloads": 9,
                "is_master": False,
            },
            {
                "name": "nn-h16-sort-b.nnue",
                "user": "SortUser",
                "downloads": 1,
                "is_master": False,
            },
        ]
        self.rundb.nndb.insert_many(docs)
        response = self.client.get("/nns?sort=downloads&order=asc&view=all")
        self.assertEqual(response.status_code, 200)
        first_idx = response.text.find("nn-h16-sort-b.nnue")
        second_idx = response.text.find("nn-h16-sort-a.nnue")
        self.assertGreaterEqual(first_idx, 0)
        self.assertGreaterEqual(second_idx, 0)
        self.assertLess(first_idx, second_idx)

    def test_nns_hx_fragment_includes_view_toggle_for_state_transitions(self):
        docs = [
            {
                "name": f"nn-h16-fragment-toggle-{idx:03d}.nnue",
                "user": "H16Fragment",
                "downloads": idx,
                "is_master": idx % 2 == 0,
            }
            for idx in range(60)
        ]
        self.rundb.nndb.insert_many(docs)

        paged_fragment = self.client.get("/nns", headers={"HX-Request": "true"})
        self.assertEqual(paged_fragment.status_code, 200)
        self.assertIn("Show all", paged_fragment.text)

        all_fragment = self.client.get(
            "/nns?view=all",
            headers={"HX-Request": "true"},
        )
        self.assertEqual(all_fragment.status_code, 200)
        self.assertIn("Show paginated", all_fragment.text)

    def test_nns_links_preserve_encoded_filters(self):
        response = self.client.get(
            "/nns?network_name=nn-h16%2Fspace+name&user=H16+User%2FQA&view=all"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("network_name=nn-h16%2Fspace+name", response.text)
        self.assertIn("user=H16+User%2FQA", response.text)
