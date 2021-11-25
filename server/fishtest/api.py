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

WORKER_VERSION = 132

flag_cache = {}


def validate_request(request):
    schema = {
        "password": str,
        optional_key("username"): str,
        optional_key("run_id"): str,
        optional_key("task_id"): int,
        optional_key("unique_key"): str,
        optional_key("pgn"): str,
        optional_key("message"): str,
        optional_key("ARCH"): str,
        optional_key("nps"): float,
        optional_key("worker_info"): {
            "uname": str,
            "architecture": [str, str],
            "concurrency": int,
            "max_memory": int,
            "min_threads": int,
            "username": str,
            "version": str,
            "gcc_version": str,
            "unique_key": str,
            "rate": {"limit": int, "remaining": int},
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

    def require_authentication(self):
        token = self.request.userdb.authenticate(
            self.get_username(), self.request.json_body["password"]
        )
        if "error" in token:
            raise HTTPUnauthorized(token)

    def validate_request(self):
        try:
            request = self.request.json_body
        except:
            raise HTTPBadRequest({"error": "request is not json encoded"})
        validate_request(request)

    def get_username(self):
        try:
            return self.__username
        except:
            pass
        try:
            if "username" in self.request.json_body:
                username = str(self.request.json_body["username"])
            else:
                username = str(self.request.json_body["worker_info"]["username"])
        except:
            error = "No username"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})
        self.__username = username
        return username

    def get_unique_key(self):
        try:
            return self.__unique_key
        except:
            pass
        try:
            if "unique_key" in self.request.json_body:
                unique_key = str(self.request.json_body["unique_key"])
            else:
                unique_key = str(self.request.json_body["worker_info"]["unique_key"])
        except:
            error = "No unique key"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})

        task = self.task()
        if unique_key != task["worker_info"]["unique_key"]:
            error = "Invalid unique key: {}".format(unique_key)
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})
        self.__unique_key = unique_key
        return unique_key

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

    def __run_(self):
        try:
            return self.__run_id, self.__run
        except:
            pass

        run_id = self.request.json_body["run_id"]
        if run_id is None:
            error = "No run_id"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})
        run = self.request.rundb.get_run(run_id)
        if run is None:
            error = "Invalid run_id: {}".format(run_id)
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})
        self.__run_id, self.__run = run_id, run
        return run_id, run

    def run(self):
        return self.__run_()[1]

    def run_id(self):
        return self.__run_()[0]

    def __task_(self):
        try:
            return self.__task_id, self.__task
        except:
            pass
        task_id = self.request.json_body.get("task_id")
        if task_id is None:
            error = "No task_id"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})

        run = self.run()
        if task_id < 0 or task_id >= len(run["tasks"]):
            error = "Invalid task_id: {}".format(task_id)
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})

        task = run["tasks"][task_id]

        self.__task_id, self.__task = task_id, task
        return task_id, task

    def task(self):
        return self.__task_()[1]

    def task_id(self, allow_none=False):
        return self.__task_()[0]

    def worker_info(self, allow_server=False):
        try:
            return self.__worker_info
        except:
            pass
        if "worker_info" in self.request.json_body:
            worker_info = self.request.json_body["worker_info"]
            worker_info["remote_addr"] = self.request.remote_addr
            flag = self.get_flag()
            if flag:
                worker_info["country_code"] = flag
            self.__worker_info = worker_info
        elif allow_server:
            worker_info = self.task().get("worker_info")
        else:
            error = "No worker_info"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})

        return worker_info

    def worker_name(self):
        try:
            return self.__worker_name
        except:
            pass
        worker_info = self.worker_info(allow_server=True)
        try:
            worker_name_ = worker_name(worker_info)
        except:
            error = "Unable to construct worker name"
            print(error, flush=True)
            raise HTTPBadRequest({"error": error})
        self.__worker_name = worker_name_
        return worker_name_

    def cpu_hours(self):
        username = self.get_username()
        user = self.request.userdb.user_cache.find_one({"username": username})
        if not user:
            return -1
        else:
            return user["cpu_hours"]

    def message(self):
        message = str(self.request.json_body.get("message"))
        return message

    def stats(self):
        stats = self.request.json_body.get("stats", {})
        return stats

    def spsa(self):
        spsa = self.request.json_body.get("spsa", {})
        return spsa

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
        self.validate_request()
        self.require_authentication()
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
        self.validate_request()
        self.require_authentication()
        return self.request.rundb.update_task(
            run_id=self.run_id(),
            task_id=self.task_id(),
            stats=self.stats(),
            nps=self.request.json_body.get("nps", 0),
            ARCH=self.request.json_body.get("ARCH", "?"),
            spsa=self.spsa(),
            username=self.get_username(),
            unique_key=self.get_unique_key(),
        )

    @view_config(route_name="api_failed_task")
    def failed_task(self):
        self.validate_request()
        self.require_authentication()
        self.get_unique_key()  # validation
        return self.request.rundb.failed_task(
            self.run_id(), self.task_id(), self.message()
        )

    @view_config(route_name="api_upload_pgn")
    def upload_pgn(self):
        self.validate_request()
        self.require_authentication()
        return self.request.rundb.upload_pgn(
            run_id="{}-{}".format(self.run_id(), self.task_id()),
            pgn_zip=base64.b64decode(self.request.json_body["pgn"]),
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
        self.validate_request()
        self.require_authentication()
        self.get_unique_key()  # validation
        error = ""
        if self.cpu_hours() < 1000:
            error = "api_stop_run: User {} has too few games to stop a run".format(
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
            print(error, flush=True)
            return {"error": error}
        return {}

    @view_config(route_name="api_request_version")
    def request_version(self):
        self.validate_request()
        self.require_authentication()
        return {"version": WORKER_VERSION}

    @view_config(route_name="api_beat")
    def beat(self):
        self.validate_request()
        self.require_authentication()
        run = self.run()
        task = self.task()
        task["last_updated"] = datetime.utcnow()
        self.request.rundb.buffer(run, False)
        return self.worker_name()

    @view_config(route_name="api_request_spsa")
    def request_spsa(self):
        self.validate_request()
        self.require_authentication()
        self.get_unique_key()  # validation
        return self.request.rundb.request_spsa(self.run_id(), self.task_id())
