import base64
import copy
import io
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import fishtest.github_api as gh
from fishtest import jwt_token
from fishtest.schemas import api_access_schema, api_schema, gzip_data
from fishtest.stats.stat_util import SPRT_elo, get_elo
from fishtest.util import strip_run, worker_name
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPFound,
    HTTPNotFound,
    HTTPUnauthorized,
)
from pyramid.response import FileIter, Response
from pyramid.view import exception_view_config, view_config, view_defaults
from vtjson import ValidationError, validate

"""
Important note
==============

APIs hosted on the primary Fishtest instance have read and write access
to the `run_cache` via `rundb.get_run()` and `rundb.buffer()`

APIs hosted on secondary instances have read access to the `run`
from the database via `rundb.get_run()`. However, they should not
attempt to write to `run_cache` using `rundb.buffer()`.

Proper configuration of `nginx` is crucial for this, and should be done
according to the route/URL mapping defined in `__init__.py`.
"""

WORKER_VERSION = 306


@exception_view_config(HTTPException)
def exception_handler(error, request):
    if request.exception.code < 400:
        return request.exception
    if not isinstance(error.detail, dict):
        return request.exception
    response = Response(json_body=error.detail)
    response.status_int = request.exception.code
    return response


class GenericApi:
    def __init__(self, request):
        self.request = request
        self.__t0 = datetime.now(UTC)

    def timestamp(self):
        return self.__t0

    def add_time(self, result):
        result["duration"] = (datetime.now(UTC) - self.timestamp()).total_seconds()
        return result

    def handle_error(self, error, exception=HTTPBadRequest):
        if error != "":
            full_url = self.request.route_url(
                self.request.matched_route.name, **self.request.matchdict
            )
            api = urlparse(full_url).path
            error = f"{api}: {error}"
            print(error, flush=True)
            raise exception(self.add_time({"error": error}))


