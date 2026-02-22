import base64
import copy
import io
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, StreamingResponse
from vtjson import ValidationError, validate

import fishtest.github_api as gh
from fishtest.http.boundary import ApiRequestShim, get_request_shim
from fishtest.schemas import api_access_schema, api_schema, gzip_data
from fishtest.stats.stat_util import SPRT_elo, get_elo
from fishtest.util import strip_run, worker_name

WORKER_VERSION = 312

WORKER_API_PATHS = {
    "/api/request_version",
    "/api/request_task",
    "/api/update_task",
    "/api/beat",
    "/api/request_spsa",
    "/api/failed_task",
    "/api/stop_run",
    "/api/upload_pgn",
    "/api/worker_log",
}

# Primary-only worker endpoints exclude upload_pgn, which is routed to a
# non-primary backend for single-instance handling.
PRIMARY_ONLY_WORKER_API_PATHS = WORKER_API_PATHS - {"/api/upload_pgn"}

router = APIRouter(tags=["api"])


def _cors_headers(methods=None):
    headers = {
        "access-control-allow-origin": "*",
        "access-control-allow-headers": "content-type",
    }
    if methods:
        if isinstance(methods, (list, tuple, set)):
            headers["access-control-allow-methods"] = ", ".join(methods)
        else:
            headers["access-control-allow-methods"] = str(methods)
    return headers


def _iter_filelike(fileobj, chunk_size=1024 * 1024):
    try:
        while True:
            chunk = fileobj.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(fileobj, "close", None)
        if callable(close):
            close()


class GenericApi:
    def __init__(self, request):
        self.request = request
        self.__t0 = datetime.now(UTC)

    def timestamp(self):
        return self.__t0

    def add_time(self, result):
        result["duration"] = (datetime.now(UTC) - self.timestamp()).total_seconds()
        return result

    def handle_error(self, error, status_code=400):
        if error != "":
            api = urlparse(str(self.request.url)).path
            error = f"{api}: {error}"
            print(error, flush=True)
            raise HTTPException(
                status_code=status_code,
                detail=self.add_time({"error": error}),
            )


