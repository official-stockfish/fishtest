"""Test `/tests/machines` helper contracts."""

import unittest
from datetime import UTC, datetime, timedelta

from fishtest.http.settings import PERSISTENT_UI_COOKIE_MAX_AGE_SECONDS
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
            authenticated_username="MachineOwner",
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
        owner = "MachineOwner"
        machines = [
            _machine_doc(0, username=owner, uname="Linux"),
            _machine_doc(1, username="OtherUser", uname="Windows 11"),
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
                f"max-age={PERSISTENT_UI_COOKIE_MAX_AGE_SECONDS}",
                cookie_header,
            )
