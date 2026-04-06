"""Test `/tests/machines` helper contracts."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from ui_user_test_case import UiUserTestCase

from fishtest.http.settings import UI_STATE_COOKIE_MAX_AGE_SECONDS
from fishtest.views_machines import (
    _MACHINES_PAGE_SIZE,
    _filtered_machine_count,
    _machine_filter_state,
    _normalize_machine_row,
    _workers_count_label,
    tests_machines,
)

BASE_TIME = datetime(2026, 3, 17, tzinfo=UTC)
BASE_NPS = 2_500_000
BASE_MEMORY_MB = 4096
BASE_COMPILER_VERSION = [13, 2, 0]
BASE_PYTHON_VERSION = [3, 12, 1]
BASE_WORKER_VERSION = 321
TARGET_PAGE_NUMBER = 2
EXTRA_MACHINE_COUNT = 2
EXPECTED_MACHINE_COOKIE_COUNT = 6


def _machine_doc(
    index: int,
    *,
    username: str | None = None,
    uname: str = "Linux",
    compiler: str = "g++",
    run_tag: str | None = None,
) -> dict[str, object]:
    machine_username = username or f"MachineUser{index:03d}"
    machine_run_tag = run_tag or f"branch-{index:03d}"
    return {
        "username": machine_username,
        "country_code": "us",
        "concurrency": index + 1,
        "unique_key": f"worker-{index:03d}-abcd1234",
        "nps": BASE_NPS + index,
        "max_memory": BASE_MEMORY_MB,
        "uname": uname,
        "worker_arch": "x86-64",
        "gcc_version": list(BASE_COMPILER_VERSION),
        "compiler": compiler,
        "python_version": list(BASE_PYTHON_VERSION),
        "version": BASE_WORKER_VERSION,
        "modified": False,
        "task_id": index,
        "last_updated": BASE_TIME - timedelta(seconds=index),
        "run": {
            "_id": f"run-{index:03d}",
            "args": {"new_tag": machine_run_tag},
        },
    }


class _RunDbStub:
    def __init__(self, machines: list[dict[str, object]]) -> None:
        self._machines = machines

    def get_machines(self) -> list[dict[str, object]]:
        return list(self._machines)


class _RequestStub:
    def __init__(
        self,
        *,
        machines: list[dict[str, object]],
        params: dict[str, str] | None = None,
        authenticated_userid: str | None = None,
    ) -> None:
        self.params = params or {}
        self.authenticated_userid = authenticated_userid
        self.response_headerlist: list[tuple[str, str]] = []
        self.rundb = _RunDbStub(machines)


class MachineFilterStateTests(unittest.TestCase):
    def test_machine_filter_state_trims_query_and_requires_user_for_my_workers(self):
        filters = _machine_filter_state(
            {"q": "  linux  ", "my_workers": "1"},
            authenticated_username=None,
        )

        self.assertEqual(filters["query_filter"], "linux")
        self.assertFalse(filters["my_workers"])
        self.assertTrue(filters["filters_active"])

    def test_machine_filter_state_decodes_cookie_values(self):
        filters = _machine_filter_state(
            {"machines_q": "Linux%20worker", "machines_my_workers": "1"},
            authenticated_username="TestMachineOwner",
            use_cookies=True,
            query_key="machines_q",
            my_workers_key="machines_my_workers",
        )

        self.assertEqual(filters["query_filter"], "Linux worker")
        self.assertTrue(filters["my_workers"])
        self.assertTrue(filters["filters_active"])


class MachineRowTests(unittest.TestCase):
    def test_normalize_machine_row_builds_labels_and_urls(self):
        machine = _machine_doc(7, run_tag="very-long-feature-branch-name")

        row = _normalize_machine_row(machine)

        self.assertEqual(row["worker_short"], "worker")
        self.assertEqual(row["compiler_label"], "g++ 13.2.0")
        self.assertEqual(row["python_label"], "3.12.1")
        self.assertEqual(row["version_label"], str(BASE_WORKER_VERSION))
        self.assertTrue(str(row["worker_url"]).startswith("/workers/"))
        self.assertTrue(str(row["run_url"]).startswith("/tests/view/run-007"))
        self.assertIn("/7", str(row["run_label"]))

    def test_filtered_machine_count_applies_query_and_my_workers(self):
        owner = "TestMachineOwner"
        machines = [
            _machine_doc(0, username=owner, uname="Linux"),
            _machine_doc(1, username="TestPeerWorkerUser", uname="Windows 11"),
            _machine_doc(2, username=owner, uname="Linux"),
        ]
        request = _RequestStub(machines=machines, authenticated_userid=owner)

        filtered_count = _filtered_machine_count(
            request,
            query_filter="linux",
            my_workers=True,
            authenticated_username=owner,
        )

        self.assertEqual(filtered_count, 2)

    def test_workers_count_label_reflects_filter_state(self):
        total_workers = 5
        filtered_workers = 2

        self.assertEqual(_workers_count_label(total_workers), "Workers - 5")
        self.assertEqual(
            _workers_count_label(
                total_workers,
                query_filter="linux",
                filtered_count=filtered_workers,
            ),
            "Workers - 5 (2)",
        )


class TestsMachinesEntryPointTests(unittest.TestCase):
    def test_tests_machines_sets_prefixed_page_urls_and_persistent_cookies(self):
        machines = [
            _machine_doc(index)
            for index in range(_MACHINES_PAGE_SIZE + EXTRA_MACHINE_COUNT)
        ]
        request = _RequestStub(
            machines=machines,
            params={"sort": "machine", "page": str(TARGET_PAGE_NUMBER)},
        )

        result = tests_machines(request)

        self.assertEqual(result["current_page"], TARGET_PAGE_NUMBER)
        self.assertEqual(len(result["machines"]), EXTRA_MACHINE_COUNT)
        self.assertTrue(result["pages"][0]["url"].startswith("/tests/machines?"))
        self.assertEqual(
            len(request.response_headerlist), EXPECTED_MACHINE_COOKIE_COUNT
        )
        cookie_headers = [
            value for key, value in request.response_headerlist if key == "Set-Cookie"
        ]
        self.assertEqual(len(cookie_headers), EXPECTED_MACHINE_COOKIE_COUNT)
        for cookie_header in cookie_headers:
            self.assertIn(
                f"max-age={UI_STATE_COOKIE_MAX_AGE_SECONDS}",
                cookie_header,
            )


class TestMachinesViews(UiUserTestCase):
    username = "TestMachinesUser"

    def test_tests_machines_server_sort_and_pagination(self):
        now = datetime.now(UTC)

        def machine_doc(idx):
            return {
                "username": f"PageUser{idx:03d}",
                "country_code": "us",
                "concurrency": 1,
                "unique_key": f"ukey-{idx:03d}-abcd",
                "nps": 2_000_000 + idx,
                "max_memory": 2048,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 123,
                "modified": False,
                "task_id": idx,
                "last_updated": now - timedelta(seconds=idx),
                "run": {
                    "_id": f"run-{idx:03d}",
                    "args": {"new_tag": f"branch-{idx:03d}"},
                },
            }

        docs = [machine_doc(idx) for idx in range(_MACHINES_PAGE_SIZE + 5)]
        with patch.object(self.rundb, "get_machines", return_value=docs):
            response = self.client.get("/tests/machines?sort=machine&page=2")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="machines_table"', response.text)
        self.assertIn('hx-disinherit="hx-include"', response.text)
        self.assertIn('hx-params="none"', response.text)
        self.assertIn(f"PageUser{_MACHINES_PAGE_SIZE + 4:03d}", response.text)
        self.assertNotIn("PageUser000", response.text)
        self.assertIn("/tests/machines?page=1&amp;sort=machine", response.text)

    def test_tests_machines_compiler_and_python_sort_are_version_aware(self):
        now = datetime.now(UTC)

        docs = [
            {
                "username": "CompPyUserA",
                "country_code": "us",
                "concurrency": 1,
                "unique_key": "comp-a-0000",
                "nps": 2_000_000,
                "max_memory": 2048,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [20, 1, 8],
                "compiler": "clang++",
                "python_version": [3, 11, 0],
                "version": 300,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-comp-a", "args": {"new_tag": "main"}},
            },
            {
                "username": "CompPyUserB",
                "country_code": "us",
                "concurrency": 1,
                "unique_key": "comp-b-0000",
                "nps": 2_000_000,
                "max_memory": 2048,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [17, 0, 6],
                "compiler": "clang++",
                "python_version": [3, 8, 20],
                "version": 300,
                "modified": False,
                "task_id": 2,
                "last_updated": now,
                "run": {"_id": "run-comp-b", "args": {"new_tag": "main"}},
            },
            {
                "username": "CompPyUserC",
                "country_code": "us",
                "concurrency": 1,
                "unique_key": "comp-c-0000",
                "nps": 2_000_000,
                "max_memory": 2048,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [18, 1, 8],
                "compiler": "clang++",
                "python_version": [3, 12, 12],
                "version": 300,
                "modified": False,
                "task_id": 3,
                "last_updated": now,
                "run": {"_id": "run-comp-c", "args": {"new_tag": "main"}},
            },
        ]

        with patch.object(self.rundb, "get_machines", return_value=docs):
            compiler_response = self.client.get(
                "/tests/machines?sort=compiler&order=asc"
            )
            python_response = self.client.get("/tests/machines?sort=python&order=asc")

        self.assertEqual(compiler_response.status_code, 200)
        self.assertLess(
            compiler_response.text.index("CompPyUserB"),
            compiler_response.text.index("CompPyUserC"),
        )
        self.assertLess(
            compiler_response.text.index("CompPyUserC"),
            compiler_response.text.index("CompPyUserA"),
        )

        self.assertEqual(python_response.status_code, 200)
        self.assertLess(
            python_response.text.index("CompPyUserB"),
            python_response.text.index("CompPyUserA"),
        )
        self.assertLess(
            python_response.text.index("CompPyUserA"),
            python_response.text.index("CompPyUserC"),
        )

    def test_tests_machines_my_workers_and_query_filter(self):
        now = datetime.now(UTC)
        docs = [
            {
                "username": self.username,
                "country_code": "us",
                "concurrency": 2,
                "unique_key": "joekey-aaaa-bbbb",
                "nps": 2_500_000,
                "max_memory": 4096,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 100,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-joe", "args": {"new_tag": "main"}},
            },
            {
                "username": "TestPeerWorkerUser",
                "country_code": "it",
                "concurrency": 4,
                "unique_key": "otherkey-cccc-dddd",
                "nps": 3_000_000,
                "max_memory": 8192,
                "uname": "Windows 11",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "clang",
                "python_version": [3, 11, 0],
                "version": 101,
                "modified": False,
                "task_id": 2,
                "last_updated": now - timedelta(seconds=30),
                "run": {"_id": "run-other", "args": {"new_tag": "dev"}},
            },
        ]

        self._login_user()
        with patch.object(self.rundb, "get_machines", return_value=docs):
            response = self.client.get("/tests/machines?my_workers=1&q=linux")

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.username, response.text)
        self.assertNotIn("TestPeerWorkerUser", response.text)
        self.assertIn("Workers - 2 (1)", response.text)
        self.assertIn("my_workers=1", response.text)

        with patch.object(self.rundb, "get_machines", return_value=docs):
            compiler_filter_response = self.client.get("/tests/machines?q=clang")

        self.assertEqual(compiler_filter_response.status_code, 200)
        self.assertIn("TestPeerWorkerUser", compiler_filter_response.text)
        self.assertNotIn(self.username, compiler_filter_response.text)

    def test_tests_machines_workers_count_shows_total_and_filtered(self):
        now = datetime.now(UTC)
        docs = [
            {
                "username": self.username,
                "country_code": "us",
                "concurrency": 2,
                "unique_key": "joekey-aaaa-bbbb",
                "nps": 2_500_000,
                "max_memory": 4096,
                "uname": "Linux",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "g++",
                "python_version": [3, 12, 0],
                "version": 100,
                "modified": False,
                "task_id": 1,
                "last_updated": now,
                "run": {"_id": "run-joe", "args": {"new_tag": "main"}},
            },
            {
                "username": "TestPeerWorkerUser",
                "country_code": "it",
                "concurrency": 4,
                "unique_key": "otherkey-cccc-dddd",
                "nps": 3_000_000,
                "max_memory": 8192,
                "uname": "Windows 11",
                "worker_arch": "x86-64",
                "gcc_version": [13, 2, 0],
                "compiler": "clang",
                "python_version": [3, 11, 0],
                "version": 101,
                "modified": False,
                "task_id": 2,
                "last_updated": now - timedelta(seconds=30),
                "run": {"_id": "run-other", "args": {"new_tag": "dev"}},
            },
        ]

        with patch.object(self.rundb, "get_machines", return_value=docs):
            response_unfiltered = self.client.get("/tests/machines")
            response_filtered = self.client.get("/tests/machines?q=windows")

        self.assertEqual(response_unfiltered.status_code, 200)
        self.assertIn("Workers - 2", response_unfiltered.text)

        self.assertEqual(response_filtered.status_code, 200)
        self.assertIn("Workers - 2 (1)", response_filtered.text)