@view_defaults(renderer="json", request_method="POST")
class WorkerApi(GenericApi):
    """All API endpoints that require authentication are used by workers"""

    def __init__(self, request):
        super().__init__(request)
        # is the request valid json?
        try:
            self.request_body = request.json_body
        except Exception:
            self.handle_error("request is not json encoded")

    def validate_auth(self):
        # Is the request syntactically correct?
        try:
            validate(api_access_schema, self.request_body, "request")
        except ValidationError as e:
            self.handle_error(str(e))

        if "jwt" in self.request_body:
            self.validate_jwt()
            self._auth_method = "jwt"
        else:
            self.validate_password()
            self._auth_method = "password"

    def validate_password(self):
        token = self.request.userdb.authenticate(
            self.request_body["worker_info"]["username"],
            self.request_body["password"],
        )
        if "error" in token:
            self.handle_error(token["error"], exception=HTTPUnauthorized)

    def validate_jwt(self):
        username = self.request_body["worker_info"]["username"]
        token = self.request_body["jwt"]
        try:
            payload = jwt_token.decode_token(token)
        except jwt_token.JwtError as e:
            self.handle_error(str(e), exception=HTTPUnauthorized)
            return
        if payload.get("sub") != username:
            self.handle_error(
                "Auth token does not match username", exception=HTTPUnauthorized
            )
        user = self.request.userdb.get_user(username)
        if user is None:
            self.handle_error(
                "Unknown user: {}".format(username), exception=HTTPUnauthorized
            )
        if user.get("blocked"):
            self.handle_error(
                "Account blocked for user: {}".format(username),
                exception=HTTPUnauthorized,
            )
        if user.get("pending"):
            self.handle_error(
                "Account pending for user: {}".format(username),
                exception=HTTPUnauthorized,
            )

    def validate_request(self):
        """
        This function will load the run from the cache or the db,
        depending on the type of instance it runs on (primary or
        secondary). If the request refers to a particular
        task then one needs to make sure that it has been saved
        to disk when invoking this function on a secondary instance.
        """
        self.__run = None
        self.__task = None

        # Preliminary validation.
        self.validate_auth()

        # Is the request syntactically correct?
        try:
            validate(api_schema, self.request_body, "request")
        except ValidationError as e:
            self.handle_error(str(e))

        # is a supplied run_id correct?
        if "run_id" in self.request_body:
            run_id = self.request_body["run_id"]
            run = self.request.rundb.get_run(run_id)
            if run is None:
                self.handle_error("Invalid run_id: {}".format(run_id))
            self.__run = run

        # if a task_id is present then the unique_key and username
        # should be correct

        if "task_id" in self.request_body:
            task_id = self.request_body["task_id"]

            if task_id < 0 or task_id >= len(run["tasks"]):
                self.handle_error(
                    "Invalid task_id {} for run_id {}".format(task_id, run_id)
                )

            task = run["tasks"][task_id]
            for key in ("unique_key", "username"):
                value_request = self.request_body["worker_info"][key]
                value_task = task["worker_info"][key]

                if value_request != value_task:
                    self.handle_error(
                        f"Invalid {key} for task {run_id}/{task_id}. From task: "
                        f"{value_task}. From request: {value_request}."
                    )

            self.__task = task

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
        if self.__task is None:
            worker_info["remote_addr"] = self.request.remote_addr
        else:
            worker_info["remote_addr"] = self.__task["worker_info"]["remote_addr"]
        worker_info["country_code"] = self.get_country_code()
        return worker_info

    def worker_name(self):
        return worker_name(self.worker_info())

    def cpu_hours(self):
        username = self.get_username()
        user = self.request.userdb.user_cache.find_one({"username": username})
        return -1 if user is None else user["cpu_hours"]

    def message(self):
        return self.request_body.get("message", "")

    def stats(self):
        return self.request_body.get("stats", {})

    def spsa(self):
        return self.request_body.get("spsa", {})

    def get_country_code(self):
        country_code = self.request.headers.get("X-Country-Code")
        return "?" if country_code in (None, "ZZ") else country_code

    @view_config(route_name="api_request_task")
    def request_task(self):
        self.validate_request()
        worker_info = self.worker_info()
        # rundb.request_task() needs this for an error message...
        worker_info["host_url"] = self.request.host_url
        result = self.request.rundb.request_task(worker_info)
        if "task_waiting" in result:
            return self.add_time(result)

        # Strip the run of unnecessary information
        run = result["run"]
        task = run["tasks"][result["task_id"]]
        min_task = {"num_games": task["num_games"], "start": task["start"]}
        if "stats" in task:
            min_task["stats"] = task["stats"]

        # Add book checksum
        args = copy.copy(run["args"])
        book = args["book"]
        books = self.request.rundb.books
        if book in books:
            args["book_sri"] = books[book]["sri"]

        min_run = {"_id": str(run["_id"]), "args": args, "my_task": min_task}
        result["run"] = min_run
        return self.add_time(result)

    @view_config(route_name="api_update_task")
    def update_task(self):
        self.validate_request()
        result = self.request.rundb.update_task(
            worker_info=self.worker_info(),
            run_id=self.run_id(),
            task_id=self.task_id(),
            stats=self.stats(),
            spsa_results=self.spsa(),
        )
        return self.add_time(result)

    @view_config(route_name="api_failed_task")
    def failed_task(self):
        self.validate_request()
        result = self.request.rundb.failed_task(
            self.run_id(), self.task_id(), self.message()
        )
        return self.add_time(result)

    @view_config(route_name="api_worker_log")
    def worker_log(self):
        self.validate_request()
        self.request.actiondb.log_message(
            username=self.get_username(),
            message=self.message(),
            worker=self.worker_name(),
        )
        return self.add_time({})

    @view_config(route_name="api_upload_pgn")
    def upload_pgn(self):
        self.validate_request()
        try:
            pgn_zip = base64.b64decode(self.pgn())
            validate(gzip_data, pgn_zip, "pgn")
        except Exception as e:
            self.handle_error(str(e))
        result = self.request.rundb.upload_pgn(
            run_id="{}-{}".format(self.run_id(), self.task_id()),
            pgn_zip=pgn_zip,
        )
        return self.add_time(result)

    @view_config(route_name="api_stop_run")
    def stop_run(self):
        self.validate_request()
        error = ""
        if self.cpu_hours() < 1000:
            error = "User {} has too few games to stop a run".format(
                self.get_username()
            )
        with self.request.rundb.active_run_lock(self.run_id()):
            run = self.run()
            if not run["finished"]:
                message = self.message()
                if error != "":
                    message = message + " (not authorized)"
                self.request.actiondb.stop_run(
                    username=self.get_username(),
                    run=run,
                    task_id=self.task_id(),
                    message=message,
                )
                if error == "":
                    run["failed"] = True
                    run["failures"] = run.get("failures", 0) + 1
                    self.request.rundb.stop_run(self.run_id())
                else:
                    self.request.rundb.set_inactive_task(self.task_id(), run)
            else:
                error = f"Run {self.run_id()} is already finished"
        self.handle_error(error, exception=HTTPUnauthorized)
        return self.add_time({})

    @view_config(route_name="api_request_version")
    def request_version(self):
        # By being more lax here, we can be more strict
        # elsewhere since the worker will upgrade.
        self.validate_auth()
        response = {"version": WORKER_VERSION}
        if getattr(self, "_auth_method", None) == "password":
            response["jwt"] = jwt_token.create_token(self.get_username())
        return self.add_time(response)

    @view_config(route_name="api_beat")
    def beat(self):
        self.validate_request()
        run = self.run()
        task = self.task()
        with self.request.rundb.active_run_lock(self.run_id()):
            if task["active"]:
                task["last_updated"] = datetime.now(UTC)
                self.request.rundb.buffer(run)
            return self.add_time({"task_alive": task["active"]})

    @view_config(route_name="api_request_spsa")
    def request_spsa(self):
        self.validate_request()
        result = self.request.rundb.spsa_handler.request_spsa_data(
            self.run_id(), self.task_id()
        )
        return self.add_time(result)


