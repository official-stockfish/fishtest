import copy
import math
import os
import random
import re
import signal
import sys
import threading
import time
import zlib
from datetime import datetime, timedelta

import fishtest.stats.stat_util
from bson.binary import Binary
from bson.objectid import ObjectId
from fishtest.actiondb import ActionDb
from fishtest.userdb import UserDb
from fishtest.util import (
    crash_or_time,
    estimate_game_duration,
    format_bounds,
    format_results,
    get_bad_workers,
    get_chi2,
    post_in_fishcooking_results,
    remaining_hours,
)
from fishtest.util import unique_key as unique_key_
from fishtest.util import update_residuals, worker_name
from fishtest.views import del_tasks
from pymongo import DESCENDING, MongoClient

DEBUG = False

boot_time = datetime.utcnow()

last_rundb = None


class RunDb:
    def __init__(self, db_name="fishtest_new"):
        # MongoDB server is assumed to be on the same machine, if not user should
        # use ssh with port forwarding to access the remote host.
        self.conn = MongoClient(os.getenv("FISHTEST_HOST") or "localhost")
        self.db = self.conn[db_name]
        self.userdb = UserDb(self.db)
        self.actiondb = ActionDb(self.db)
        self.pgndb = self.db["pgns"]
        self.nndb = self.db["nns"]
        if "runs_new" in self.db.list_collection_names():
            print('Using "runs_new"')
            self.runs = self.db["runs_new"]
        else:
            print('Not using "runs_new"')
            self.runs = self.db["runs"]
        self.deltas = self.db["deltas"]
        self.task_runs = []

        self.chunk_size = 200
        self.task_duration = 900  # 15 minutes

        global last_rundb
        last_rundb = self

    def generate_tasks(self, num_games):
        return []

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
        msg_base="",
        msg_new="",
        base_signature="",
        new_signature="",
        base_net=None,
        new_net=None,
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
            start_time = datetime.utcnow()

        run_args = {
            "base_tag": base_tag,
            "new_tag": new_tag,
            "base_net": base_net,
            "new_net": new_net,
            "num_games": num_games,
            "tc": tc,
            "new_tc": new_tc,
            "book": book,
            "book_depth": book_depth,
            "threads": threads,
            "resolved_base": resolved_base,
            "resolved_new": resolved_new,
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

        tc_base = re.search("^(\d+(\.\d+)?)", tc)
        if tc_base:
            tc_base = float(tc_base.group(1))
        new_run = {
            "args": run_args,
            "start_time": start_time,
            "last_updated": start_time,
            # This tc_base is redundant,
            # but it is used for an index.
            "tc_base": tc_base,
            "base_same_as_master": base_same_as_master,
            # Will be filled in by tasks, indexed by task-id.
            # Starts as an empty list.
            # generate_tasks() is currently a dummy
            "tasks": self.generate_tasks(num_games),
            # Aggregated results
            "results": {
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "crashes": 0,
                "time_losses": 0,
                "pentanomial": 5 * [0],
            },
            "results_stale": False,
            "approved": False,
            "approver": "",
        }

        # administrative flags

        # "finished"
        # set in stop_run(), /api/stop_run
        # cleared in purge_run(), /tests/modify
        new_run["finished"] = False

        # "deleted"
        # set in /tests/delete
        new_run["deleted"] = False

        # "failed"
        # set in /api/stop_run
        # cleared in /tests/modify
        new_run["failed"] = False

        # "is_green"
        # set in stop_run()
        # cleared in purge_run(), /tests/modify
        new_run["is_green"] = False

        # "is_yellow"
        # set in stop_run()
        # cleared in purge_run(), /tests/modify
        new_run["is_yellow"] = False

        if rescheduled_from:
            new_run["rescheduled_from"] = rescheduled_from

        return self.runs.insert_one(new_run).inserted_id

    def get_machines(self):
        machines = []
        active_runs = self.runs.find(
            {"finished": False, "tasks": {"$elemMatch": {"active": True}}},
            sort=[("last_updated", DESCENDING)],
        )
        for run in active_runs:
            for task in run["tasks"]:
                if task["active"]:
                    machine = copy.copy(task["worker_info"])
                    machine["last_updated"] = task.get("last_updated", None)
                    machine["run"] = run
                    machines.append(machine)
        return machines

    def get_pgn(self, pgn_id):
        pgn_id = pgn_id.split(".")[0]  # strip .pgn
        pgn = self.pgndb.find_one({"run_id": pgn_id})
        if pgn:
            return zlib.decompress(pgn["pgn_zip"]).decode()
        return None

    def get_pgn_100(self, skip):
        return [
            p["run_id"]
            for p in self.pgndb.find(skip=skip, limit=100, sort=[("_id", DESCENDING)])
        ]

    def upload_nn(self, userid, name, nn):
        self.nndb.insert_one({"user": userid, "name": name, "downloads": 0})
        # 'nn': Binary(zlib.compress(nn))})
        return {}

    def update_nn(self, net):
        net.pop("downloads", None)
        self.nndb.update_one({"name": net["name"]}, {"$set": net})

    def get_nn(self, name):
        # nn = self.nndb.find_one({'name': name})
        nn = self.nndb.find_one({"name": name}, {"nn": 0})
        if nn:
            self.nndb.update_one({"name": name}, {"$inc": {"downloads": 1}})
            return nn
        return None

    def get_nns(self, limit, skip=0):
        return [
            dict(n, time=n["_id"].generation_time)
            for n in self.nndb.find(
                {}, {"nn": 0}, limit=limit, skip=skip, sort=[("_id", DESCENDING)]
            )
        ]

    # Cache runs
    run_cache = {}
    run_cache_lock = threading.Lock()
    run_cache_write_lock = threading.Lock()

    timer = None

    # handle termination
    def exit_run(signum, frame):
        global last_rundb
        if last_rundb:
            last_rundb.flush_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, exit_run)
    signal.signal(signal.SIGTERM, exit_run)

    def get_run(self, r_id):
        with self.run_cache_lock:
            r_id = str(r_id)
            if r_id in self.run_cache:
                self.run_cache[r_id]["rtime"] = time.time()
                return self.run_cache[r_id]["run"]
            try:
                run = self.runs.find_one({"_id": ObjectId(r_id)})
                if DEBUG:
                    print("Load", r_id, flush=True)
                if run:
                    self.run_cache[r_id] = {
                        "rtime": time.time(),
                        "ftime": time.time(),
                        "run": run,
                        "dirty": False,
                    }
                return run
            except:
                return None

    def start_timer(self):
        self.timer = threading.Timer(1.0, self.flush_buffers)
        self.timer.start()

    def buffer(self, run, flush):
        with self.run_cache_lock:
            if self.timer is None:
                self.start_timer()
            r_id = str(run["_id"])
            if flush:
                self.run_cache[r_id] = {
                    "dirty": False,
                    "rtime": time.time(),
                    "ftime": time.time(),
                    "run": run,
                }
                with self.run_cache_write_lock:
                    self.runs.replace_one({"_id": ObjectId(r_id)}, run)
            else:
                if r_id in self.run_cache:
                    ftime = self.run_cache[r_id]["ftime"]
                else:
                    ftime = time.time()
                self.run_cache[r_id] = {
                    "dirty": True,
                    "rtime": time.time(),
                    "ftime": ftime,
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
            if entry is not None and entry["dirty"]:
                self.runs.replace_one({"_id": ObjectId(r_id)}, entry["run"])
                print(".", end="", flush=True)
        print("done", flush=True)

    def flush_buffers(self):
        if self.timer is None:
            return
        try:
            self.run_cache_lock.acquire()
            now = time.time()
            old = now + 1
            oldest = None
            for r_id in list(self.run_cache):
                if not self.run_cache[r_id]["dirty"]:
                    if not self.run_cache[r_id]["run"].get("finished", False) and (
                        "scavenge" not in self.run_cache[r_id]
                        or self.run_cache[r_id]["scavenge"] < now - 60
                    ):
                        self.run_cache[r_id]["scavenge"] = now
                        if self.scavenge(self.run_cache[r_id]["run"]):
                            with self.run_cache_write_lock:
                                self.runs.replace_one(
                                    {"_id": ObjectId(r_id)}, self.run_cache[r_id]["run"]
                                )
                    if self.run_cache[r_id]["rtime"] < now - 300:
                        del self.run_cache[r_id]
                elif self.run_cache[r_id]["ftime"] < old:
                    old = self.run_cache[r_id]["ftime"]
                    oldest = r_id
            # print(oldest)
            if oldest is not None:
                self.scavenge(self.run_cache[oldest]["run"])
                self.run_cache[oldest]["scavenge"] = now
                self.run_cache[oldest]["dirty"] = False
                self.run_cache[oldest]["ftime"] = time.time()
                # print("SYNC")
                with self.run_cache_write_lock:
                    self.runs.replace_one(
                        {"_id": ObjectId(oldest)}, self.run_cache[oldest]["run"]
                    )
        except:
            print("Flush exception", flush=True)
        finally:
            # Restart timer:
            self.run_cache_lock.release()
            self.start_timer()

    def scavenge(self, run):
        if datetime.utcnow() < boot_time + timedelta(seconds=150):
            return False
        # print("scavenge ", run["_id"])
        dead_task = False
        old = datetime.utcnow() - timedelta(minutes=3)
        task_id = -1
        run_id = str(run["_id"])
        for task in run["tasks"]:
            task_id += 1
            if task["active"] and task["last_updated"] < old:
                task["active"] = False
                dead_task = True
                print(
                    "dead task: run: https://tests.stockfishchess.org/tests/view/{} task_id: {} worker: {}".format(
                        run["_id"], task_id, worker_name(task["worker_info"])
                    ),
                    flush=True,
                )
                run = del_tasks(run)
                run["dead_task"] = "task_id: {}, worker: {}".format(
                    task_id, worker_name(task["worker_info"])
                )
                self.actiondb.dead_task(task["worker_info"]["username"], run)
        return dead_task

    def get_unfinished_runs_id(self):
        with self.run_cache_write_lock:
            unfinished_runs = self.runs.find(
                {"finished": False}, {"_id": 1}, sort=[("last_updated", DESCENDING)]
            )
            return unfinished_runs

    def get_unfinished_runs(self, username=None):
        with self.run_cache_write_lock:
            unfinished_runs = self.runs.find(
                {"finished": False}, sort=[("last_updated", DESCENDING)]
            )
            if username:
                unfinished_runs = [
                    r for r in unfinished_runs if r["args"].get("username") == username
                ]
            return unfinished_runs

    def aggregate_unfinished_runs(self, username=None):
        unfinished_runs = self.get_unfinished_runs(username)
        runs = {"pending": [], "active": []}
        for run in unfinished_runs:
            state = (
                "active" if any(task["active"] for task in run["tasks"]) else "pending"
            )
            if state == "pending":
                run["cores"] = 0
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
        for m in self.get_machines():
            concurrency = int(m["concurrency"])
            cores += concurrency
            nps += concurrency * m["nps"]
        pending_hours = 0
        for run in runs["pending"] + runs["active"]:
            if cores > 0:
                eta = remaining_hours(run) / cores
                pending_hours += eta
            results = self.get_results(run, False)
            run["results_info"] = format_results(results, run)
            if "Pending..." in run["results_info"]["info"]:
                if cores > 0:
                    run["results_info"]["info"][0] += " ({:.1f} hrs)".format(eta)
                if "sprt" in run["args"]:
                    sprt = run["args"]["sprt"]
                    elo_model = sprt.get("elo_model", "BayesElo")
                    run["results_info"]["info"].append(
                        format_bounds(elo_model, sprt["elo0"], sprt["elo1"])
                    )
        return (runs, pending_hours, cores, nps)

    def get_finished_runs(
        self,
        skip=0,
        limit=0,
        username="",
        success_only=False,
        yellow_only=False,
        ltc_only=False,
    ):
        q = {"finished": True}
        idx_hint = "finished_runs"
        if username:
            q["args.username"] = username
            idx_hint = None
        if ltc_only:
            q["tc_base"] = {"$gte": 40}
            idx_hint = "finished_ltc_runs"
        if success_only:
            q["is_green"] = True
            idx_hint = "finished_green_runs"
        if yellow_only:
            q["is_yellow"] = True
            idx_hint = "finished_yellow_runs"

        c = self.runs.find(
            q, skip=skip, limit=limit, sort=[("last_updated", DESCENDING)]
        )

        if idx_hint == "finished_runs":
            # Use a fast COUNT_SCAN query when possible
            count = self.runs.estimated_document_count()
            q = {"finished": False}
            uf = self.runs.count_documents(q, hint="unfinished_runs")
            count -= uf
            # Otherwise, the count is slow
        elif idx_hint is not None:
            count = self.runs.count_documents(q, hint=idx_hint)
        else:
            count = self.runs.count_documents(q)

        # Don't show runs that were deleted
        runs_list = [run for run in c if not run.get("deleted")]
        return [runs_list, count]

    def get_results(self, run, save_run=True):
        if not run["results_stale"]:
            return run["results"]

        results = {"wins": 0, "losses": 0, "draws": 0, "crashes": 0, "time_losses": 0}

        has_pentanomial = True
        pentanomial = 5 * [0]
        for task in run["tasks"]:
            if "stats" in task:
                stats = task["stats"]
                results["wins"] += stats["wins"]
                results["losses"] += stats["losses"]
                results["draws"] += stats["draws"]
                results["crashes"] += stats.get("crashes", 0)
                results["time_losses"] += stats.get("time_losses", 0)
                if "pentanomial" in stats.keys() and has_pentanomial:
                    pentanomial = [
                        pentanomial[i] + stats["pentanomial"][i] for i in range(0, 5)
                    ]
                else:
                    has_pentanomial = False
        if has_pentanomial:
            results["pentanomial"] = pentanomial

        run["results_stale"] = False
        run["results"] = results
        if save_run:
            self.buffer(run, True)

        return results

    def calc_itp(self, run):
        itp = run["args"]["throughput"]
        if itp < 1:
            itp = 1
        elif itp > 500:
            itp = 500
        itp *= math.sqrt(
            estimate_game_duration(run["args"]["tc"]) / estimate_game_duration("10+0.1")
        )
        itp *= math.sqrt(run["args"]["threads"])
        if "sprt" not in run["args"]:
            itp *= 0.5
        else:
            llr = run["args"]["sprt"].get("llr", 0)
            itp *= (5 + llr) / 5
        run["args"]["itp"] = itp

    def sum_cores(self, run):
        cores = 0
        for task in run["tasks"]:
            if task["active"]:
                cores += int(task["worker_info"]["concurrency"])
        run["cores"] = cores

    # Limit concurrent request_task
    task_lock = threading.Lock()
    task_semaphore = threading.Semaphore(4)

    task_time = 0
    task_runs = None

    worker_runs = {}

    def worker_cap(self, run, worker_info):
        # Estimate how many games a worker will be able to run
        # during the time interval determined by "self.task_duration".
        # Make sure the result is properly quantized and not zero.

        game_time = estimate_game_duration(run["args"]["tc"])
        concurrency = worker_info["concurrency"] // run["args"]["threads"]
        assert concurrency >= 1
        games = self.task_duration / game_time * concurrency
        if "sprt" in run["args"]:
            batch_size = 2 * run["args"]["sprt"].get("batch_size", 1)
            games = max(batch_size, batch_size * int(games / batch_size + 1 / 2))
        else:
            games = max(2, 2 * int(games / 2 + 1 / 2))
        return games

    def request_task(self, worker_info):
        if self.task_semaphore.acquire(False):
            try:
                with self.task_lock:
                    return self.sync_request_task(worker_info)
            finally:
                self.task_semaphore.release()
        else:
            print("request_task too busy", flush=True)
            return {"task_waiting": False}

    def sync_request_task(self, worker_info):

        unique_key = worker_info["unique_key"]

        # We get the list of unfinished runs.
        # To limit db access the list is cached for
        # 60 seconds.

        runs_finished = True
        for run in self.task_runs:
            if not run["finished"]:
                runs_finished = False
                break

        if runs_finished:
            print("Request_task: no useful cached runs left", flush=True)

        if runs_finished or time.time() > self.task_time + 60:
            print("Request_task: refresh queue", flush=True)
            self.task_runs = []
            for r in self.get_unfinished_runs_id():
                run = self.get_run(r["_id"])
                self.sum_cores(run)
                self.calc_itp(run)
                self.task_runs.append(run)
            self.task_time = time.time()

        # We sort the list of unfinished runs according to priority.
        # Note that because of the caching, the properties of the
        # runs may have changed, so resorting is necessary.
        # Changes can be created by the code below or else in update_task().
        # Note that update_task() uses the same objects as here
        # (they are not copies).

        last_run_id = self.worker_runs.get(unique_key, {}).get("last_run", None)

        def priority(run):  # lower is better
            return (
                -run["args"]["priority"],
                # Try to find a new run for this worker.
                run["_id"] == last_run_id,
                run["cores"] / run["args"]["itp"] * 100.0,
                -run["args"]["itp"],
                run["_id"],
            )

        self.task_runs.sort(key=priority)

        # We go through the list of unfinished runs to see if the worker
        # has reached the number of allowed connections from the same ip
        # address.

        connections = 0
        for run in self.task_runs:
            for task in run["tasks"]:
                if (
                    task["active"]
                    and task["worker_info"]["remote_addr"] == worker_info["remote_addr"]
                ):
                    connections = connections + 1

        if connections >= self.userdb.get_machine_limit(worker_info["username"]):
            error = "Request_task: Machine limit reached for user {}".format(
                worker_info["username"]
            )
            print(error, flush=True)
            return {"task_waiting": False, "error": error}

        # Collect some data about the worker that will be used below.

        # Memory
        max_threads = int(worker_info["concurrency"])
        min_threads = int(worker_info.get("min_threads", 1))
        max_memory = int(worker_info.get("max_memory", 0))

        # Is the worker near the github api limit?
        if "rate" in worker_info:
            rate = worker_info["rate"]
            near_github_api_limit = rate["remaining"] <= 2 * math.sqrt(rate["limit"])
        else:
            near_github_api_limit = False

        # Now go through the sorted list of unfinished runs.
        # We will add a task to the first run that is suitable.

        run_found = False

        for run in self.task_runs:
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
            committed_games = 0
            for task in run["tasks"]:
                if not task["active"]:
                    if "stats" in task:
                        stats = task["stats"]
                        committed_games += (
                            stats["wins"] + stats["losses"] + stats["draws"]
                        )
                else:
                    committed_games += task["num_games"]

            remaining = run["args"]["num_games"] - committed_games
            if remaining <= 0:
                continue

            # We check if the worker has reserved enough memory
            need_tt = 0
            need_base = 0
            if max_memory > 0:

                def get_hash(s):
                    h = re.search("Hash=([0-9]+)", s)
                    if h:
                        return int(h.group(1))
                    return 0

                need_tt += get_hash(run["args"]["new_options"])
                need_tt += get_hash(run["args"]["base_options"])
                need_tt *= max_threads // run["args"]["threads"]
                # estime another 70MB per process for net (40) and other things besides hash
                need_base = 2 * 70 * (max_threads // run["args"]["threads"])

            if need_base + need_tt > max_memory:
                continue

            # Github API limit...
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
            if max_threads > 32:
                if "windows" in worker_info["uname"].lower():
                    short_tc = estimate_game_duration(
                        run["args"]["tc"]
                    ) <= estimate_game_duration("55+0.5")
                else:
                    short_tc = estimate_game_duration(run["args"]["tc"]) * run["args"][
                        "threads"
                    ] <= estimate_game_duration("30+0.3")
                if short_tc:
                    continue

            # Limit the number of cores.
            # Currently this is only done for spsa.
            if "spsa" in run["args"]:
                limit_cores = 40000 / math.sqrt(len(run["args"]["spsa"]["params"]))
            else:
                limit_cores = 1000000  # infinity

            cores = 0
            core_limit_reached = False
            for task in run["tasks"]:
                if task["active"]:
                    cores += task["worker_info"]["concurrency"]
                    if cores > limit_cores:
                        core_limit_reached = True
                        break

            if core_limit_reached:
                continue

            # If we make it here, it means we have found a run
            # suitable for a new task.
            run_found = True
            break

        # If there is no suitable run, tell the worker.
        if not run_found:
            return {"task_waiting": False}

        # Now we create a new task for this run.
        opening_offset = 0
        for task in run["tasks"]:
            opening_offset += task["num_games"]

        task_size = min(self.worker_cap(run, worker_info), remaining)
        task = {
            "num_games": task_size,
            "active": True,
            "worker_info": worker_info,
            "last_updated": datetime.utcnow(),
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

        task_id = len(run["tasks"]) - 1

        run["cores"] += task["worker_info"]["concurrency"]
        self.buffer(run, False)

        # Cache some data. Currently we record the id's
        # the worker has seen, as well as the last id that was seen.
        # Note that "worker_runs" is empty after a server restart.

        if unique_key not in self.worker_runs:
            self.worker_runs[unique_key] = {}

        if run["_id"] not in self.worker_runs[unique_key]:
            self.worker_runs[unique_key][run["_id"]] = True

        self.worker_runs[unique_key]["last_run"] = run["_id"]

        if DEBUG:
            print(
                "Allocate run: https://tests.stockfishchess.org/tests/view/{} task_id: {} to {}/{} Stats: {}".format(
                    run["_id"],
                    task_id,
                    worker_info["username"],
                    unique_key,
                    run["tasks"][task_id]["stats"],
                ),
                flush=True,
            )
        return {"run": run, "task_id": task_id}

    # Create a lock for each active run
    run_lock = threading.Lock()
    active_runs = {}
    purge_count = 0

    def active_run_lock(self, id):
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
                active_lock = threading.Lock()
                self.active_runs[id] = {"time": time.time(), "lock": active_lock}
            return active_lock

    def update_task(self, worker_info, run_id, task_id, stats, spsa):
        lock = self.active_run_lock(str(run_id))
        with lock:
            return self.sync_update_task(worker_info, run_id, task_id, stats, spsa)

    def sync_update_task(self, worker_info, run_id, task_id, stats, spsa):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        update_time = datetime.utcnow()

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
            print(info, flush=True)
            task["active"] = False
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
            task["active"] = False
            return {"task_alive": False, "error": error}

        # The update seems fine. Update run["tasks"][task_id] (=task).

        task["stats"] = stats
        task["last_updated"] = update_time
        task["worker_info"] = worker_info  # updates rate, ARCH, nps

        task_finished = False
        if num_games >= task["num_games"]:
            # This task is now finished
            task_finished = True
            task["active"] = False

        # Now update the current run.

        run["last_updated"] = update_time

        if task_finished:
            # run["cores"] is also updated in request_task().
            # We use the same lock.
            with self.task_lock:
                run["cores"] -= task["worker_info"]["concurrency"]
                assert run["cores"] >= 0

        run["results_stale"] = True  # force recalculation of results
        updated_results = self.get_results(
            run, False
        )  # computed from run["tasks"] which
        # has just been updated. Sets run["results_stale"]=False.

        if "sprt" in run["args"]:
            sprt = run["args"]["sprt"]
            fishtest.stats.stat_util.update_SPRT(updated_results, sprt)

        if "spsa" in run["args"] and spsa_games == spsa["num_games"]:
            self.update_spsa(task["worker_info"]["unique_key"], run, spsa)

        # Check if the run is finished.

        run_finished = False
        if count_games(updated_results) >= run["args"]["num_games"]:
            run_finished = True
        elif "sprt" in run["args"] and sprt["state"] != "":
            run_finished = True

        # Return.

        if run_finished:
            self.buffer(run, True)
            self.stop_run(run_id)
            ret = {"task_alive": False}
        else:
            self.buffer(run, False)
            ret = {"task_alive": task["active"]}

        return ret

    def upload_pgn(self, run_id, pgn_zip):
        self.pgndb.insert_one({"run_id": run_id, "pgn_zip": Binary(pgn_zip)})
        return {}

    def failed_task(self, run_id, task_id, message="Unknown reason"):
        run = self.get_run(run_id)
        task = run["tasks"][task_id]
        # Check if the worker is still working on this task.
        if not task["active"]:
            info = "Failed_task: task {}/{} is not active".format(run_id, task_id)
            print(info, flush=True)
            return {"task_alive": False, "info": info}
        # Mark the task as inactive.
        task["active"] = False
        self.buffer(run, False)
        print(
            "Failed_task: failure for: https://tests.stockfishchess.org/tests/view/{}, "
            "task_id: {}, worker: {}, reason: '{}'".format(
                run_id, task_id, worker_name(task["worker_info"]), message
            ),
            flush=True,
        )
        run = del_tasks(run)
        run["failure_reason"] = "task_id: {}, worker: {}, reason: '{}'".format(
            task_id, worker_name(task["worker_info"]), message[:1024]
        )
        self.actiondb.failed_task(task["worker_info"]["username"], run)
        return {}

    def stop_run(self, run_id, run=None):
        """Stops a run and runs auto-purge if it was enabled
        - Used by the website and API for manually stopping runs
        - Called during /api/update_task:
          - for stopping SPRT runs if the test is accepted or rejected
          - for stopping a run after all games are finished
        """
        self.clear_params(run_id)
        save_it = False
        if run is None:
            run = self.get_run(run_id)
            save_it = True
        run["tasks"] = [task for task in run["tasks"] if "stats" in task]
        for task in run["tasks"]:
            task["active"] = False
        if save_it:
            self.buffer(run, True)
            self.task_time = 0
            # Auto-purge runs here
            purged = False
            if run["args"].get("auto_purge", True) and "spsa" not in run["args"]:
                if self.purge_run(run):
                    purged = True
                    run = self.get_run(run["_id"])
                    results = self.get_results(run, True)
                    run["results_info"] = format_results(results, run)
                    self.buffer(run, True)
            if not purged:
                # The run is now finished and will no longer be updated after this
                run["finished"] = True
                results = self.get_results(run, True)
                run["results_info"] = format_results(results, run)
                # De-couple the styling of the run from its finished status
                if run["results_info"]["style"] == "#44EB44":
                    run["is_green"] = True
                elif run["results_info"]["style"] == "yellow":
                    run["is_yellow"] = True
                self.buffer(run, True)
                # Publish the results of the run to the Fishcooking forum
                post_in_fishcooking_results(run)

    def approve_run(self, run_id, approver):
        run = self.get_run(run_id)
        # Can't self approve
        if run["args"]["username"] == approver:
            return False

        run["approved"] = True
        run["approver"] = approver
        self.buffer(run, True)
        self.task_time = 0
        return True

    def purge_run(self, run, p=0.001, res=7.0, iters=1):
        now = datetime.utcnow()
        if "start_time" not in run or (now - run["start_time"]).days > 30:
            return False
        # Do not revive failed runs
        if run.get("failed", False):
            return False
        # Remove bad tasks
        purged = False
        if "bad_tasks" not in run:
            run["bad_tasks"] = []

        tasks = copy.copy(run["tasks"])
        for task in tasks:
            # Special cases: crashes or time losses.
            if crash_or_time(task):
                purged = True
                # The next two lines are a bit hacky but
                # the correct residual and color may not have
                # been set yet.
                task["residual"] = 10.0
                task["residual_color"] = "#FF6A6A"
                task["bad"] = True
                run["bad_tasks"].append(task)
                run["tasks"].remove(task)

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
            iters=iters - 1 if purged else iters,
        )
        tasks = copy.copy(run["tasks"])
        for task in tasks:
            if unique_key_(task["worker_info"]) in bad_workers:
                purged = True
                task["bad"] = True
                run["bad_tasks"].append(task)
                run["tasks"].remove(task)
        if purged:
            run["results_stale"] = True
            results = self.get_results(run)
            run["finished"] = False
            run["is_green"] = False
            run["is_yellow"] = False
            if "sprt" in run["args"] and "state" in run["args"]["sprt"]:
                fishtest.stats.stat_util.update_SPRT(results, run["args"]["sprt"])
                run["args"]["sprt"]["state"] = ""
            self.buffer(run, True)
        return purged

    def spsa_param_clip_round(self, param, increment, clipping, rounding):
        if clipping == "old":
            value = param["theta"] + increment
            if value < param["min"]:
                value = param["min"]
            elif value > param["max"]:
                value = param["max"]
        else:  # clipping == 'careful':
            inc = min(
                abs(increment),
                abs(param["theta"] - param["min"]) / 2,
                abs(param["theta"] - param["max"]) / 2,
            )
            if inc > 0:
                value = param["theta"] + inc * increment / abs(increment)
            else:  # revert to old behavior to bounce off boundary
                value = param["theta"] + increment
                if value < param["min"]:
                    value = param["min"]
                elif value > param["max"]:
                    value = param["max"]

        # 'deterministic' rounding calls round() inside the worker.
        # 'randomized' says 4.p should be 5 with probability p,
        # 4 with probability 1-p,
        # and is continuous (albeit after expectation) unlike round().
        if rounding == "randomized":
            value = math.floor(value + random.uniform(0, 1))

        return value

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
        if "clipping" not in spsa:
            spsa["clipping"] = "old"
        if "rounding" not in spsa:
            spsa["rounding"] = "deterministic"

        # Generate the next set of tuning parameters
        iter_local = spsa["iter"] + 1  # assume at least one completed,
        # and avoid division by zero
        for param in spsa["params"]:
            c = param["c"] / iter_local ** spsa["gamma"]
            flip = 1 if random.getrandbits(1) else -1
            result["w_params"].append(
                {
                    "name": param["name"],
                    "value": self.spsa_param_clip_round(
                        param, c * flip, spsa["clipping"], spsa["rounding"]
                    ),
                    "R": param["a"]
                    / (spsa["A"] + iter_local) ** spsa["alpha"]
                    / c ** 2,
                    "c": c,
                    "flip": flip,
                }
            )
            result["b_params"].append(
                {
                    "name": param["name"],
                    "value": self.spsa_param_clip_round(
                        param, -c * flip, spsa["clipping"], spsa["rounding"]
                    ),
                }
            )

        return result

    def update_spsa(self, worker, run, spsa_results):
        spsa = run["args"]["spsa"]
        if "clipping" not in spsa:
            spsa["clipping"] = "old"

        spsa["iter"] += int(spsa_results["num_games"] / 2)

        # Store the history every 'freq' iterations.
        # More tuned parameters result in a lower update frequency,
        # so that the required storage (performance) remains constant.
        if "param_history" not in spsa:
            spsa["param_history"] = []
        L = len(spsa["params"])
        freq_max = 250000
        freq = max(100, min(L * 25, freq_max))

        # adjust freq to multiples of 100 that divide exactly into freq_max
        freq_div = (i for i in range(100, freq_max + 1, 100) if not freq_max % i)
        freq = max(i for i in freq_div if i <= freq)

        maxlen = freq_max / freq
        grow_summary = len(spsa["param_history"]) < min(maxlen, spsa["iter"] / freq)

        # Update the current theta based on the results from the worker
        # Worker wins/losses are always in terms of w_params
        result = spsa_results["wins"] - spsa_results["losses"]
        summary = []
        w_params = self.get_params(run["_id"], worker)
        for idx, param in enumerate(spsa["params"]):
            R = w_params[idx]["R"]
            c = w_params[idx]["c"]
            flip = w_params[idx]["flip"]
            param["theta"] = self.spsa_param_clip_round(
                param, R * c * result * flip, spsa["clipping"], "deterministic"
            )
            if grow_summary:
                summary.append({"theta": param["theta"], "R": R, "c": c})

        if grow_summary:
            spsa["param_history"].append(summary)
