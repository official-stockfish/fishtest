import copy
import math
import os
import random
import re
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta, timezone

import fishtest.stats.stat_util
from bson.binary import Binary
from bson.codec_options import CodecOptions
from bson.errors import InvalidId
from bson.objectid import ObjectId
from fishtest.actiondb import ActionDb
from fishtest.schemas import (
    RUN_VERSION,
    cache_schema,
    compute_committed_games,
    compute_cores,
    compute_results,
    compute_total_games,
    compute_workers,
    nn_schema,
    pgns_schema,
    runs_schema,
)
from fishtest.stats.stat_util import SPRT_elo
from fishtest.userdb import UserDb
from fishtest.util import (
    GeneratorAsFileReader,
    Scheduler,
    crash_or_time,
    estimate_game_duration,
    format_bounds,
    format_results,
    get_bad_workers,
    get_chi2,
    get_hash,
    get_tc_ratio,
    remaining_hours,
    update_residuals,
    worker_name,
)
from fishtest.workerdb import WorkerDb
from pymongo import DESCENDING, MongoClient
from vtjson import ValidationError, validate

boot_time = datetime.now(timezone.utc)


class RunDb:

    def __init__(self, db_name="fishtest_new", port=-1, is_primary_instance=True):
        # MongoDB server is assumed to be on the same machine, if not user should
        # use ssh with port forwarding to access the remote host.
        self.conn = MongoClient(os.getenv("FISHTEST_HOST") or "localhost")
        codec_options = CodecOptions(tz_aware=True, tzinfo=timezone.utc)
        self.db = self.conn[db_name].with_options(codec_options=codec_options)
        self.userdb = UserDb(self.db)
        self.actiondb = ActionDb(self.db)
        self.workerdb = WorkerDb(self.db)
        self.pgndb = self.db["pgns"]
        self.nndb = self.db["nns"]
        self.runs = self.db["runs"]
        self.deltas = self.db["deltas"]
        self.port = port
        self.unfinished_runs = set()
        self.unfinished_runs_lock = threading.Lock()
        self.wtt_map = {}
        self.wtt_lock = threading.RLock()

        self.connections_counter = {}
        self.connections_lock = threading.Lock()

        self.task_duration = 1800  # 30 minutes
        self.ltc_lower_bound = 40  # Beware: this is used as a filter in an index!
        self.pt_info = {
            "pt_version": "SF_16",
            "pt_branch": "68e1e9b3811e16cad014b590d7443b9063b3eb52",
            "pt_bench": 2593605,
        }

        if self.port >= 0:
            self.actiondb.system_event(message=f"start fishtest@{self.port}")

        self.__is_primary_instance = is_primary_instance

        self.request_task_lock = threading.Lock()
        self.scheduler = None

    def schedule_tasks(self):
        if self.scheduler is None:
            self.scheduler = Scheduler(jitter=0.05)
        self.scheduler.create_task(1.0, self.flush_buffers)
        self.scheduler.create_task(60.0, self.clean_cache)
        self.scheduler.create_task(60.0, self.scavenge_dead_tasks)
        self.scheduler.create_task(60.0, self.update_itp)
        # short intial delay to make testing more pleasant
        self.scheduler.create_task(180.0, self.validate_random_run, initial_delay=60.0)
        self.scheduler.create_task(180.0, self.clean_wtt_map, initial_delay=60.0)

    def update_itp(self):
        with self.unfinished_runs_lock:
            unfinished_runs = [self.get_run(run_id) for run_id in self.unfinished_runs]

        user_active = [
            run["args"].get("username") for run in unfinished_runs if run["workers"] > 0
        ]

        for run in unfinished_runs:
            self.calc_itp(run, user_active.count(run["args"].get("username")))
            self.buffer(run, False)

    def clean_wtt_map(self):
        with self.wtt_lock:
            for short_worker_name in list(self.wtt_map):
                run, task_id = self.wtt_map[short_worker_name]
                task = run["tasks"][task_id]
                if not task["active"]:
                    del self.wtt_map[short_worker_name]
        print(f"Clean_wtt_map: {len(self.wtt_map)} active workers...")

    # Do not use this while holding an active_run_lock!
    def insert_in_wtt_map(self, run, task_id):
        task = run["tasks"][task_id]
        if not task["active"]:
            return
        short_worker_name = worker_name(task["worker_info"], short=True)
        with self.wtt_lock:
            if short_worker_name in self.wtt_map:
                wtt_run, wtt_task_id = self.wtt_map[short_worker_name]
                wtt_task = wtt_run["tasks"][wtt_task_id]
                with self.active_run_lock(wtt_run["_id"]):
                    if wtt_task["active"]:
                        self.failed_task(
                            wtt_run["_id"], wtt_task_id, message="Stale active task"
                        )
            self.wtt_map[short_worker_name] = run, task_id

    def validate_random_run(self):
        # Excess of caution. Another thread may change run_cache
        # while we are iterating over it.
        with self.run_cache_lock:
            run_list = [
                cache_entry["run"]
                for cache_entry in self.run_cache.values()
                if not cache_entry["run"]["finished"]
            ]
        if len(run_list) == 0:
            print(
                "Validate_random_run: no unfinished cache runs. No runs to validate...",
                flush=True,
            )
            return
        run = random.choice(run_list)
        run_id = str(run["_id"])
        try:
            # Make sure that the run object does not change while we are
            # validating it
            with self.active_run_lock(run_id):
                validate(runs_schema, run, "run")
                print(
                    f"Validate_random_run: validated cache run {run_id}...",
                    flush=True,
                )
        except ValidationError as e:
            message = f"The run object {run_id} does not validate: {str(e)}"
            print(message, flush=True)
            if "version" in run and run["version"] >= RUN_VERSION:
                self.actiondb.log_message(
                    username="fishtest.system",
                    message=message,
                )

    def set_inactive_run(self, run):
        run_id = str(run["_id"])
        with self.active_run_lock(run_id):
            for task_id in range(len(run["tasks"])):
                self.set_inactive_task(task_id, run)
            self.unfinished_runs.discard(run_id)
            run["finished"] = True

    def set_active_run(self, run):
        run_id = str(run["_id"])
        with self.active_run_lock(run_id):
            self.unfinished_runs.add(run_id)
            run["deleted"] = False
            run["failed"] = False
            run["is_green"] = False
            run["is_yellow"] = False
            run["finished"] = False

    def set_inactive_task(self, task_id, run):
        run_id = run["_id"]
        with self.active_run_lock(run_id):
            task = run["tasks"][task_id]
            if task["active"]:
                run["workers"] -= 1
                run["cores"] -= task["worker_info"]["concurrency"]
                stats = task["stats"]
                run["committed_games"] += (
                    -task["num_games"]
                    + stats["wins"]
                    + stats["losses"]
                    + stats["draws"]
                )
                task["active"] = False
                with self.connections_lock:
                    try:
                        remote_addr = task["worker_info"]["remote_addr"]
                        self.connections_counter[remote_addr] -= 1
                        if self.connections_counter[remote_addr] == 0:
                            del self.connections_counter[remote_addr]
                    except Exception as e:
                        print(f"Error while deleting connection: {str(e)}", flush=True)

    def set_bad_task(self, task_id, run, residual=None, residual_color=None):
        zero_stats = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": 5 * [0],
        }
        run_id = str(run["_id"])
        with self.active_run_lock(run_id):
            task = run["tasks"][task_id]
            if "bad" in task:
                return
            self.set_inactive_task(task_id, run)

            if "bad_tasks" not in run:
                run["bad_tasks"] = []
            bad_task = copy.deepcopy(task)
            run["bad_tasks"].append(bad_task)
            bad_task["task_id"] = task_id
            bad_task["bad"] = True

            if residual is not None:
                bad_task["residual"] = residual
            if residual_color is not None:
                bad_task["residual_color"] = residual_color

            stats = task["stats"]
            run["committed_games"] -= stats["wins"] + stats["losses"] + stats["draws"]

            # Rather than removing the task, we mark
            # it as bad.
            # In this way the numbering of tasks
            # does not change.
            # For safety we also set the stats
            # to zero.
            task["bad"] = True
            task["stats"] = copy.deepcopy(zero_stats)

    # Do not run two copies of this function in parallel!
    def update_aggregated_data(self):
        with self.wtt_lock:
            self.wtt_map = {}
        with self.connections_lock:
            self.connections_counter = {}
        with self.unfinished_runs_lock:
            self.unfinished_runs = set()

        for r in self.get_unfinished_runs_id():
            run_id = str(r["_id"])
            run = self.get_run(run_id)
            changed = False
            with self.active_run_lock(run_id):
                results = compute_results(run)
                if results != run["results"]:
                    print(
                        f"Warning: correcting results for {run_id}",
                        f"db: {run['results']} computed:{results}",
                        flush=True,
                    )
                    run["results"] = results
                    changed = True
                cores = compute_cores(run)
                if cores != run["cores"]:
                    print(
                        f"Warning: correcting cores for {run_id}",
                        f"db: {run['cores']} computed:{cores}",
                        flush=True,
                    )
                    run["cores"] = cores
                    changed = True
                workers = compute_workers(run)
                if workers != run["workers"]:
                    print(
                        f"Warning: correcting workers for {run_id}",
                        f"db: {run['workers']} computed:{workers}",
                        flush=True,
                    )
                    run["workers"] = workers
                    changed = True
                committed_games = compute_committed_games(run)
                committed_games_run = run.get("committed_games", None)
                if committed_games != committed_games_run:
                    print(
                        f"Warning: correcting committed_games for {run_id}",
                        f"db: {committed_games_run} computed:{committed_games}",
                        flush=True,
                    )
                    run["committed_games"] = committed_games
                    changed = True
                total_games = compute_total_games(run)
                total_games_run = run.get("total_games", None)
                if total_games != total_games_run:
                    print(
                        f"Warning: correcting total_games for {run_id}",
                        f"db: {total_games_run} computed:{total_games}",
                        flush=True,
                    )
                    run["total_games"] = total_games
                    changed = True

                with self.unfinished_runs_lock:
                    self.unfinished_runs.add(run_id)

                for task_id, task in enumerate(run["tasks"]):
                    if task["active"]:
                        with self.connections_lock:
                            remote_addr = task["worker_info"]["remote_addr"]
                            if remote_addr in self.connections_counter:
                                self.connections_counter[remote_addr] += 1
                            else:
                                self.connections_counter[remote_addr] = 1

            if changed:
                self.buffer(run, False)

            with self.wtt_lock:
                for task_id in range(len(run["tasks"])):
                    self.insert_in_wtt_map(run, task_id)

        self.update_itp()

        # This will be moved to a more suitable place once we have documented more
        # internal Fishtest data structures.
        try:
            validate(
                cache_schema,
                self.run_cache,
                name="run_cache",
                subs={"runs_schema": dict},
            )
        except ValidationError as e:
            print(f"Validation of run_cache failed: {str(e)}")

    def new_run(
        self,
        base_tag,
        new_tag,
        num_games,
        tc,
        new_tc,
        book,
        book_depth,
        threads,
        base_options,
        new_options,
        info="",
        resolved_base="",
        resolved_new="",
        master_sha="",
        official_master_sha="",
        msg_base="",
        msg_new="",
        base_signature="",
        new_signature="",
        base_nets=None,
        new_nets=None,
        rescheduled_from=None,
        base_same_as_master=None,
        start_time=None,
        sprt=None,
        spsa=None,
        username=None,
        tests_repo=None,
        auto_purge=False,
        throughput=100,
        priority=0,
        adjudication=True,
    ):
        if start_time is None:
            start_time = datetime.now(timezone.utc)

        run_args = {
            "base_tag": base_tag,
            "new_tag": new_tag,
            "base_nets": base_nets,
            "new_nets": new_nets,
            "num_games": num_games,
            "tc": tc,
            "new_tc": new_tc,
            "book": book,
            "book_depth": book_depth,
            "threads": threads,
            "resolved_base": resolved_base,
            "resolved_new": resolved_new,
            "master_sha": master_sha,
            "official_master_sha": official_master_sha,
            "msg_base": msg_base,
            "msg_new": msg_new,
            "base_options": base_options,
            "new_options": new_options,
            "info": info,
            "base_signature": base_signature,
            "new_signature": new_signature,
            "username": username,
            "tests_repo": tests_repo,
            "auto_purge": auto_purge,
            "throughput": throughput,
            "itp": 100,  # internal throughput
            "priority": priority,
            "adjudication": adjudication,
        }

        if sprt is not None:
            run_args["sprt"] = sprt

        if spsa is not None:
            run_args["spsa"] = spsa

        tc_base = re.search(r"^(\d+(\.\d+)?)", tc)
        if tc_base:
            tc_base = float(tc_base.group(1))
        new_run = {
            "version": RUN_VERSION,
            "args": run_args,
            "start_time": start_time,
            "last_updated": start_time,
            # This tc_base is redundant,
            # but it is used for an index.
            "tc_base": tc_base,
            "base_same_as_master": base_same_as_master,
            # Will be filled in by tasks, indexed by task-id.
            # Starts as an empty list.
            "tasks": [],
            "approved": False,
            "approver": "",
            # Aggregated data
            "results": {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "crashes": 0,
                "time_losses": 0,
                "pentanomial": 5 * [0],
            },
            "workers": 0,
            "cores": 0,
            "committed_games": 0,
            "total_games": 0,
        }

        # Administrative flags.
        # If the following comments are incorrect then that's a bug!

        # set in set_inactive_run()
        # cleared in set_active_run()
        new_run["finished"] = False

        # "deleted"
        # set in /tests/delete
        # cleared in set_active_run()
        new_run["deleted"] = False

        # "failed"
        # set in /api/stop_run
        # cleared in set_active_run()
        new_run["failed"] = False

        # "is_green"
        # set in stop_run(), purge_run()
        # cleared in purge_run(), set_active_run()
        new_run["is_green"] = False

        # "is_yellow"
        # set in stop_run(), purge_run()
        # cleared in purge_run(), set_active_run()
        new_run["is_yellow"] = False

        if rescheduled_from:
            new_run["rescheduled_from"] = rescheduled_from

        try:
            validate(runs_schema, new_run, "run")
        except ValidationError as e:
            message = f"The new run object does not validate: {str(e)}"
            print(message, flush=True)
            raise Exception(message)

        # We cannot use self.buffer since new_run does not have an id yet.
        run_id = self.runs.insert_one(new_run).inserted_id

        with self.unfinished_runs_lock:
            self.unfinished_runs.add(str(run_id))

        return run_id

    def is_primary_instance(self):
        return self.__is_primary_instance

    def upload_pgn(self, run_id, pgn_zip):
        record = {"run_id": run_id, "pgn_zip": Binary(pgn_zip), "size": len(pgn_zip)}
        try:
            validate(pgns_schema, record)
        except ValidationError as e:
            message = f"Internal Error. Pgn record has the wrong format: {str(e)}"
            print(message, flush=True)
            self.actiondb.log_message(
                username="fishtest.system",
                message=message,
            )
        self.pgndb.insert_one(
            record,
        )
        return {}

    def get_pgn(self, run_id):
        pgn = self.pgndb.find_one({"run_id": run_id})
        return (pgn["pgn_zip"], pgn["size"]) if pgn else (None, 0)

    def get_run_pgns(self, run_id):
        # Compute the total size using MongoDB's aggregation framework
        pgns_query = {"run_id": {"$regex": f"^{run_id}-\\d+"}}
        total_size_agg = self.pgndb.aggregate(
            [
                {"$match": pgns_query},
                {"$project": {"size": 1, "_id": 0}},
                {"$group": {"_id": None, "totalSize": {"$sum": "$size"}}},
            ]
        )
        total_size = total_size_agg.next()["totalSize"] if total_size_agg.alive else 0

        if total_size > 0:
            # Create a file reader from a generator that yields each pgn.gz file
            pgns = self.pgndb.find(pgns_query, {"pgn_zip": 1, "_id": 0})
            pgns_reader = GeneratorAsFileReader(pgn["pgn_zip"] for pgn in pgns)
        else:
            pgns_reader = None

        return pgns_reader, total_size

    def write_nn(self, net):
        validate(nn_schema, net, "net")
        self.nndb.replace_one({"name": net["name"]}, net, upsert=True)

    def get_nn(self, name):
        return self.nndb.find_one({"name": name}, {"nn": 0})

    def upload_nn(self, userid, name):
        self.write_nn({"user": userid, "name": name, "downloads": 0})

    def update_nn(self, net):
        net = copy.copy(net)  # avoid side effects
        net.pop("downloads", None)
        old_net = self.get_nn(net["name"])
        old_net.update(net)
        self.write_nn(old_net)

    def increment_nn_downloads(self, name):
        net = self.get_nn(name)
        net["downloads"] += 1
        self.write_nn(net)

    def get_nns(self, user="", network_name="", master_only=False, limit=0, skip=0):
        q = {}
        if user:
            q["user"] = {"$regex": ".*{}.*".format(user), "$options": "i"}
        if network_name:
            q["name"] = {"$regex": ".*{}.*".format(network_name), "$options": "i"}
        if master_only:
            q["is_master"] = True

        count = self.nndb.count_documents(q)
        nns_list = (
            dict(n, time=n["_id"].generation_time)
            for n in self.nndb.find(
                q, {"nn": 0}, limit=limit, skip=skip, sort=[("_id", DESCENDING)]
            )
        )
        return nns_list, count

    # Cache runs
    run_cache = {}
    run_cache_lock = threading.Lock()
    run_cache_write_lock = threading.Lock()

    # handle termination
    def exit_run(self, signum, frame):
        if self.scheduler is not None:
            self.scheduler.stop()
        self.flush_all()
        if self.port >= 0:
            self.actiondb.system_event(message=f"stop fishtest@{self.port}")
        sys.exit(0)

    def get_run(self, r_id):
        r_id = str(r_id)
        try:
            r_id_obj = ObjectId(r_id)
        except InvalidId:
            return None

        if self.is_primary_instance():
            with self.run_cache_lock:
                if r_id in self.run_cache:
                    self.run_cache[r_id]["last_access_time"] = time.time()
                    return self.run_cache[r_id]["run"]
                run = self.runs.find_one({"_id": r_id_obj})
                if run is not None:
                    self.run_cache[r_id] = {
                        "last_access_time": time.time(),
                        "last_sync_time": time.time(),
                        "run": run,
                        "is_changed": False,
                    }
                return run
        else:
            return self.runs.find_one({"_id": r_id_obj})

    def buffer(self, run, flush):
        if not self.is_primary_instance():
            print(
                "Warning: attempt to use the run_cache on the",
                f"secondary instance with port number {self.port}!",
                flush=True,
            )
            return
        with self.run_cache_lock:
            r_id = str(run["_id"])
            if flush:
                self.run_cache[r_id] = {
                    "is_changed": False,
                    "last_access_time": time.time(),
                    "last_sync_time": time.time(),
                    "run": run,
                }
                with self.run_cache_write_lock:
                    self.runs.replace_one({"_id": ObjectId(r_id)}, run)
            else:
                if r_id in self.run_cache:
                    last_sync_time = self.run_cache[r_id]["last_sync_time"]
                else:
                    last_sync_time = time.time()
                self.run_cache[r_id] = {
                    "is_changed": True,
                    "last_access_time": time.time(),
                    "last_sync_time": last_sync_time,
                    "run": run,
                }

    def stop(self):
        self.flush_all()
        with self.run_cache_lock:
            self.timer = None
        time.sleep(1.1)

    def flush_all(self):
        print("flush", flush=True)
        # Note that we do not grab locks because this method is
        # called from a signal handler and grabbing locks might deadlock
        for r_id in list(self.run_cache):
            entry = self.run_cache.get(r_id, None)
            if entry is not None and entry["is_changed"]:
                self.runs.replace_one({"_id": ObjectId(r_id)}, entry["run"])
                print(".", end="", flush=True)
        print("done", flush=True)

    # For documentation of the cache format see "cache_schema" in schemas.py.

    def flush_buffers(self):
        oldest_entry = None
        old = float("inf")
        with self.run_cache_lock:
            for cache_entry in self.run_cache.values():
                run = cache_entry["run"]
                if cache_entry["is_changed"] and cache_entry["last_sync_time"] < old:
                    old = cache_entry["last_sync_time"]
                    oldest_entry = cache_entry
            if oldest_entry is not None:
                oldest_run = oldest_entry["run"]
                oldest_entry["is_changed"] = False
                oldest_entry["last_sync_time"] = time.time()
                with self.run_cache_write_lock:
                    self.runs.replace_one({"_id": oldest_run["_id"]}, oldest_run)

    def clean_cache(self):
        now = time.time()
        with self.run_cache_lock:
            # We make this a list to be able to change run_cache during iteration
            for r_id, cache_entry in list(self.run_cache.items()):
                run = cache_entry["run"]
                # Presently run["finished"] implies run["cores"]==0 but
                # this was not always true in the past.
                if (
                    not cache_entry["is_changed"]
                    and (run["cores"] <= 0 or run["finished"])
                    and cache_entry["last_access_time"] < now - 300
                ):
                    del self.run_cache[r_id]

    def scavenge_dead_tasks(self):
        now = time.time()
        dead_tasks = []
        with self.run_cache_lock:
            for cache_entry in self.run_cache.values():
                run = cache_entry["run"]
                if not run["finished"]:
                    for task_id, task in enumerate(run["tasks"]):
                        if (
                            task["active"]
                            and task["last_updated"].timestamp() < now - 360
                        ):
                            dead_tasks.append((task_id, run))
        # We release the lock to avoid deadlock
        for task_id, run in dead_tasks:
            task = run["tasks"][task_id]
            print(
                "dead task: run: https://montychess.org/tests/view/{} task_id: {} worker: {}".format(
                    run["_id"], task_id, worker_name(task["worker_info"])
                ),
                flush=True,
            )
            self.handle_crash_or_time(run, task_id)
            self.actiondb.dead_task(
                username=task["worker_info"]["username"],
                run=run,
                task_id=task_id,
            )
            self.set_inactive_task(task_id, run)
            self.buffer(run, False)

    def get_unfinished_runs_id(self):
        with self.run_cache_write_lock:
            unfinished_runs = self.runs.find(
                {"finished": False}, {"_id": 1}, sort=[("last_updated", DESCENDING)]
            )
            return unfinished_runs

    def get_unfinished_runs(self, username=None):
        # Note: the result can be only used once.

        unfinished_runs = self.runs.find({"finished": False})
        if username:
            unfinished_runs = (
                r for r in unfinished_runs if r["args"].get("username") == username
            )
        return unfinished_runs

    def get_machines(self):
        active_runs = self.runs.find({"finished": False}, {"tasks": 1, "args": 1})
        machines = (
            task["worker_info"]
            | {
                "last_updated": (
                    task["last_updated"] if task.get("last_updated") else None
                ),
                "run": run,
                "task_id": task_id,
            }
            for run in active_runs
            if any(task["active"] for task in reversed(run["tasks"]))
            for task_id, task in enumerate(run["tasks"])
            if task["active"]
        )
        return machines

    def aggregate_unfinished_runs(self, username=None):
        unfinished_runs = self.get_unfinished_runs(username=username)
        runs = {"pending": [], "active": []}
        for run in unfinished_runs:
            state = "active" if run["workers"] > 0 else "pending"
            runs[state].append(run)
        runs["pending"].sort(
            key=lambda run: (
                run["args"]["priority"],
                run["args"]["itp"] if "itp" in run["args"] else 100,
            )
        )
        runs["active"].sort(
            reverse=True,
            key=lambda run: (
                "sprt" in run["args"],
                run["args"].get("sprt", {}).get("llr", 0),
                "spsa" not in run["args"],
                run["results"]["wins"]
                + run["results"]["draws"]
                + run["results"]["losses"],
            ),
        )

        # Calculate but don't save results_info on runs using info on current machines
        cores = 0
        nps = 0
        games_per_minute = 0.0
        machines_count = 0
        for run in runs["active"]:
            machines_count += run["workers"]
            cores += run["cores"]
            for task_id, task in enumerate(run["tasks"]):
                if task["active"]:
                    concurrency = int(task["worker_info"]["concurrency"])
                    nps += concurrency * task["worker_info"]["nps"]
                    if task["worker_info"]["nps"] != 0:
                        games_per_minute += (
                            (task["worker_info"]["nps"] / 368174)
                            * (60.0 / estimate_game_duration(run["args"]["tc"]))
                            * (
                                int(task["worker_info"]["concurrency"])
                                // run["args"].get("threads", 1)
                            )
                        )

        pending_hours = 0
        for run in runs["pending"] + runs["active"]:
            if cores > 0:
                eta = remaining_hours(run) / cores
                pending_hours += eta
            results = run["results"]
            run["results_info"] = format_results(results, run)
        return (runs, pending_hours, cores, nps, games_per_minute, machines_count)

    def get_finished_runs(
        self,
        skip=0,
        limit=0,
        username="",
        success_only=False,
        yellow_only=False,
        ltc_only=False,
        last_updated=None,
    ):
        q = {"finished": True}
        projection = {"tasks": 0, "bad_tasks": 0, "args.spsa.param_history": 0}
        if username:
            q["args.username"] = username
        if ltc_only:
            q["tc_base"] = {"$gte": self.ltc_lower_bound}
        if success_only:
            q["is_green"] = True
        if yellow_only:
            q["is_yellow"] = True
        if last_updated is not None:
            q["last_updated"] = {"$gte": last_updated}

        c = self.runs.find(
            q,
            skip=skip,
            limit=limit,
            sort=[("last_updated", DESCENDING)],
            projection=projection,
        )

        count = self.runs.count_documents(q)

        # Don't show runs that were deleted
        runs_list = [run for run in c if not run.get("deleted")]
        return [runs_list, count]

    def calc_itp(self, run, count):
        # Tests default to 100% base throughput, but we have several adjustments behind the scenes to get internal throughput.
        base_tp = run["args"]["throughput"]
        itp = base_tp = max(min(base_tp, 500), 1)  # Sanity check

        # The primary adjustment is derived from a power law of test TC relative to STC, so that long TCs compromise
        # between worse latency and chewing too many cores.
        tc_ratio = get_tc_ratio(run["args"]["tc"], run["args"]["threads"])
        # Discount longer test itp-per-TC without boosting sub-STC tests
        if tc_ratio > 1:
            # LTC/STC tc_ratio = 6, target latency ratio = 3/2,
            # --> LTC itp = 4 --> power = log(4)/log(6) ~ 0.774
            itp *= tc_ratio**0.774

        # The second adjustment is a multiplicative malus for too many active runs
        itp *= 36.0 / (36.0 + count * count)

        # Finally two gentle bonuses for positive LLR and long-running tests
        if sprt := run["args"].get("sprt"):
            llr = sprt.get("llr", 0)
            # Don't throw workers at a run that finishes in 2 minutes anyways
            llr = min(max(llr, 0), 2.0)
            a = 3  # max LLR bonus 1.67x
            itp *= (llr + a) / a
            # max long test bonus 2.0x
            r = run["results"]
            n = r["wins"] + r["losses"] + r["draws"]
            x = 200_000
            if n > x:
                itp *= min(n / x, 2)

        run["args"]["itp"] = itp

    # Limit concurrent request_task
    # It is very important that the following semaphore is initialized
    # with a value strictly less than the number of Waitress threads.

    task_semaphore = threading.Semaphore(2)

    worker_runs = {}

    def worker_cap(self, run, worker_info):
        # Estimate how many games a worker will be able to run
        # during the time interval determined by "self.task_duration".
        # Make sure the result is properly quantized and not zero.

        game_time = estimate_game_duration(run["args"]["tc"])
        concurrency = worker_info["concurrency"] // run["args"]["threads"]
        assert concurrency >= 1
        # as we have more tasks done (>250), make them longer to avoid
        # having many tasks in long running tests
        scale_duration = 1 + min(4, len(run["tasks"]) // 250)
        games = self.task_duration * scale_duration / game_time * concurrency
        if "sprt" in run["args"]:
            batch_size = 2 * run["args"]["sprt"].get("batch_size", 1)
            games = max(batch_size, batch_size * int(games / batch_size + 1 / 2))
        else:
            games = max(2, 2 * int(games / 2 + 1 / 2))
        return games

    def blocked_worker_message(self, worker_name, message, host_url):
        wrapped_message = textwrap.fill("Message: " + message, width=70)
        return f"""

**********************************************************************
Request_task: This worker has been blocked!
{wrapped_message}
You may possibly find more information at
{host_url}/actions?text=%22{worker_name}%22.
After fixing the issues you can unblock the worker at
{host_url}/workers/{worker_name}.
**********************************************************************
"""

    def request_task(self, worker_info):
        if self.task_semaphore.acquire(False):
            try:
                with self.request_task_lock:
                    return self.sync_request_task(worker_info)
            finally:
                self.task_semaphore.release()
        else:
            message = "Request_task: the server is currently too busy..."
            print(message, flush=True)
            return {"task_waiting": False, "info": message}

    def sync_request_task(self, worker_info):
        # We check if the worker has not been blocked.
        my_name = worker_name(worker_info, short=True)
        host_url = worker_info.get("host_url", "<host_url>")
        w = self.workerdb.get_worker(my_name)
        if w["blocked"]:
            # updates last_updated
            self.workerdb.update_worker(
                my_name, blocked=w["blocked"], message=w["message"]
            )
            error = self.blocked_worker_message(my_name, w["message"], host_url)
            return {"task_waiting": False, "error": error}
        # do not waste space in the db but also avoid side effects!
        worker_info = copy.copy(worker_info)
        worker_info.pop("host_url", None)

        # Now we see if a worker with the same name is already connected.
        now = datetime.now(timezone.utc)
        my_name_long = worker_name(worker_info)
        unique_key = worker_info["unique_key"]
        with self.wtt_lock:
            if my_name in self.wtt_map:
                wtt_run, wtt_task_id = self.wtt_map[my_name]
                wtt_task = wtt_run["tasks"][wtt_task_id]
                if wtt_task["active"]:
                    task_name_long = worker_name(wtt_task["worker_info"])
                    wtt_task_unique_key = wtt_task["worker_info"]["unique_key"]
                    if unique_key != wtt_task_unique_key:
                        last_update = (now - wtt_task["last_updated"]).seconds
                        if last_update <= 120:
                            error = (
                                f'Request_task: There is already a worker running with name "{task_name_long}" '
                                f'which {last_update} seconds ago sent an update for task {str(wtt_run["_id"])}/{wtt_task_id} '
                                f'(my name is "{my_name_long}")'
                            )
                            print(error, flush=True)
                            return {"task_waiting": False, "error": error}

        # We see if the worker has reached the number of allowed connections from the same ip
        # address.
        with self.connections_lock:
            connections_limit = self.userdb.get_machine_limit(worker_info["username"])
            connections = self.connections_counter.get(worker_info["remote_addr"], 0)
            if connections >= connections_limit:
                error = "Request_task: Machine limit reached for user {}".format(
                    worker_info["username"]
                )
                print(error, flush=True)
                return {"task_waiting": False, "error": error}

        # Collect some data about the worker that will be used below.
        max_threads = int(worker_info["concurrency"])
        min_threads = int(worker_info.get("min_threads", 1))
        max_memory = int(worker_info.get("max_memory", 0))
        near_github_api_limit = worker_info["near_github_api_limit"]

        # Now we sort the list of unfinished runs according to priority.
        last_run_id = self.worker_runs.get(unique_key, {}).get("last_run", None)

        def priority(run):  # lower is better
            return (
                # Always consider the higher priority runs first
                -run["args"]["priority"],
                # Try to avoid repeatedly working on the same test
                run["_id"] == last_run_id,
                # Make sure all runs at this priority level get _some_ cores
                run["cores"] > 0,
                # Try to match run["args"]["itp"].
                # Add max_threads/2 to mitigate granularity issues with large core workers.
                (run["cores"] + max_threads / 2) / run["args"]["itp"],
            )

        # Use a local copy of (the sorted) unfinished runs list so that it does
        # not change under our nose.
        with self.unfinished_runs_lock:
            unfinished_runs = [self.get_run(run_id) for run_id in self.unfinished_runs]
        unfinished_runs = sorted(unfinished_runs, key=priority)

        # Now go through the sorted list of unfinished runs.
        # We will add a task to the first run that is suitable.

        run_found = False

        for run in unfinished_runs:
            if run["finished"]:
                continue

            if not run["approved"]:
                continue

            if run["args"]["threads"] > max_threads:
                continue

            if run["args"]["threads"] < min_threads:
                continue

            # Check if there aren't already enough workers
            # working on this run.
            committed_games = run["committed_games"]

            remaining = run["args"]["num_games"] - committed_games
            if remaining <= 0:
                continue

            # We check if the worker has reserved enough memory
            need_tt = 0
            need_tt += get_hash(run["args"]["new_options"])
            need_tt += get_hash(run["args"]["base_options"])
            need_tt *= max_threads // run["args"]["threads"]
            # Needed for cutechess-cli with the fairly large UHO_Lichess_4852_v1.epd opening book
            need_base = 60
            # estimate another 10MB per process, 16MB per thread, and 132+6MB for large and small net
            # Note that changes here need the corresponding worker change to STC_memory, which limits concurrency
            need_base += (
                2
                * (max_threads // run["args"]["threads"])
                * (10 + 138 + 16 * run["args"]["threads"])
            )

            if need_base + need_tt > max_memory:
                continue

            # GitHub API limit...
            if near_github_api_limit:
                have_binary = (
                    unique_key in self.worker_runs
                    and run["_id"] in self.worker_runs[unique_key]
                )
                if not have_binary:
                    continue

            # To avoid time losses in the case of large concurrency and short TC,
            # probably due to cutechess-cli as discussed in issue #822,
            # assign linux workers to LTC or multi-threaded jobs
            # and windows workers only to LTC jobs
            if max_threads >= 29:
                if "windows" in worker_info["uname"].lower():
                    tc_too_short = get_tc_ratio(run["args"]["tc"], base="55+0.5") < 1.0
                else:
                    tc_too_short = (
                        get_tc_ratio(
                            run["args"]["tc"], run["args"]["threads"], "35+0.3"
                        )
                        < 1.0
                    )
                if tc_too_short:
                    continue

            # Limit the number of cores.
            # Currently this is only done for spsa.
            if "spsa" in run["args"]:
                limit_cores = 40000 / math.sqrt(len(run["args"]["spsa"]["params"]))
            else:
                limit_cores = 1000000  # infinity

            if run["cores"] > limit_cores:
                continue

            # If we make it here, it means we have found a run
            # suitable for a new task.
            run_found = True
            break

        # If there is no suitable run, tell the worker.
        if not run_found:
            return {"task_waiting": False}

        # Now we create a new task for this run.
        run_id = run["_id"]
        with self.active_run_lock(run_id):
            # It may happen that the run we have selected is now finished or
            # has enough games.
            # Since this is very rare we just return instead of cluttering the
            # code with remedial actions.

            # First recompute "remaining" because the value computed above was not
            # synchronized.
            remaining = run["args"]["num_games"] - run["committed_games"]

            if run["finished"] or remaining <= 0:
                info = (
                    f"Request_task: alas the run {run_id} corresponding to the "
                    "assigned task no longer needs games. Please try again..."
                )
                print(info, flush=True)
                return {"task_waiting": False, "info": info}

            opening_offset = run["total_games"]

            if "sprt" in run["args"]:
                sprt_batch_size_games = 2 * run["args"]["sprt"]["batch_size"]
                remaining = sprt_batch_size_games * math.ceil(
                    remaining / sprt_batch_size_games
                )

            task_size = min(self.worker_cap(run, worker_info), remaining)
            task = {
                "num_games": task_size,
                "active": True,
                "worker_info": worker_info,
                "last_updated": datetime.now(timezone.utc),
                "start": opening_offset,
                "stats": {
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "crashes": 0,
                    "time_losses": 0,
                    "pentanomial": 5 * [0],
                },
            }
            run["tasks"].append(task)

            with self.connections_lock:
                remote_addr = worker_info["remote_addr"]
                if remote_addr in self.connections_counter:
                    self.connections_counter[remote_addr] += 1
                else:
                    self.connections_counter[remote_addr] = 1

            task_id = len(run["tasks"]) - 1

            run["workers"] += 1
            run["cores"] += task["worker_info"]["concurrency"]
            run["committed_games"] += task["num_games"]
            run["total_games"] += task["num_games"]

        # We give up the lock to avoid deadlock

        self.insert_in_wtt_map(run, task_id)

        self.buffer(run, False)

        # Cache some data. Currently we record the id's
        # the worker has seen, as well as the last id that was seen.
        # Note that "worker_runs" is empty after a server restart.

        if unique_key not in self.worker_runs:
            self.worker_runs[unique_key] = {}

        if run["_id"] not in self.worker_runs[unique_key]:
            self.worker_runs[unique_key][run["_id"]] = True

        self.worker_runs[unique_key]["last_run"] = run["_id"]

        return {"run": run, "task_id": task_id}

    # Create a lock for each active run
    run_lock = threading.Lock()
    active_runs = {}
    purge_count = 0

    def active_run_lock(self, id):
        id = str(id)
        with self.run_lock:
            self.purge_count = self.purge_count + 1
            if self.purge_count > 100000:
                old = time.time() - 10000
                self.active_runs = dict(
                    (k, v) for k, v in self.active_runs.items() if v["time"] >= old
                )
                self.purge_count = 0
            if id in self.active_runs:
                active_lock = self.active_runs[id]["lock"]
                self.active_runs[id]["time"] = time.time()
            else:
                active_lock = threading.RLock()
                self.active_runs[id] = {"time": time.time(), "lock": active_lock}
            return active_lock

    def finished_run_message(self, run):
        if "spsa" in run["args"]:
            return "SPSA tune finished"
        result = "unknown"
        if "sprt" in run["args"]:
            sprt = run["args"]["sprt"]
            result = sprt.get("state", "")
            elo_model = sprt["elo_model"]
            alpha = sprt["alpha"]
            beta = sprt["beta"]
            elo0 = sprt["elo0"]
            elo1 = sprt["elo1"]
            results = run["results"]
            a = SPRT_elo(
                results,
                alpha=alpha,
                beta=beta,
                elo0=elo0,
                elo1=elo1,
                elo_model=elo_model,
            )
            ret = f"Result:{result}"
            ret += f" Elo:{a['elo']:.2f}[{a['ci'][0]:.2f},{a['ci'][1]:.2f}]"
            ret += f" LOS:{a['LOS']:.0%}"
        else:
            results = run["results"]
            if "pentanomial" in results:
                elo, elo95, los = fishtest.stats.stat_util.get_elo(
                    results["pentanomial"]
                )
            else:
                WLD = [results["wins"], results["losses"], results["draws"]]
                elo, elo95, los = fishtest.stats.stat_util.get_elo(
                    [WLD[1], WLD[2], WLD[0]]
                )
            if run["is_green"]:
                result = "accepted"
            else:
                result = "rejected"

            ret = f"Result:{result}"
            ret += f" Elo:{elo:.2f}[{elo-elo95:.2f},{elo+elo95:.2f}]"
            ret += f" LOS:{los:.0%}"

        results = run["results"]
        pentanomial = results["pentanomial"]
        total = 2 * sum(pentanomial)
        ret += f" Games:{total} Ptnml:{str(pentanomial).replace(' ','')}"
        return ret

    def handle_crash_or_time(self, run, task_id):
        task = run["tasks"][task_id]
        if crash_or_time(task):
            stats = task.get("stats", {})
            total = (
                stats.get("wins", 0) + stats.get("losses", 0) + stats.get("draws", 0)
            )
            if not total:
                return
            crashes = stats.get("crashes", 0)
            time_losses = stats.get("time_losses", 0)
            message = f"Time losses:{time_losses}({time_losses/total:.1%}) Crashes:{crashes}({crashes/total:.1%})"
            self.actiondb.crash_or_time(
                username=task["worker_info"]["username"],
                run=run,
                task_id=task_id,
                message=message,
            )

    def update_task(self, worker_info, run_id, task_id, stats, spsa):
        lock = self.active_run_lock(run_id)
        with lock:
            return self.sync_update_task(worker_info, run_id, task_id, stats, spsa)

    def sync_update_task(self, worker_info, run_id, task_id, stats, spsa):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        update_time = datetime.now(timezone.utc)

        error = ""

        def count_games(d):
            return d["wins"] + d["losses"] + d["draws"]

        num_games = count_games(stats)
        old_num_games = count_games(task["stats"]) if "stats" in task else 0
        spsa_games = count_games(spsa) if "spsa" in run["args"] else 0

        # First some sanity checks on the update
        # If something is wrong we return early.

        # task["active"]=True means that a worker should be working on this task.
        # Tasks are created as "active" and become "not active" when they
        # are finished, or when the worker goes offline.

        if not task["active"]:
            info = "Update_task: task {}/{} is not active".format(run_id, task_id)
            # Only log the case where the run is not yet finished,
            # otherwise it is expected behavior
            if not run["finished"]:
                print(info, flush=True)
            return {"task_alive": False, "info": info}

        # Guard against incorrect results

        if (
            num_games < old_num_games
            or (spsa_games > 0 and num_games <= 0)
            or (spsa_games > 0 and "stats" in task and num_games <= old_num_games)
        ) and error == "":
            error = "Update_task: task {}/{} has incompatible stats. ".format(
                run_id, task_id
            ) + "Before {}. Now {}. SPSA_games {}.".format(
                old_num_games, num_games, spsa_games
            )
        elif (
            num_games - old_num_games
        ) % 2 != 0 and error == "":  # the worker should only return game pairs
            error = "Update_task: odd number of games received for task {}/{}. Before {}. Now {}.".format(
                run_id, task_id, old_num_games, num_games
            )
        elif "sprt" in run["args"] and error == "":
            batch_size = 2 * run["args"]["sprt"].get("batch_size", 1)
            if num_games % batch_size != 0:
                error = "Update_task: the number of games received for task {}/{} is incompatible with the SPRT batch size".format(
                    run_id, task_id
                )

        if error != "":
            print(error, flush=True)
            self.set_inactive_task(task_id, run)
            return {"task_alive": False, "error": error}

        # The update seems fine.

        # Increment run results before overwriting task["stats"]

        for key, value in stats.items():
            if key == "pentanomial":
                run["results"][key] = [
                    x + y - z
                    for x, y, z in zip(
                        run["results"][key], value, task["stats"].get(key, [0] * 5)
                    )
                ]
            else:
                run["results"][key] += value - task["stats"].get(key, 0)

        # Update run["tasks"][task_id] (=task).

        task["stats"] = stats
        task["last_updated"] = update_time
        task["worker_info"] = worker_info  # updates rate, ARCH, nps

        task_finished = False
        if num_games >= task["num_games"]:
            # This task is now finished
            task_finished = True
            self.set_inactive_task(task_id, run)

        # Now update the current run.

        run["last_updated"] = update_time

        if "sprt" in run["args"]:
            sprt = run["args"]["sprt"]
            fishtest.stats.stat_util.update_SPRT(run["results"], sprt)
            if sprt["state"] != "":
                task_finished = True
                self.set_inactive_task(task_id, run)

        if "spsa" in run["args"] and spsa_games == spsa["num_games"]:
            self.update_spsa(task["worker_info"]["unique_key"], run, spsa)

        # Record tasks with an excessive amount of crashes or time losses in the event log

        if task_finished:
            self.handle_crash_or_time(run, task_id)

        # Check if the run is finished.

        run_finished = False
        if count_games(run["results"]) >= run["args"]["num_games"]:
            run_finished = True
        elif "sprt" in run["args"] and sprt["state"] != "":
            run_finished = True

        # Return.

        if run_finished:
            self.stop_run(run_id)
            # stop run may not actually stop a run because of autopurging!
            if run["finished"]:
                self.actiondb.finished_run(
                    username=run["args"]["username"],
                    run=run,
                    message=self.finished_run_message(run),
                )
            # No need to update the db since it was already
            # done by stop_run.
            ret = {"task_alive": False}
        else:
            self.buffer(run, False)
            ret = {"task_alive": task["active"]}

        return ret

    def failed_task(self, run_id, task_id, message="Unknown reason"):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        # Check if the worker is still working on this task.
        if not task["active"]:
            info = "Failed_task: task {}/{} is not active".format(run_id, task_id)
            print(info, flush=True)
            return {"task_alive": False, "info": info}
        # Mark the task as inactive.
        self.set_inactive_task(task_id, run)
        self.handle_crash_or_time(run, task_id)
        self.buffer(run, False)
        print(
            "Failed_task: failure for: https://montychess.org/tests/view/{}, "
            "task_id: {}, worker: {}, reason: '{}'".format(
                run_id, task_id, worker_name(task["worker_info"]), message
            ),
            flush=True,
        )
        self.actiondb.failed_task(
            username=task["worker_info"]["username"],
            run=run,
            task_id=task_id,
            message=message,
        )
        return {}

    def stop_run(self, run_id):
        """Stops a run and runs auto-purge if it was enabled
        - Used by the website and API for manually stopping runs
        - Called during /api/update_task:
          - for stopping SPRT runs if the test is accepted or rejected
          - for stopping a run after all games are finished
        """
        self.clear_params(run_id)  # spsa stuff
        run = self.get_run(run_id)
        self.set_inactive_run(run)

        results = run["results"]
        run["results_info"] = format_results(results, run)
        # De-couple the styling of the run from its finished status
        if run["results_info"]["style"] == "#44EB44":
            run["is_green"] = True
        elif run["results_info"]["style"] == "yellow":
            run["is_yellow"] = True
        try:
            validate(runs_schema, run, "run")
        except ValidationError as e:
            message = f"The run object {run_id} does not validate: {str(e)}"
            print(message, flush=True)
            if "version" in run and run["version"] >= RUN_VERSION:
                self.actiondb.log_message(
                    username="fishtest.system",
                    message=message,
                )
        self.buffer(run, True)

        # Auto-purge runs here. This may revive the run.
        if run["args"].get("auto_purge", True) and "spsa" not in run["args"]:
            message = self.purge_run(run)
            self.actiondb.purge_run(
                username=run["args"]["username"],
                run=run,
                message=(
                    f"Auto purge (not performed): {message}"
                    if message
                    else "Auto purge"
                ),
            )
            if message == "":
                print("Run {} was auto-purged".format(str(run_id)), flush=True)
            else:
                print(
                    "Run {} was not auto-purged. Message: {}.".format(
                        str(run_id), message
                    ),
                    flush=True,
                )

    def approve_run(self, run_id, approver):
        run = self.get_run(run_id)
        if run is None:
            return None, f"Run {str(run_id)} not found!"
        # Can't self approve
        if run["args"]["username"] == approver:
            return None, f"Run {str(run_id)}: Self approval is disabled!"
        # Only one approval per run
        if not run["approved"]:
            run["approved"] = True
            run["approver"] = approver
            self.buffer(run, True)
            return run, f"Run {str(run_id)} approved"
        else:
            return None, f"Run {str(run_id)} already approved!"

    def purge_run(self, run, p=0.001, res=7.0, iters=1):
        # Only purge finished runs
        if not run["finished"]:
            return "Can only purge completed run"

        now = datetime.now(timezone.utc)
        if "start_time" not in run or (now - run["start_time"]).days > 30:
            return "Run too old to be purged"
        # Do not revive failed runs
        if run.get("failed", False):
            return "You cannot purge a failed run"
        message = "No bad workers"
        # Transfer bad tasks to run["bad_tasks"]
        if "bad_tasks" not in run:
            run["bad_tasks"] = []

        tasks = copy.copy(run["tasks"])
        zero_stats = {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "crashes": 0,
            "time_losses": 0,
            "pentanomial": 5 * [0],
        }

        for task_id, task in enumerate(tasks):
            if "bad" in task:
                continue
            # Special cases: crashes or time losses.
            if crash_or_time(task):
                message = ""
                # The residual or residual color my not have been set yet
                self.set_bad_task(task_id, run, residual=10.0, residual_color="#FF6A6A")

        chi2 = get_chi2(run["tasks"])
        # Make sure the residuals are up to date.
        # Once a task is moved to run["bad_tasks"] its
        # residual will no longer change.
        update_residuals(run["tasks"], cached_chi2=chi2)
        bad_workers = get_bad_workers(
            run["tasks"],
            cached_chi2=chi2,
            p=p,
            res=res,
            iters=iters - 1 if message == "" else iters,
        )
        tasks = copy.copy(run["tasks"])
        for task_id, task in enumerate(tasks):
            if "bad" in task:
                continue
            if task["worker_info"]["unique_key"] in bad_workers:
                message = ""
                self.set_bad_task(task_id, run)

        if message == "":
            results = compute_results(run)
            run["results"] = results
            revived = True
            if "sprt" in run["args"] and "state" in run["args"]["sprt"]:
                fishtest.stats.stat_util.update_SPRT(results, run["args"]["sprt"])
                if run["args"]["sprt"]["state"] != "":
                    revived = False

            run["results_info"] = format_results(results, run)
            if revived:
                self.set_active_run(run)
            else:
                # Copied code. Must be refactored.
                style = run["results_info"]["style"]
                run["is_green"] = style == "#44EB44"
                run["is_yellow"] = style == "yellow"
            self.buffer(run, True)
        return message

    def spsa_param_clip(self, param, increment):
        return min(max(param["theta"] + increment, param["min"]), param["max"])

    # Store SPSA parameters for each worker
    spsa_params = {}

    def store_params(self, run_id, worker, params):
        run_id = str(run_id)
        if run_id not in self.spsa_params:
            self.spsa_params[run_id] = {}
        self.spsa_params[run_id][worker] = params

    def get_params(self, run_id, worker):
        run_id = str(run_id)
        if run_id not in self.spsa_params or worker not in self.spsa_params[run_id]:
            # Should only happen after server restart
            return self.generate_spsa(self.get_run(run_id))["w_params"]
        return self.spsa_params[run_id][worker]

    def clear_params(self, run_id):
        run_id = str(run_id)
        if run_id in self.spsa_params:
            del self.spsa_params[run_id]

    def request_spsa(self, run_id, task_id):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        # Check if the worker is still working on this task.
        if not task["active"]:
            info = "Request_spsa: task {}/{} is not active".format(run_id, task_id)
            print(info, flush=True)
            return {"task_alive": False, "info": info}

        result = self.generate_spsa(run)
        self.store_params(
            run["_id"], task["worker_info"]["unique_key"], result["w_params"]
        )
        return result

    def generate_spsa(self, run):
        result = {"task_alive": True, "w_params": [], "b_params": []}
        spsa = run["args"]["spsa"]

        # Generate the next set of tuning parameters
        iter_local = spsa["iter"] + 1  # start from 1 to avoid division by zero
        for param in spsa["params"]:
            c = param["c"] / iter_local ** spsa["gamma"]
            flip = 1 if random.getrandbits(1) else -1
            result["w_params"].append(
                {
                    "name": param["name"],
                    "value": self.spsa_param_clip(param, c * flip),
                    "R": param["a"] / (spsa["A"] + iter_local) ** spsa["alpha"] / c**2,
                    "c": c,
                    "flip": flip,
                }
            )
            result["b_params"].append(
                {
                    "name": param["name"],
                    "value": self.spsa_param_clip(param, -c * flip),
                }
            )

        return result

    def update_spsa(self, worker, run, spsa_results):
        spsa = run["args"]["spsa"]
        spsa["iter"] += int(spsa_results["num_games"] / 2)

        # Store the history every 'freq' iterations.
        # More tuned parameters result in a lower update frequency,
        # so that the required storage (performance) remains constant.
        if "param_history" not in spsa:
            spsa["param_history"] = []
        n_params = len(spsa["params"])
        samples = 101 if n_params < 100 else 10000 / n_params if n_params < 1000 else 1
        freq = run["args"]["num_games"] / 2 / samples
        grow_summary = len(spsa["param_history"]) < spsa["iter"] / freq

        # Update the current theta based on the results from the worker
        # Worker wins/losses are always in terms of w_params
        result = spsa_results["wins"] - spsa_results["losses"]
        summary = []
        w_params = self.get_params(run["_id"], worker)
        for idx, param in enumerate(spsa["params"]):
            R = w_params[idx]["R"]
            c = w_params[idx]["c"]
            flip = w_params[idx]["flip"]
            param["theta"] = self.spsa_param_clip(param, R * c * result * flip)
            if grow_summary:
                summary.append({"theta": param["theta"], "R": R, "c": c})

        if grow_summary:
            spsa["param_history"].append(summary)
