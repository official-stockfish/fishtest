import base64
import copy
from datetime import datetime

import requests
from fishtest.stats.stat_util import SPRT_elo
from fishtest.util import optional_key, validate, worker_name
from fishtest.views import del_tasks
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPFound,
    HTTPUnauthorized,
    exception_response,
)
from pyramid.response import Response
from pyramid.view import exception_view_config, view_config, view_defaults

WORKER_VERSION = 133

flag_cache = {}


def validate_request(request):
    schema = {
        "password": str,
        optional_key("run_id"): str,
        optional_key("task_id"): int,
        optional_key("pgn"): str,
        optional_key("message"): str,
        optional_key("ARCH"): str,
        optional_key("nps"): float,
        "worker_info": {
            "uname": str,
            "architecture": [str, str],
            "concurrency": int,
            "max_memory": int,
            "min_threads": int,
            "username": str,
            "version": str,
            "gcc_version": str,
            "unique_key": str,
            optional_key("rate"): {"limit": int, "remaining": int},
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
    error = validate(schema, request, "request")
    if error != "":
        print(error, flush=True)
        raise HTTPBadRequest({"error": error})


def strip_run(run):
    run = copy.deepcopy(run)
    if "tasks" in run:
        del run["tasks"]
    if "bad_tasks" in run:
        del run["bad_tasks"]
    if "spsa" in run["args"] and "param_history" in run["args"]["spsa"]:
        del run["args"]["spsa"]["param_history"]
    run["_id"] = str(run["_id"])
    run["start_time"] = str(run["start_time"])
    run["last_updated"] = str(run["last_updated"])
    return run


@exception_view_config(HTTPUnauthorized)
def authentication_failed(error, request):
    response = Response(json_body=error.detail)
    response.status_int = 401
    return response


@exception_view_config(HTTPBadRequest)
def badrequest_failed(error, request):
    response = Response(json_body=error.detail)
    response.status_int = 400
    return response


@view_defaults(renderer="json")
class ApiView(object):
    """All API endpoints that require authentication are used by workers"""

    def __init__(self, request):
        self.request = request

    def validate_request(self, api):
        error = ""
        exception = HTTPBadRequest
        for _ in range(1):  # trick to be able to use break
            # is the request valid json?
            try:
                self.request_body = self.request.json_body
            except:
                error = "request is not json encoded"
                break

            # Is the request syntactically correct?
            # Raises HTTPBadRequest() in case of error.
            validate_request(self.request_body)

            # is the supplied password correct?
            token = self.request.userdb.authenticate(
                self.request_body["worker_info"]["username"],
                self.request_body["password"],
            )
            if "error" in token:
                error = "Invalid password for user: {}".format(
                    self.request_body["worker_info"]["username"],
                )
                exception = HTTPUnauthorized
                break

            # is a supplied run_id correct?
            self.__run = None
            if "run_id" in self.request_body:
                run_id = self.request_body["run_id"]
                run = self.request.rundb.get_run(run_id)
                if run is None:
                    error = "Invalid run_id: {}".format(run_id)
                    break

                self.__run = run

            # if a task_id is present then there should be a run_id, and
            # the unique_key should correspond to the unique_key of the
            # task
            self.__task = None
            if "task_id" in self.request_body:
                task_id = self.request_body["task_id"]
                if "run_id" not in self.request_body:
                    error = "The request has a task_id but no run_id"
                    break

                if task_id < 0 or task_id >= len(run["tasks"]):
                    error = "Invalid task_id {} for run_id {}".format(task_id, run_id)
                    break

                task = run["tasks"][task_id]
                unique_key = self.request_body["worker_info"]["unique_key"]
                if unique_key != task["worker_info"]["unique_key"]:
                    error = "Invalid unique key {} for task_id {} for run_id {}".format(
                        unique_key, task_id, run_id
                    )
                    break

                self.__task = task

        if error != "":
            error = "{}: {}".format(api, error)
            print(error, flush=True)
            raise exception({"error": error})

    def get_username(self):
        return self.request_body["worker_info"]["username"]

    def get_unique_key(self):
        return self.request_body["worker_info"]["unique_key"]

    def run(self):
        if self.__run is not None:
            return self.__run

        error = "Missing run_id"
        print(error, flush=True)
        raise HTTPBadRequest({"error": error})

    def run_id(self):
        if "run_id" in self.request_body:
            return self.request_body["run_id"]

        error = "Missing run_id"
        print(error, flush=True)
        raise HTTPBadRequest({"error": error})

    def task(self):
        if self.__task is not None:
            return self.__task

        error = "Missing task_id"
        print(error, flush=True)
        raise HTTPBadRequest({"error": error})

    def task_id(self):
        if "task_id" in self.request_body:
            return self.request_body["task_id"]

        error = "Missing task_id"
        print(error, flush=True)
        raise HTTPBadRequest({"error": error})

    def worker_info(self):
        worker_info = self.request_body["worker_info"]
        worker_info["remote_addr"] = self.request.remote_addr
        flag = self.get_flag()
        if flag:
            worker_info["country_code"] = flag
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
        stats = self.request.json_body.get("stats", {})
        return stats

    def spsa(self):
        spsa = self.request_body.get("spsa", {})
        return spsa

    def get_flag(self):
        ip = self.request.remote_addr
        if ip in flag_cache:
            return flag_cache.get(ip, None)  # Handle race condition on "del"
        # concurrent invocations get None, race condition is not an issue
        flag_cache[ip] = None
        result = self.request.userdb.flag_cache.find_one({"ip": ip})
        if result:
            flag_cache[ip] = result["country_code"]
            return result["country_code"]
        try:
            # Get country flag from worker IP address
            FLAG_HOST = "https://freegeoip.app/json/"
            r = requests.get(FLAG_HOST + self.request.remote_addr, timeout=1.0)
            if r.status_code == 200:
                country_code = r.json()["country_code"]
                self.request.userdb.flag_cache.insert_one(
                    {
                        "ip": ip,
                        "country_code": country_code,
                        "geoip_checked_at": datetime.utcnow(),
                    }
                )
                flag_cache[ip] = country_code
                return country_code
            raise ConnectionError("flag server failed")
        except:
            del flag_cache[ip]
            print("Failed GeoIP check for {}".format(ip))
            return None

    @view_config(route_name="api_active_runs")
    def active_runs(self):
        active = {}
        for run in self.request.rundb.get_unfinished_runs():
            active[str(run["_id"])] = strip_run(run)
        return active

    @view_config(route_name="api_get_run")
    def get_run(self):
        run = self.request.rundb.get_run(self.request.matchdict["id"])
        return strip_run(run)

    @view_config(route_name="api_get_elo")
    def get_elo(self):
        run = self.request.rundb.get_run(self.request.matchdict["id"])
        results = run["results"]
        if "sprt" not in run["args"]:
            return {}
        sprt = run["args"].get("sprt").copy()
        elo_model = sprt.get("elo_model", "BayesElo")
        alpha = sprt["alpha"]
        beta = sprt["beta"]
        elo0 = sprt["elo0"]
        elo1 = sprt["elo1"]
        sprt["elo_model"] = elo_model
        a = SPRT_elo(
            results, alpha=alpha, beta=beta, elo0=elo0, elo1=elo1, elo_model=elo_model
        )
        run = strip_run(run)
        run["elo"] = a
        run["args"]["sprt"] = sprt
        return run

    @view_config(route_name="api_request_task")
    def request_task(self):
        self.validate_request("/api/request_task")
        worker_info = self.worker_info()
        result = self.request.rundb.request_task(worker_info)
        if "task_waiting" in result:
            return result

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
        return result

    @view_config(route_name="api_update_task")
    def update_task(self):
        self.validate_request("/api/update_task")
        return self.request.rundb.update_task(
            run_id=self.run_id(),
            task_id=self.task_id(),
            stats=self.stats(),
            nps=self.request_body.get("nps", 0),
            ARCH=self.request_body.get("ARCH", "?"),
            spsa=self.spsa(),
            username=self.get_username(),
            unique_key=self.get_unique_key(),
        )

    @view_config(route_name="api_failed_task")
    def failed_task(self):
        self.validate_request("/api/failed_task")
        return self.request.rundb.failed_task(
            self.run_id(), self.task_id(), self.message()
        )

    @view_config(route_name="api_upload_pgn")
    def upload_pgn(self):
        self.validate_request("/api/upload_pgn")
        return self.request.rundb.upload_pgn(
            run_id="{}-{}".format(self.run_id(), self.task_id()),
            pgn_zip=base64.b64decode(self.request_body["pgn"]),
        )

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
            run["stop_reason"] = "task_id: {}, worker: {}, reason: '{}' {}".format(
                self.task_id(),
                self.worker_name(),
                self.message()[:1024],
                " (not authorized)" if error != "" else "",
            )
            run_ = del_tasks(run)
            self.request.actiondb.stop_run(self.get_username(), run_)
            if error == "":
                run["finished"] = True
                run["failed"] = True
                self.request.rundb.stop_run(self.run_id())
            else:
                task = self.task()
                task["active"] = False
                self.request.rundb.buffer(run, True)

        if error != "":
            error = "{}: {}".format(api, error)
            print(error, flush=True)
            return {"error": error}
        return {}

    @view_config(route_name="api_request_version")
    def request_version(self):
        self.validate_request("/api/request_version")
        return {"version": WORKER_VERSION}

    @view_config(route_name="api_beat")
    def beat(self):
        self.validate_request("/api/beat")
        run = self.run()
        task = self.task()
        task["last_updated"] = datetime.utcnow()
        self.request.rundb.buffer(run, False)
        return self.worker_name()

    @view_config(route_name="api_request_spsa")
    def request_spsa(self):
        self.validate_request("/api/request_spsa")
        return self.request.rundb.request_spsa(self.run_id(), self.task_id())
