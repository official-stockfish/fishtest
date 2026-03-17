"""Test run-creation and run-mutation helper contracts."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from starlette.responses import RedirectResponse

from fishtest.views_run import (
    _RUN_MODIFY_MAX_AGE_DAYS,
    can_modify_run,
    del_tasks,
    is_same_user,
    parse_spsa_params,
    sanitize_options,
    validate_form,
    validate_modify,
)

BASE_TIME = datetime(2026, 3, 17, tzinfo=UTC)
BASE_THREADS = "1"
BASE_PRIORITY = "10"
BASE_THROUGHPUT = "100"
BASE_NUM_GAMES = "200"
BASE_TC = "10+0.1"
BASE_REPO = "https://github.com/official-stockfish/Stockfish"
BASE_SIGNATURE = "123456"
BASE_SHA = "a" * 40
NEW_SHA = "b" * 40
SPSA_FIELD_COUNT = 6


class _SessionStub:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def flash(self, message: str, level: str = "info") -> None:
        self.messages.append((message, level))


class _UserDbStub:
    def __init__(self, user: dict[str, object]) -> None:
        self._user = dict(user)
        self.saved_users: list[dict[str, object]] = []

    def get_user(self, _username: str) -> dict[str, object]:
        return dict(self._user)

    def save_user(self, user: dict[str, object]) -> None:
        self.saved_users.append(dict(user))


class _RunDbStub:
    def __init__(self) -> None:
        self.pt_info = {"pt_branch": "pt-master", "pt_version": "PT"}
        self.ltc_lower_bound = 9999

    def get_nn(self, _net_name: str):
        return None


class _RequestStub:
    def __init__(
        self,
        *,
        post_data: dict[str, str],
        authenticated_userid: str = "RunOwner",
        can_approve: bool = False,
    ) -> None:
        self.POST = dict(post_data)
        self.authenticated_userid = authenticated_userid
        self.session = _SessionStub()
        self.userdb = _UserDbStub(
            {
                "username": authenticated_userid,
                "tests_repo": BASE_REPO,
                "registration_time": BASE_TIME - timedelta(days=365),
            }
        )
        self.rundb = _RunDbStub()
        self._can_approve = can_approve

    def has_permission(self, permission: str) -> bool:
        return permission == "approve_run" and self._can_approve


def _valid_post_data() -> dict[str, str]:
    return {
        "base-branch": "dev",
        "test-branch": "feature",
        "tc": BASE_TC,
        "new_tc": BASE_TC,
        "book": "book.pgn",
        "book-depth": "8",
        "base-signature": BASE_SIGNATURE,
        "test-signature": BASE_SIGNATURE,
        "base-options": "Threads=1 Hash=16",
        "new-options": "Threads=1 Hash=16",
        "tests-repo": BASE_REPO,
        "run-info": "Feature validation",
        "arch-filter": "x86-64",
        "compiler": "g++",
        "stop_rule": "numgames",
        "threads": BASE_THREADS,
        "priority": BASE_PRIORITY,
        "throughput": BASE_THROUGHPUT,
        "num-games": BASE_NUM_GAMES,
        "odds": "off",
        "checkbox-compiler": "off",
        "checkbox-arch-filter": "off",
    }


class SpsaParsingTests(unittest.TestCase):
    def test_parse_spsa_params_returns_structured_params(self):
        spsa = {
            "raw_params": "Tempo,1,0,2,0.5,0.1",
            "num_iter": 100,
            "gamma": 0.101,
            "A": 25,
            "alpha": 0.602,
        }

        params = parse_spsa_params(spsa)

        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "Tempo")
        self.assertEqual(params[0]["start"], 1.0)

    def test_parse_spsa_params_rejects_wrong_field_count(self):
        spsa = {
            "raw_params": "Tempo,1,0,2,0.5",
            "num_iter": 100,
            "gamma": 0.101,
            "A": 25,
            "alpha": 0.602,
        }

        with self.assertRaisesRegex(ValueError, str(SPSA_FIELD_COUNT)):
            parse_spsa_params(spsa)


class SanitizeOptionsTests(unittest.TestCase):
    def test_sanitize_options_normalizes_spacing(self):
        options = sanitize_options("Threads=1   Hash=16")

        self.assertEqual(options, "Threads=1 Hash=16")

    def test_sanitize_options_rejects_non_ascii(self):
        with self.assertRaisesRegex(ValueError, "ASCII"):
            sanitize_options("Hash=16 Eval=caf\u00e9")


class ValidateModifyTests(unittest.TestCase):
    def test_validate_modify_rejects_old_run(self):
        request = _RequestStub(post_data=_valid_post_data())
        old_run = {
            "start_time": BASE_TIME - timedelta(days=_RUN_MODIFY_MAX_AGE_DAYS + 1),
            "args": {"num_games": 200},
        }

        response = validate_modify(request, old_run)

        self.assertIsInstance(response, RedirectResponse)
        self.assertEqual(request.session.messages[0][1], "error")

    def test_validate_modify_accepts_current_run(self):
        request = _RequestStub(post_data=_valid_post_data())
        current_run = {
            "start_time": BASE_TIME,
            "args": {"num_games": 400},
        }

        response = validate_modify(request, current_run)

        self.assertIsNone(response)


class ValidateFormTests(unittest.TestCase):
    def test_validate_form_numgames_path_returns_normalized_data(self):
        request = _RequestStub(post_data=_valid_post_data())

        with (
            mock.patch(
                "fishtest.views_run.gh.normalize_repo", side_effect=lambda repo: repo
            ),
            mock.patch(
                "fishtest.views_run.gh.parse_repo",
                return_value=("official-stockfish", "Stockfish"),
            ),
            mock.patch("fishtest.views_run.gh.get_master_repo", return_value=BASE_REPO),
            mock.patch(
                "fishtest.views_run.get_sha",
                side_effect=[(BASE_SHA, "base"), (NEW_SHA, "new")],
            ),
            mock.patch("fishtest.views_run.get_nets", return_value=[]),
        ):
            data = validate_form(request)

        self.assertEqual(data["new_tc"], BASE_TC)
        self.assertEqual(data["num_games"], int(BASE_NUM_GAMES))
        self.assertNotIn("compiler", data)
        self.assertNotIn("arch_filter", data)
        self.assertEqual(data["resolved_base"], BASE_SHA)
        self.assertEqual(data["resolved_new"], NEW_SHA)

    def test_validate_form_rejects_invalid_arch_regex(self):
        post_data = _valid_post_data()
        post_data["checkbox-arch-filter"] = "on"
        post_data["arch-filter"] = "["
        request = _RequestStub(post_data=post_data)

        with (
            mock.patch(
                "fishtest.views_run.gh.normalize_repo", side_effect=lambda repo: repo
            ),
            mock.patch(
                "fishtest.views_run.gh.parse_repo",
                return_value=("official-stockfish", "Stockfish"),
            ),
            mock.patch("fishtest.views_run.gh.get_master_repo", return_value=BASE_REPO),
        ):
            with self.assertRaisesRegex(ValueError, "Invalid arch filter"):
                validate_form(request)


class RunPermissionTests(unittest.TestCase):
    def test_del_tasks_returns_deep_copy_without_tasks(self):
        original_run = {
            "args": {"username": "RunOwner"},
            "tasks": [{"worker_info": {"username": "worker"}}],
        }

        cloned_run = del_tasks(original_run)
        cloned_run["args"]["username"] = "Changed"

        self.assertNotIn("tasks", cloned_run)
        self.assertEqual(original_run["args"]["username"], "RunOwner")

    def test_run_permission_helpers_follow_owner_or_approver_contract(self):
        run = {"args": {"username": "RunOwner"}}
        owner_request = _RequestStub(post_data=_valid_post_data())
        approver_request = _RequestStub(
            post_data=_valid_post_data(),
            authenticated_userid="Approver",
            can_approve=True,
        )

        self.assertTrue(is_same_user(owner_request, run))
        self.assertFalse(is_same_user(approver_request, run))
        self.assertTrue(can_modify_run(owner_request, run))
        self.assertTrue(can_modify_run(approver_request, run))
