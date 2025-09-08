import base64
import hashlib

from pyramid.path import AssetResolver
from pyramid.static import QueryStringCacheBuster


def setup_routes(config):
    config.add_static_view("static", "static", cache_max_age=3600)

    config.add_cache_buster(
        "static/", FileHashCacheBuster(package="fishtest", base_path="static/")
    )

    config.add_route("home", "/")
    config.add_route("login", "/login")
    config.add_route("nn_upload", "/upload")
    config.add_route("logout", "/logout")
    config.add_route("signup", "/signup")
    config.add_route("user", "/user/{username}")
    config.add_route("profile", "/user")
    config.add_route("user_management", "/user_management")
    config.add_route("contributors", "/contributors")
    config.add_route("contributors_monthly", "/contributors/monthly")
    config.add_route("actions", "/actions")
    config.add_route("nns", "/nns")
    config.add_route("sprt_calc", "/sprt_calc")
    config.add_route("rate_limits", "/rate_limits")
    config.add_route("workers", "/workers/{worker_name}")

    config.add_route("tests", "/tests")
    config.add_route("tests_machines", "/tests/machines")
    config.add_route("tests_finished", "/tests/finished")
    config.add_route("tests_run", "/tests/run")
    config.add_route("tests_view", "/tests/view/{id}")
    config.add_route("tests_tasks", "/tests/tasks/{id}")
    config.add_route("tests_user", "/tests/user/{username}")
    config.add_route("tests_stats", "/tests/stats/{id}")
    config.add_route("tests_live_elo", "/tests/live_elo/{id}")

    # Tests - actions
    config.add_route("tests_modify", "/tests/modify")
    config.add_route("tests_delete", "/tests/delete")
    config.add_route("tests_stop", "/tests/stop")
    config.add_route("tests_approve", "/tests/approve")
    config.add_route("tests_purge", "/tests/purge")

    # WorkerApi
    config.add_route("api_request_task", "/api/request_task")
    config.add_route("api_update_task", "/api/update_task")
    config.add_route("api_failed_task", "/api/failed_task")
    config.add_route("api_stop_run", "/api/stop_run")
    config.add_route("api_request_version", "/api/request_version")
    config.add_route("api_beat", "/api/beat")
    config.add_route("api_request_spsa", "/api/request_spsa")
    config.add_route("api_worker_log", "/api/worker_log")

    # UserApi
    config.add_route("api_rate_limit", "/api/rate_limit")
    config.add_route("api_active_runs", "/api/active_runs")
    config.add_route("api_finished_runs", "/api/finished_runs")
    config.add_route("api_get_run", "/api/get_run/{id}")
    config.add_route("api_get_task", "/api/get_task/{id}/{task_id}")
    config.add_route("api_upload_pgn", "/api/upload_pgn")
    config.add_route("api_download_pgn", "/api/pgn/{id}")
    config.add_route("api_download_run_pgns", "/api/run_pgns/{id}")
    config.add_route("api_download_nn", "/api/nn/{id}")
    config.add_route("api_get_elo", "/api/get_elo/{id}")
    config.add_route("api_actions", "/api/actions")
    config.add_route("api_calc_elo", "/api/calc_elo")


class FileHashCacheBuster(QueryStringCacheBuster):
    def __init__(self, package, base_path, param="x") -> None:
        super().__init__(param)
        self.asset_resolver = AssetResolver(package)
        self.base_path = base_path
        self.token_cache = {}

    def tokenize(self, request, pathspec, kw):
        cached = self.token_cache.get(pathspec)
        if cached:
            return cached

        token = self._hash_asset(self._resolve_asset(pathspec))
        self.token_cache[pathspec] = token

        return token

    def _resolve_asset(self, pathspec):
        return self.asset_resolver.resolve(self.base_path + pathspec)

    def _hash_asset(self, asset):
        content = asset.stream().read()
        return base64.b64encode(hashlib.sha384(content).digest()).decode("utf8")