class WorkerApi(GenericApi):
    """All API endpoints that require authentication are used by workers"""

    def __init__(self, request):
        super().__init__(request)
        # is the request valid json?
        try:
            self.request_body = request.json_body
        except Exception:
            self.handle_error("request is not json encoded")

    def validate_username_password(self):
        # Is the request syntactically correct?
        try:
            validate(api_access_schema, self.request_body, "request")
        except ValidationError as e:
            self.handle_error(str(e))

        # is the supplied password correct?
        token = self.request.userdb.authenticate(
            self.request_body["worker_info"]["username"],
            self.request_body["password"],
        )
        if "error" in token:
            self.handle_error(token["error"], status_code=401)

    def validate_request(self):
        """This function will load the run from the cache or the db,
        depending on the type of instance it runs on (primary or
        secondary). If the request refers to a particular
        task then one needs to make sure that it has been saved
        to disk when invoking this function on a secondary instance.
        """
        self.__run = None
        self.__task = None

        # Preliminary validation.
        self.validate_username_password()

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
                self.handle_error(f"Invalid run_id: {run_id}")
            self.__run = run

        # if a task_id is present then the unique_key and username
        # should be correct
        if "task_id" in self.request_body:
            task_id = self.request_body["task_id"]

            if task_id < 0 or task_id >= len(run["tasks"]):
                self.handle_error(
                    f"Invalid task_id {task_id} for run_id {run_id}",
                )

            task = run["tasks"][task_id]
            for key in ("unique_key", "username"):
                value_request = self.request_body["worker_info"][key]
                value_task = task["worker_info"][key]

                if value_request != value_task:
                    self.handle_error(
                        f"Invalid {key} for task {run_id}/{task_id}. From task: "
                        f"{value_task}. From request: {value_request}.",
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

    def failed_task(self):
        self.validate_request()
        result = self.request.rundb.failed_task(
            self.run_id(),
            self.task_id(),
            self.message(),
        )
        return self.add_time(result)

    def worker_log(self):
        self.validate_request()
        self.request.actiondb.log_message(
            username=self.get_username(),
            message=self.message(),
            worker=self.worker_name(),
        )
        return self.add_time({})

    def upload_pgn(self):
        self.validate_request()
        try:
            pgn_zip = base64.b64decode(self.pgn())
            validate(gzip_data, pgn_zip, "pgn")
        except Exception as e:
            self.handle_error(str(e))
        result = self.request.rundb.upload_pgn(
            run_id=f"{self.run_id()}-{self.task_id()}",
            pgn_zip=pgn_zip,
        )
        return self.add_time(result)

    def stop_run(self):
        self.validate_request()
        error = ""
        if self.cpu_hours() < 1000:
            error = f"User {self.get_username()} has too few games to stop a run"
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
        self.handle_error(error, status_code=401)
        return self.add_time({})

    def request_version(self):
        # By being more lax here, we can be more strict
        # elsewhere since the worker will upgrade.
        self.validate_username_password()
        return self.add_time({"version": WORKER_VERSION})

    def beat(self):
        self.validate_request()
        run = self.run()
        task = self.task()
        with self.request.rundb.active_run_lock(self.run_id()):
            if task["active"]:
                task["last_updated"] = datetime.now(UTC)
                self.request.rundb.buffer(run)
            return self.add_time({"task_alive": task["active"]})

    def request_spsa(self):
        self.validate_request()
        result = self.request.rundb.spsa_handler.request_spsa_data(
            self.run_id(),
            self.task_id(),
        )
        return self.add_time(result)


class UserApi(GenericApi):
    def rate_limit(self):
        return gh.rate_limit()

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

    def get_run(self):
        run_id = self.request.matchdict["id"]
        run = self.request.rundb.get_run(run_id)
        if run is None:
            self.handle_error(f"The run {run_id} does not exist", status_code=404)
        self.request.response.headers["access-control-allow-origin"] = "*"
        self.request.response.headers["access-control-allow-headers"] = "content-type"
        return strip_run(run)

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
                f"The task {run_id}/{task_id} does not exist",
                status_code=404,
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

    def get_elo(self):
        run_id = self.request.matchdict["id"]
        run = self.request.rundb.get_run(run_id)
        if run is None:
            self.handle_error(f"The run {run_id} does not exist", status_code=404)
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
            results,
            alpha=alpha,
            beta=beta,
            elo0=elo0,
            elo1=elo1,
            elo_model=elo_model,
        )
        run["elo"] = a
        return run

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
                "Invalid or missing parameters. Please provide all values as valid numbers.",
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
            WLD = [results["wins"], results["losses"], results["draws"]]
            elo3, elo95_3, LOS3 = get_elo([WLD[1], WLD[2], WLD[0]])
            elo3_l = elo3 - elo95_3
            elo3_u = elo3 + elo95_3
            return {"elo": elo3, "ci": [elo3_l, elo3_u], "LOS": LOS3}
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
                "Valid Elo models are: BayesElo, logistic, and normalized.",
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

    def download_pgn(self):
        zip_name = self.request.matchdict["id"]
        run_id = zip_name.split(".")[0]  # strip .pgn
        pgn_zip, size = self.request.rundb.get_pgn(run_id)
        if pgn_zip is None:
            self.handle_error(f"No data found for {zip_name}", status_code=404)

        headers = {
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "Content-Encoding": "gzip",
            "Content-Length": str(size),
        }
        return StreamingResponse(
            iterate_in_threadpool(_iter_filelike(io.BytesIO(pgn_zip))),
            media_type="application/gzip",
            headers=headers,
        )

    def download_run_pgns(self):
        pgns_name = self.request.matchdict["id"]
        match = re.match(r"^([a-zA-Z0-9]+)\.pgn\.gz$", pgns_name)
        if not match:
            self.handle_error(f"Invalid filename format for {pgns_name}")
        run_id = match.group(1)
        pgns_reader, total_size = self.request.rundb.get_run_pgns(run_id)
        if pgns_reader is None:
            self.handle_error(f"No data found for {pgns_name}", status_code=404)
        headers = {
            "Content-Disposition": f'attachment; filename="{pgns_name}"',
            "Content-Length": str(total_size),
        }
        return StreamingResponse(
            iterate_in_threadpool(_iter_filelike(pgns_reader)),
            media_type="application/gzip",
            headers=headers,
        )

    def download_nn(self):
        nn_id = self.request.matchdict["id"]
        nn = self.request.rundb.get_nn(nn_id)
        if nn is None:
            self.handle_error(f"The network {nn_id} does not exist", status_code=404)

        self.request.rundb.increment_nn_downloads(nn_id)
        nn_base_url = os.environ.get(
            "FISHTEST_NN_URL",
            f"{self.request.scheme}://{self.request.host}",
        ).rstrip("/")
        return RedirectResponse(f"{nn_base_url}/nn/{nn_id}", status_code=302)


