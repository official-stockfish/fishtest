import base64
import copy
from datetime import datetime

from fishtest.stats.stat_util import SPRT_elo
from fishtest.util import optional_key, union, validate, worker_name
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPFound,
    HTTPUnauthorized,
    exception_response,
)
from pyramid.response import Response
from pyramid.view import exception_view_config, view_config, view_defaults

"""
Important note
==============

All apis that are relying on get_run() should be served from a single
Fishtest instance.

If other instances need information about runs they should query the
db directly. However this information may be slightly outdated, depending
on how frequently the main instance flushes its run cache.
"""

WORKER_VERSION = 203


def validate_request(request):
    schema = {
        "password": str,
        optional_key("run_id"): str,
        optional_key("task_id"): int,
        optional_key("pgn"): str,
        optional_key("message"): str,
        "worker_info": {
            "uname": str,
            "architecture": [str, str],
            "concurrency": int,
            "max_memory": int,
            "min_threads": int,
            "username": str,
            "version": int,
            "python_version": [int, int, int],
            "gcc_version": [int, int, int],
            "compiler": union("g++", "clang++"),
            "unique_key": str,
            "modified": bool,
            "near_github_api_limit": bool,
            "ARCH": str,
            "nps": float,
        },
        optional_key("spsa"): {
            "wins": int,
            "losses": int,
            "draws": int,
            "num_games": int,
        },
        optional_key("stats"): {
            "wins": int,
            "losses": int,
            "draws": int,
            "crashes": int,
            "time_losses": int,
            "pentanomial": [int, int, int, int, int],
        },
    }
    return validate(schema, request, "request")


# Avoids exposing sensitive data about the workers to the client and skips some heavy data.
def strip_run(run):
    # a deep copy, avoiding copies of a few large lists.
    stripped = {}
    for k1, v1 in run.items():
        if k1 in ["tasks", "bad_tasks"]:
            stripped[k1] = []
        elif k1 == "args":
            stripped[k1] = {}
            for k2, v2 in v1.items():
                if k2 == "spsa":
                    stripped[k1][k2] = {
                        k3: [] if k3 == "param_history" else copy.deepcopy(v3)
                        for k3, v3 in v2.items()
                    }
                else:
                    stripped[k1][k2] = copy.deepcopy(v2)
        else:
            stripped[k1] = copy.deepcopy(v1)

    # and some string conversions
    stripped["_id"] = str(run["_id"])
    stripped["start_time"] = str(run["start_time"])
    stripped["last_updated"] = str(run["last_updated"])

    return stripped


@exception_view_config(HTTPBadRequest)
def badrequest_failed(error, request):
    response = Response(json_body=error.detail)
    response.status_int = 400
    return response


@exception_view_config(HTTPUnauthorized)
def authentication_failed(error, request):
    response = Response(json_body=error.detail)
    response.status_int = 401
    return response


