import os
import signal
import sys
import threading
import traceback

from fishtest import helpers
from fishtest.routes import setup_routes
from fishtest.rundb import RunDb
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.events import ApplicationCreated, BeforeRender, NewRequest
from pyramid.httpexceptions import HTTPFound, HTTPServiceUnavailable
from pyramid.security import forget
from pyramid.session import SignedCookieSessionFactory


def thread_stack_dump(sig, frame):
    for th in threading.enumerate():
        print("=================== ", th, " ======================", flush=True)
        try:
            traceback.print_stack(sys._current_frames()[th.ident])
        except Exception:
            print("Failed to print traceback, the thread is probably gone", flush=True)


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""

    # Register handler, will list the stack traces of all active threads
    # trigger with: kill -USR1 <pid>
    signal.signal(signal.SIGUSR1, thread_stack_dump)

    session_factory = SignedCookieSessionFactory("fishtest")
    config = Configurator(
        settings=settings,
        session_factory=session_factory,
        root_factory="fishtest.models.RootFactory",
    )
    config.include("pyramid_mako")
    config.set_default_csrf_options(require_csrf=False)

    port = int(settings.get("fishtest.port", -1))
    primary_port = int(settings.get("fishtest.primary_port", -1))
    # If the port number cannot be determined like during unit tests or CI,
    # assume the instance is primary for backward compatibility.
    is_primary_instance = port == primary_port

    rundb = RunDb(port=port, is_primary_instance=is_primary_instance)

    def add_rundb(event):
        event.request.rundb = rundb
        event.request.userdb = rundb.userdb
        event.request.actiondb = rundb.actiondb
        event.request.workerdb = rundb.workerdb

    def add_renderer_globals(event):
        event["h"] = helpers

    def check_blocked_user(event):
        request = event.request
        if request.authenticated_userid is not None:
            auth_user_id = request.authenticated_userid
            if is_user_blocked(auth_user_id, request.userdb):
                session = request.session
                headers = forget(request)
                session.invalidate()
                raise HTTPFound(location=request.route_url("tests"), headers=headers)

    def check_shutdown(event):
        if rundb._shutdown:
            raise HTTPServiceUnavailable()

    def is_user_blocked(auth_user_id, userdb):
        blocked_users = userdb.get_blocked()
        for user in blocked_users:
            if user["username"] == auth_user_id and user["blocked"]:
                return True
        return False

    def init_rundb(event):
        # We do not want to do the following in the constructor of rundb since
        # it writes to the db and starts the flush timer.
        if rundb.is_primary_instance():
            rundb.update_aggregated_data()
            # We install signal handlers when all cache-sensitive code in the
            # main thread is finished. In that way we can safely use
            # locks in the signal handlers (which also run in the main thread).
            signal.signal(signal.SIGINT, rundb.exit_run)
            signal.signal(signal.SIGTERM, rundb.exit_run)
            rundb.schedule_tasks()

    def set_default_base_url(event):
        if not rundb._base_url_set:
            rundb.base_url = f"{event.request.scheme}://{event.request.host}"
            rundb._base_url_set = True

    config.add_subscriber(add_rundb, NewRequest)
    config.add_subscriber(check_shutdown, NewRequest)
    config.add_subscriber(add_renderer_globals, BeforeRender)
    config.add_subscriber(check_blocked_user, NewRequest)
    config.add_subscriber(init_rundb, ApplicationCreated)
    config.add_subscriber(set_default_base_url, NewRequest)

    # Authentication
    def group_finder(username, request):
        return request.userdb.get_user_groups(username)

    secret = os.environ.get("FISHTEST_AUTHENTICATION_SECRET", "")
    if not secret:
        print(
            "FISHTEST_AUTHENTICATION_SECRET is missing, using an insecure default for authentication.",
            flush=True,
        )
    config.set_authentication_policy(
        AuthTktAuthenticationPolicy(
            secret, callback=group_finder, hashalg="sha512", http_only=True
        )
    )
    config.set_authorization_policy(ACLAuthorizationPolicy())

    setup_routes(config)

    config.scan()
    return config.make_wsgi_app()