@view_defaults(renderer="json")
class UserApi(GenericApi):
    @view_config(route_name="api_rate_limit")
    def rate_limit(self):
        return gh.rate_limit()

    @view_config(route_name="api_active_runs")
    def active_runs(self):
        runs = self.request.rundb.runs.find(
            {"finished": False},
            {"tasks": 0, "bad_tasks": 0, "args.spsa.param_history": 0},
        )
        active = {}
        for run in runs:
            # some string conversions
            for key in ("_id", "start_time", "last_updated"):
                run[key] = str(run[key])
            active[str(run["_id"])] = run
        return active

    @view_config(route_name="api_finished_runs")
    def finished_runs(self):
        username = self.request.params.get("username", "")
        success_only = self.request.params.get("success_only", False)
        yellow_only = self.request.params.get("yellow_only", False)
        ltc_only = self.request.params.get("ltc_only", False)
        timestamp = self.request.params.get("timestamp", "")
        page_param = self.request.params.get("page", "")

        if page_param == "":
            self.handle_error("Please provide a Page number.")
        if not page_param.isdigit() or int(page_param) < 1:
            self.handle_error("Please provide a valid Page number.")
        page_idx = int(page_param) - 1
        page_size = 50

        last_updated = None
        if timestamp != "" and re.match(r"^\d{10}(\.\d+)?$", timestamp):
            last_updated = datetime.fromtimestamp(float(timestamp))
        elif timestamp != "":
            self.handle_error("Please provide a valid UNIX timestamp.")

        runs, num_finished = self.request.rundb.get_finished_runs(
            username=username,
            success_only=success_only,
            yellow_only=yellow_only,
            ltc_only=ltc_only,
            skip=page_idx * page_size,
            limit=page_size,
            last_updated=last_updated,
        )

        finished = {}
        for run in runs:
            # some string conversions
            for key in ("_id", "start_time", "last_updated"):
                run[key] = str(run[key])
            finished[str(run["_id"])] = run
        return finished

    @view_config(route_name="api_actions")
    def actions(self):
        try:
            query = self.request.json_body
            actions = self.request.rundb.db["actions"].find(query).limit(200)
        except Exception:
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
        run_id = self.request.matchdict["id"]
        run = self.request.rundb.get_run(run_id)
        if run is None:
            self.handle_error(
                f"The run {run_id} does not exist", exception=HTTPNotFound
            )
        self.request.response.headers["access-control-allow-origin"] = "*"
        self.request.response.headers["access-control-allow-headers"] = "content-type"
        return strip_run(run)

    @view_config(route_name="api_get_task")
    def get_task(self):
        try:
            run_id = self.request.matchdict["id"]
            run = self.request.rundb.get_run(run_id)
            task_id = self.request.matchdict["task_id"]
            if task_id.endswith("bad"):
                task_id = int(task_id[:-3])
                task = copy.deepcopy(run["bad_tasks"][task_id])
            else:
                task_id = int(task_id)
                task = copy.deepcopy(run["tasks"][task_id])
        except Exception:
            self.handle_error(
                f"The task {run_id}/{task_id} does not exist", exception=HTTPNotFound
            )
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
            if task.get("residual", None) == float("inf"):
                task["residual"] = "inf"
        if "spsa_params" in task:
            spsa_params = task["spsa_params"]
            if "packed_flips" in spsa_params:
                # json has no binary type
                spsa_params["packed_flips"] = list(spsa_params["packed_flips"])
        return task

    @view_config(route_name="api_get_elo")
    def get_elo(self):
        run_id = self.request.matchdict["id"]
        run = self.request.rundb.get_run(run_id)
        if run is None:
            self.handle_error(
                f"The run {run_id} does not exist", exception=HTTPNotFound
            )
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

    @view_config(route_name="api_calc_elo")
    def calc_elo(self):
        W = self.request.params.get("W")
        D = self.request.params.get("D")
        L = self.request.params.get("L")
        LL = self.request.params.get("LL")
        LD = self.request.params.get("LD")
        DDWL = self.request.params.get("DDWL")
        WD = self.request.params.get("WD")
        WW = self.request.params.get("WW")
        elo0 = self.request.params.get("elo0", "")
        elo1 = self.request.params.get("elo1", "")

        is_ptnml = all(
            value is not None and value.replace(".", "").replace("-", "").isdigit()
            for value in (LL, LD, DDWL, WD, WW)
        )

        is_ptnml = is_ptnml and all(int(value) >= 0 for value in (LL, LD, DDWL, WD, WW))

        is_wdl = not is_ptnml and all(
            value is not None and value.replace(".", "").replace("-", "").isdigit()
            for value in (W, D, L)
        )

        is_wdl = is_wdl and all(int(value) >= 0 for value in (W, D, L))

        if not is_ptnml and not is_wdl:
            self.handle_error(
                "Invalid or missing parameters. Please provide all values as valid numbers."
            )

        if is_ptnml:
            LL = int(LL)
            LD = int(LD)
            DDWL = int(DDWL)
            WD = int(WD)
            WW = int(WW)
            if (LL + LD + DDWL + WD + WW) * 2 > 2**32:
                self.handle_error("Number of games exceeds the limit.")
            if LL + LD + DDWL + WD + WW == 0:
                self.handle_error("No games to calculate Elo.")
            results = {
                "pentanomial": [LL, LD, DDWL, WD, WW],
            }
        if is_wdl:
            W = int(W)
            D = int(D)
            L = int(L)
            if W + D + L > 2**32:
                self.handle_error("Number of games exceeds the limit.")
            if W + D + L == 0:
                self.handle_error("No games to calculate Elo.")
            results = {
                "wins": W,
                "draws": D,
                "losses": L,
            }

        is_sprt = elo0 != "" and elo1 != ""

        if not is_sprt:  # fixed games
            if "pentanomial" in results:
                elo5, elo95_5, LOS5 = get_elo(results["pentanomial"])
                elo5_l = elo5 - elo95_5
                elo5_u = elo5 + elo95_5
                return {"elo": elo5, "ci": [elo5_l, elo5_u], "LOS": LOS5}
            else:
                WLD = [results["wins"], results["losses"], results["draws"]]
                elo3, elo95_3, LOS3 = get_elo([WLD[1], WLD[2], WLD[0]])
                elo3_l = elo3 - elo95_3
                elo3_u = elo3 + elo95_3
                return {"elo": elo3, "ci": [elo3_l, elo3_u], "LOS": LOS3}
        else:
            badEloValues = (
                not all(
                    value.replace(".", "").replace("-", "").isdigit()
                    for value in (elo0, elo1)
                )
                or float(elo1) < float(elo0) + 0.5
                or abs(float(elo0)) > 10
                or abs(float(elo1)) > 10
            )
            if badEloValues:
                self.handle_error("Bad elo0, and elo1 values.")

            elo_model = self.request.params.get("elo_model", "normalized")

            if elo_model not in ["BayesElo", "logistic", "normalized"]:
                self.handle_error(
                    "Valid Elo models are: BayesElo, logistic, and normalized."
                )

            elo0 = float(elo0)
            elo1 = float(elo1)
            alpha = 0.05
            beta = 0.05
            return SPRT_elo(
                results,
                alpha=alpha,
                beta=beta,
                elo0=elo0,
                elo1=elo1,
                elo_model=elo_model,
            )

    @view_config(route_name="api_download_pgn", renderer="string")
    def download_pgn(self):
        zip_name = self.request.matchdict["id"]
        run_id = zip_name.split(".")[0]  # strip .pgn
        pgn_zip, size = self.request.rundb.get_pgn(run_id)
        if pgn_zip is None:
            self.handle_error(f"No data found for {zip_name}", exception=HTTPNotFound)
        response = Response(content_type="application/gzip")
        response.app_iter = io.BytesIO(pgn_zip)
        response.headers["Content-Disposition"] = f'attachment; filename="{zip_name}"'
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(size)
        return response

    @view_config(route_name="api_download_run_pgns")
    def download_run_pgns(self):
        pgns_name = self.request.matchdict["id"]
        match = re.match(r"^([a-zA-Z0-9]+)\.pgn\.gz$", pgns_name)
        if not match:
            self.handle_error(
                f"Invalid filename format for {pgns_name}", exception=HTTPBadRequest
            )
        run_id = match.group(1)
        pgns_reader, total_size = self.request.rundb.get_run_pgns(run_id)
        if pgns_reader is None:
            self.handle_error(f"No data found for {pgns_name}", exception=HTTPNotFound)
        response = Response(content_type="application/gzip")
        response.app_iter = FileIter(pgns_reader)
        response.headers["Content-Disposition"] = f'attachment; filename="{pgns_name}"'
        response.headers["Content-Length"] = str(total_size)
        return response

    @view_config(route_name="api_download_nn")
    def download_nn(self):
        nn_id = self.request.matchdict["id"]
        nn = self.request.rundb.get_nn(nn_id)
        if nn is None:
            self.handle_error(
                f"The network {nn_id} does not exist", exception=HTTPNotFound
            )

        self.request.rundb.increment_nn_downloads(nn_id)
        nn_base_url = os.environ.get(
            "FISHTEST_NN_URL", f"{self.request.scheme}://{self.request.host}"
        ).rstrip("/")

        return HTTPFound(f"{nn_base_url}/nn/{nn_id}")


class InternalApi(GenericApi):
    pass
