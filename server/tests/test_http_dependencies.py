"""Test HTTP dependency resolution and request-context assembly."""

import unittest
from types import SimpleNamespace
from unittest import mock

from starlette.datastructures import State
from starlette.requests import Request

from fishtest.actiondb import ActionDb
from fishtest.http.cookie_session import CookieSession
from fishtest.http.dependencies import (
    DependencyNotInitializedError,
    get_actiondb,
    get_request_context,
    get_rundb,
    get_userdb,
    get_workerdb,
)
from fishtest.rundb import RunDb
from fishtest.userdb import UserDb
from fishtest.workerdb import WorkerDb


def _instance_without_init(cls):
    return cls.__new__(cls)


def _request_with_state(
    *, state: object | None = None, app_state: object | None = None
) -> Request:
    request = Request({"type": "http", "headers": [], "state": {}})
    request.scope["app"] = SimpleNamespace(state=State())

    if state is not None:
        for key, value in vars(state).items():
            setattr(request.state, key, value)

    if app_state is not None:
        for key, value in vars(app_state).items():
            setattr(request.app.state, key, value)

    return request


class DependencyContractTests(unittest.TestCase):
    def test_request_state_dependency_overrides_app_state(self):
        request_rundb = _instance_without_init(RunDb)
        fallback_rundb = _instance_without_init(RunDb)
        request = _request_with_state(
            state=SimpleNamespace(rundb=request_rundb),
            app_state=SimpleNamespace(rundb=fallback_rundb),
        )

        self.assertIs(get_rundb(request), request_rundb)

    def test_missing_dependency_raises_named_error(self):
        request = _request_with_state()

        with self.assertRaises(DependencyNotInitializedError) as raised:
            get_userdb(request)

        self.assertEqual(str(raised.exception), "UserDb not initialized")

    def test_request_context_collects_session_user_and_handles(self):
        rundb = _instance_without_init(RunDb)
        userdb = _instance_without_init(UserDb)
        actiondb = _instance_without_init(ActionDb)
        workerdb = _instance_without_init(WorkerDb)
        request = _request_with_state(
            state=SimpleNamespace(
                rundb=rundb,
                userdb=userdb,
                actiondb=actiondb,
                workerdb=workerdb,
            )
        )
        session = CookieSession(data={})

        with (
            mock.patch("fishtest.http.dependencies.load_session", return_value=session),
            mock.patch(
                "fishtest.http.dependencies.authenticated_user",
                return_value="ContextUser",
            ),
        ):
            context = get_request_context(request)

        self.assertIs(context["session"], session)
        self.assertEqual(context["user"], "ContextUser")
        self.assertIs(context["rundb"], rundb)
        self.assertIs(context["userdb"], userdb)
        self.assertIs(context["actiondb"], actiondb)
        self.assertIs(context["workerdb"], workerdb)

    def test_dependency_helpers_read_each_domain_handle(self):
        request = _request_with_state(
            state=SimpleNamespace(
                actiondb=_instance_without_init(ActionDb),
                workerdb=_instance_without_init(WorkerDb),
            ),
            app_state=SimpleNamespace(userdb=_instance_without_init(UserDb)),
        )

        self.assertIsInstance(get_actiondb(request), ActionDb)
        self.assertIsInstance(get_workerdb(request), WorkerDb)
        self.assertIsInstance(get_userdb(request), UserDb)