@router.post("/api/request_task")
async def api_request_task(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.request_task)


@router.post("/api/update_task")
async def api_update_task(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.update_task)


@router.post("/api/failed_task")
async def api_failed_task(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.failed_task)


@router.post("/api/stop_run")
async def api_stop_run(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.stop_run)


@router.post("/api/request_version")
async def api_request_version(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.request_version)


@router.post("/api/beat")
async def api_beat(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.beat)


@router.post("/api/request_spsa")
async def api_request_spsa(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.request_spsa)


@router.post("/api/worker_log")
async def api_worker_log(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.worker_log)


@router.post("/api/upload_pgn")
async def api_upload_pgn(request: Request):
    api = WorkerApi(await get_request_shim(request))
    return await run_in_threadpool(api.upload_pgn)


@router.get("/api/rate_limit")
async def api_rate_limit(request: Request):
    api = UserApi(ApiRequestShim(request))
    return await run_in_threadpool(api.rate_limit)


@router.get("/api/active_runs")
async def api_active_runs(request: Request):
    api = UserApi(ApiRequestShim(request))
    return await run_in_threadpool(api.active_runs)


@router.get("/api/finished_runs")
async def api_finished_runs(request: Request):
    api = UserApi(ApiRequestShim(request))
    return await run_in_threadpool(api.finished_runs)


@router.post("/api/actions")
async def api_actions(request: Request):
    api = UserApi(await get_request_shim(request))
    result = await run_in_threadpool(api.actions)
    return JSONResponse(result, headers=api.request.response.headers)


@router.options("/api/actions")
async def api_actions_options(request: Request):
    # Explicit preflight route retained for browser clients using cross-origin
    # POST requests against this endpoint.
    return JSONResponse([], headers=_cors_headers(["POST", "OPTIONS"]))


@router.get("/api/get_run/{id}")
async def api_get_run(id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id}))
    result = await run_in_threadpool(api.get_run)
    return JSONResponse(result, headers=api.request.response.headers)


@router.options("/api/get_run/{id}")
async def api_get_run_options(id, request: Request):
    # Explicit preflight route retained for browser clients using cross-origin
    # GET requests with custom headers against this endpoint.
    return JSONResponse([], headers=_cors_headers(["GET", "OPTIONS"]))


@router.get("/api/get_task/{id}/{task_id}")
async def api_get_task(id, task_id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id, "task_id": task_id}))
    return await run_in_threadpool(api.get_task)


@router.get("/api/get_elo/{id}")
async def api_get_elo(id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id}))
    return await run_in_threadpool(api.get_elo)


@router.get("/api/calc_elo")
async def api_calc_elo(request: Request):
    api = UserApi(ApiRequestShim(request))
    return await run_in_threadpool(api.calc_elo)


@router.get("/api/pgn/{id}")
async def api_download_pgn(id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id}))
    return await run_in_threadpool(api.download_pgn)


@router.get("/api/run_pgns/{id}")
async def api_download_run_pgns(id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id}))
    return await run_in_threadpool(api.download_run_pgns)


@router.get("/api/nn/{id}")
async def api_download_nn(id, request: Request):
    api = UserApi(ApiRequestShim(request, matchdict={"id": id}))
    return await run_in_threadpool(api.download_nn)


__all__ = ["WORKER_VERSION", "router"]