@view_defaults(renderer="json")
class ApiView(object):
    """All API endpoints that require authentication are used by workers"""

    def __init__(self, request):
        self.request = request

    def handle_error(self, error, exception=HTTPBadRequest):
        if error != "":
            error = "{}: {}".format(self.__api, error)
            print(error, flush=True)
            raise exception(self.add_time({"error": error}))

    def validate_username_password(self, api):
        self.__t0 = datetime.utcnow()
        self.__api = api
        # is the request valid json?
        try:
            self.request_body = self.request.json_body
        except:
            self.handle_error("request is not json encoded")

        # Is the request syntactically correct?
        schema = {"password": str, "worker_info": {"username": str}}
        self.handle_error(validate(schema, self.request_body, "request"))

        # is the supplied password correct?
        token = self.request.userdb.authenticate(
            self.request_body["worker_info"]["username"],
            self.request_body["password"],
        )
        if "error" in token:
            self.handle_error(
                token["error"],
                exception=HTTPUnauthorized,
            )

    def validate_request(self, api):
        self.__run = None
        self.__task = None

        # Preliminary validation.
        self.validate_username_password(api)

        # Is the request syntactically correct?
        self.handle_error(validate_request(self.request_body))

        # is a supplied run_id correct?
        if "run_id" in self.request_body:
            run_id = self.request_body["run_id"]
            run = self.request.rundb.get_run(run_id)
            if run is None:
                self.handle_error("Invalid run_id: {}".format(run_id))
            self.__run = run

        # if a task_id is present then there should be a run_id, and
        # the unique_key should correspond to the unique_key of the
        # task
        if "task_id" in self.request_body:
            task_id = self.request_body["task_id"]
            if "run_id" not in self.request_body:
                self.handle_error("The request has a task_id but no run_id")

            if task_id < 0 or task_id >= len(run["tasks"]):
                self.handle_error(
                    "Invalid task_id {} for run_id {}".format(task_id, run_id)
                )

            task = run["tasks"][task_id]
            unique_key = self.request_body["worker_info"]["unique_key"]
            if unique_key != task["worker_info"]["unique_key"]:
                self.handle_error(
                    "Invalid unique key {} for task_id {} for run_id {}".format(
                        unique_key, task_id, run_id
                    )
                )
            self.__task = task

    def add_time(self, result):
        result["duration"] = (datetime.utcnow() - self.__t0).total_seconds()
        return result

    def get_username(self):
        return self.request_body["worker_info"]["username"]

    def run(self):
        if self.__run is not None:
            return self.__run

        self.handle_error("Missing run_id")

    def run_id(self):
        if "run_id" in self.request_body:
            return self.request_body["run_id"]

        self.handle_error("Missing run_id")

    def task(self):
        if self.__task is not None:
            return self.__task

        self.handle_error("Missing task_id")

    def task_id(self):
        if "task_id" in self.request_body:
            return self.request_body["task_id"]

        self.handle_error("Missing task_id")

    def pgn(self):
        if "pgn" in self.request_body:
            return self.request_body["pgn"]

        self.handle_error("Missing pgn content")

    def worker_info(self):
        worker_info = self.request_body["worker_info"]
        worker_info["remote_addr"] = self.request.remote_addr
        worker_info["country_code"] = self.get_country_code()
        return worker_info

    def worker_name(self):
        return worker_name(self.worker_info())

    def cpu_hours(self):
        username = self.get_username()
        user = self.request.userdb.user_cache.find_one({"username": username})
        if not user:
            return -1
        else:
            return user["cpu_hours"]

    def message(self):
        return self.request_body.get("message", "")

    def stats(self):
        return self.request_body.get("stats", {})

    def spsa(self):
        return self.request_body.get("spsa", {})

    def get_country_code(self):
        country_code = self.request.headers.get("X-Country-Code")
        return "?" if country_code in (None, "ZZ") else country_code

    @view_config(route_name="api_active_runs")
    def active_runs(self):
        runs = self.request.rundb.runs.find(
            {"finished": False},
            {"tasks": 0, "bad_tasks": 0, "args.spsa.param_history": 0},
        )
        active = {}
        for run in runs:
            # some string conversions
            run["_id"] = str(run["_id"])
            run["start_time"] = str(run["start_time"])
            run["last_updated"] = str(run["last_updated"])
            active[str(run["_id"])] = run
        return active

    @view_config(route_name="api_actions")
    def actions(self):
        try:
            query = self.request.json_body
            actions = self.request.rundb.db["actions"].find(query).limit(200)
        except:
            actions = []
        ret = []
        for action in actions:
            action["_id"] = str(action["_id"])
            ret.append(action)
        self.request.response.headers["access-control-allow-origin"] = "*"
        self.request.response.headers["access-control-allow-headers"] = "content-type"
        return ret

    @view_config(route_name="api_get_run")
    def get_run(self):
        run = self.request.rundb.get_run(self.request.matchdict["id"])
        if run is None:
            raise exception_response(404)
        return strip_run(run)

    @view_config(route_name="api_get_task")
    def get_task(self):
        try:
            run = self.request.rundb.get_run(self.request.matchdict["id"])
            task_id = self.request.matchdict["task_id"]
            if task_id.endswith("bad"):
                task_id = int(task_id[:-3])
                task = copy.deepcopy(run["bad_tasks"][task_id])
            else:
                task_id = int(task_id)
                task = copy.deepcopy(run["tasks"][task_id])
        except:
            raise exception_response(404)
        if "worker_info" in task:
            worker_info = task["worker_info"]
            # Do not reveal the unique_key.
            if "unique_key" in worker_info:
                unique_key = worker_info["unique_key"]
                worker_info["unique_key"] = unique_key[0:8] + "..."
            # Do not reveal remote_addr.
            if "remote_addr" in worker_info:
                worker_info["remote_addr"] = "?.?.?.?"
        if "last_updated" in task:
            # json does not know about datetime
            task["last_updated"] = str(task["last_updated"])
        if "residual" in task:
            # json does not know about infinity
            if task["residual"] == float("inf"):
                task["residual"] = "inf"
        return task

    @view_config(route_name="api_get_elo")
    def get_elo(self):
        run = self.request.rundb.get_run(self.request.matchdict["id"])
        if run is None:
            raise exception_response(404)
        results = run["results"]
        if "sprt" not in run["args"]:
            return {}
        run = strip_run(run)
        sprt = run["args"].get("sprt")
        elo_model = sprt.get("elo_model", "BayesElo")
        alpha = sprt["alpha"]
        beta = sprt["beta"]
        elo0 = sprt["elo0"]
        elo1 = sprt["elo1"]
        sprt["elo_model"] = elo_model
        a = SPRT_elo(
            results, alpha=alpha, beta=beta, elo0=elo0, elo1=elo1, elo_model=elo_model
        )
        run["elo"] = a
        return run

    @view_config(route_name="api_request_task")
    def request_task(self):
        self.validate_request("/api/request_task")
        worker_info = self.worker_info()
        result = self.request.rundb.request_task(worker_info)
        if "task_waiting" in result:
            return self.add_time(result)

        # Strip the run of unneccesary information
        run = result["run"]
        min_run = {"_id": str(run["_id"]), "args": run["args"], "tasks": []}
        if int(str(worker_info["version"]).split(":")[0]) > 64:
            task = run["tasks"][result["task_id"]]
            min_task = {"num_games": task["num_games"]}
            if "stats" in task:
                min_task["stats"] = task["stats"]
            min_task["start"] = task["start"]
            min_run["my_task"] = min_task
        else:
            for task in run["tasks"]:
                min_task = {"num_games": task["num_games"]}
                if "stats" in task:
                    min_task["stats"] = task["stats"]
                min_run["tasks"].append(min_task)

        result["run"] = min_run
        return self.add_time(result)

    @view_config(route_name="api_update_task")
    def update_task(self):
        self.validate_request("/api/update_task")
        result = self.request.rundb.update_task(
            worker_info=self.worker_info(),
            run_id=self.run_id(),
            task_id=self.task_id(),
            stats=self.stats(),
            spsa=self.spsa(),
        )
        return self.add_time(result)

    @view_config(route_name="api_failed_task")
    def failed_task(self):
        self.validate_request("/api/failed_task")
        result = self.request.rundb.failed_task(
            self.run_id(), self.task_id(), self.message()
        )
        return self.add_time(result)

    @view_config(route_name="api_upload_pgn")
    def upload_pgn(self):
        self.validate_request("/api/upload_pgn")
        result = self.request.rundb.upload_pgn(
            run_id="{}-{}".format(self.run_id(), self.task_id()),
            pgn_zip=base64.b64decode(self.pgn()),
        )
        return self.add_time(result)

    @view_config(route_name="api_download_pgn", renderer="string")
    def download_pgn(self):
        pgn = self.request.rundb.get_pgn(self.request.matchdict["id"])
        if pgn is None:
            raise exception_response(404)
        if ".pgn" in self.request.matchdict["id"]:
            self.request.response.content_type = "application/x-chess-pgn"
        return pgn

    @view_config(route_name="api_download_pgn_100")
    def download_pgn_100(self):
        skip = int(self.request.matchdict["skip"])
        urls = self.request.rundb.get_pgn_100(skip)
        if urls is None:
            raise exception_response(404)
        return urls

    @view_config(route_name="api_download_nn")
    def download_nn(self):
        nn = self.request.rundb.get_nn(self.request.matchdict["id"])
        if nn is None:
            raise exception_response(404)
        # self.request.response.content_type = 'application/x-chess-nnue'
        # self.request.response.body = zlib.decompress(nn['nn'])
        # return self.request.response
        return HTTPFound(
            "https://data.stockfishchess.org/nn/" + self.request.matchdict["id"]
        )

    @view_config(route_name="api_stop_run")
    def stop_run(self):
        api = "/api/stop_run"
        self.validate_request(api)
        error = ""
        if self.cpu_hours() < 1000:
            error = "User {} has too few games to stop a run".format(
                self.get_username()
            )
        with self.request.rundb.active_run_lock(self.run_id()):
            run = self.run()
            message = self.message()[:1024] + (
                " (not authorized)" if error != "" else ""
            )
            self.request.actiondb.stop_run(
                username=self.get_username(),
                run=run,
                task_id=self.task_id(),
                message=message,
            )
            if error == "":
                run["finished"] = True
                run["failed"] = True
                self.request.rundb.stop_run(self.run_id())
            else:
                task = self.task()
                task["active"] = False
                self.request.rundb.buffer(run, True)

        self.handle_error(error, exception=HTTPUnauthorized)
        return self.add_time({})

    @view_config(route_name="api_request_version")
    def request_version(self):
        # By being mor lax here we can be more strict
        # elsewhere since the worker will upgrade.
        self.validate_username_password("/api/request_version")
        return self.add_time({"version": WORKER_VERSION})

    @view_config(route_name="api_beat")
    def beat(self):
        self.validate_request("/api/beat")
        run = self.run()
        task = self.task()
        task["last_updated"] = datetime.utcnow()
        self.request.rundb.buffer(run, False)
        return self.add_time({})

    @view_config(route_name="api_request_spsa")
    def request_spsa(self):
        self.validate_request("/api/request_spsa")
        result = self.request.rundb.request_spsa(self.run_id(), self.task_id())
        return self.add_time(result)
