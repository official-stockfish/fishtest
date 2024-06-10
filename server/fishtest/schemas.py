# This file describes some of the data structures used by Fishtest so that they
# can be statically validated before they are processed further or written
# to the database.
#
# See https://github.com/vdbergh/vtjson for a description of the schema format.

import copy
import math
from datetime import datetime, timezone

from bson.binary import Binary
from bson.objectid import ObjectId
from vtjson import (
    anything,
    at_least_one_of,
    at_most_one_of,
    cond,
    div,
    email,
    fields,
    ge,
    glob,
    gt,
    ifthen,
    intersect,
    ip_address,
    keys,
    lax,
    magic,
    nothing,
    number,
    one_of,
    quote,
    regex,
    set_label,
    set_name,
    size,
    union,
    url,
)

run_id = intersect(str, set_name(ObjectId.is_valid, "valid_object_id"))
run_id_pgns = regex(r"[a-f0-9]{24}-(0|[1-9]\d*)", name="run_id_pgns")
run_name = intersect(regex(r".*-[a-f0-9]{7}", name="run_name"), size(0, 23 + 1 + 7))
action_message = intersect(str, size(0, 1024))
worker_message = intersect(str, size(0, 500))
short_worker_name = regex(r".*-[\d]+cores-[a-zA-Z0-9]{2,8}", name="short_worker_name")
long_worker_name = regex(
    r".*-[\d]+cores-[a-zA-Z0-9]{2,8}-[a-f0-9]{4}\*?", name="long_worker_name"
)
username = regex(r"[!-~][ -~]{0,30}[!-~]", name="username")
net_name = regex(r"nn-[a-f0-9]{12}.nnue", name="net_name")
tc = regex(r"([1-9]\d*/)?\d+(\.\d+)?(\+\d+(\.\d+)?)?", name="tc")
str_int = regex(r"[1-9]\d*", name="str_int")
sha = regex(r"[a-f0-9]{40}", name="sha")
uuid = regex(r"[0-9a-zA-Z]{2,8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}", name="uuid")
country_code = regex(r"[A-Z][A-Z]", name="country_code")
epd_file = glob("*.epd", name="epd_file")
pgn_file = glob("*.pgn", name="pgn_file")
even = div(2, name="even")
datetime_utc = intersect(datetime, fields({"tzinfo": timezone.utc}))
gzip_data = magic("application/gzip", name="gzip_data")

uint = intersect(int, ge(0))
suint = intersect(int, gt(0))
ufloat = intersect(float, ge(0))
unumber = intersect(number, ge(0))
sunumber = intersect(number, gt(0))


def size_is_length(x):
    return x["size"] == len(x["pgn_zip"])


pgns_schema = intersect(
    {
        "_id?": ObjectId,
        "run_id": run_id_pgns,
        "pgn_zip": intersect(Binary, gzip_data),
        "size": uint,
    },
    size_is_length,
)

user_schema = {
    "_id?": ObjectId,
    "username": username,
    "password": str,
    "registration_time": datetime_utc,
    "pending": bool,
    "blocked": bool,
    "email": email,
    "groups": [str, ...],
    "tests_repo": union("", url),
    "machine_limit": uint,
}


worker_schema = {
    "_id?": ObjectId,
    "worker_name": short_worker_name,
    "blocked": bool,
    "message": worker_message,
    "last_updated": datetime_utc,
}


def first_test_before_last(x):
    f = x["first_test"]["date"]
    l = x["last_test"]["date"]
    if f <= l:
        return True
    else:
        raise Exception(
            f"The first test at {str(f)} is later than the last test at {str(l)}"
        )


nn_schema = intersect(
    {
        "_id?": ObjectId,
        "downloads": uint,
        "first_test?": {"date": datetime_utc, "id": run_id},
        "is_master?": True,
        "last_test?": {"date": datetime_utc, "id": run_id},
        "name": net_name,
        "user": username,
    },
    ifthen(
        at_least_one_of("is_master", "first_test", "last_test"),
        intersect(
            keys("first_test", "last_test"),
            first_test_before_last,
        ),
    ),
)

# not yet used, not tested
contributors_schema = {
    "_id": ObjectId,
    "cpu_hours": unumber,
    "diff": unumber,
    "games": uint,
    "games_per_hour": unumber,
    "last_updated": datetime_utc,
    "str_last_updated": str,
    "tests": uint,
    "tests_repo": union(url, ""),
    "username": username,
}


action_name = set_name(
    union(
        "failed_task",
        "crash_or_time",
        "dead_task",
        "system_event",
        "new_run",
        "upload_nn",
        "modify_run",
        "delete_run",
        "stop_run",
        "finished_run",
        "approve_run",
        "purge_run",
        "block_user",
        "accept_user",
        "block_worker",
        "log_message",
    ),
    "action_name",
)


def action_is(x):
    return lax({"action": x})


action_schema = intersect(
    # First make sure that we recognize the action name.
    lax(
        {
            "action": action_name,
        }
    ),
    # For every action name introduce a specific schema.
    cond(
        (
            action_is("failed_task"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "failed_task",
                "username": username,
                "worker": long_worker_name,
                "run_id": run_id,
                "run": run_name,
                "task_id": uint,
                "message": action_message,
            },
        ),
        (
            action_is("crash_or_time"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "crash_or_time",
                "username": username,
                "worker": long_worker_name,
                "run_id": run_id,
                "run": run_name,
                "task_id": uint,
                "message": action_message,
            },
        ),
        (
            action_is("dead_task"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "dead_task",
                "username": username,
                "worker": long_worker_name,
                "run_id": run_id,
                "run": run_name,
                "task_id": uint,
            },
        ),
        (
            action_is("system_event"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "system_event",
                "username": "fishtest.system",
                "message": action_message,
            },
        ),
        (
            action_is("new_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "new_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
                "message": action_message,
            },
        ),
        (
            action_is("upload_nn"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "upload_nn",
                "username": username,
                "nn": net_name,
            },
        ),
        (
            action_is("modify_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "modify_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
                "message": action_message,
            },
        ),
        (
            action_is("delete_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "delete_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
            },
        ),
        (
            action_is("stop_run"),
            intersect(
                {
                    "_id?": ObjectId,
                    "time": float,
                    "action": "stop_run",
                    "username": username,
                    "run_id": run_id,
                    "run": run_name,
                    "message": action_message,
                    "worker?": long_worker_name,
                    "task_id?": uint,
                },
                ifthen(at_least_one_of("worker", "task_id"), keys("worker", "task_id")),
            ),
        ),
        (
            action_is("finished_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "finished_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
                "message": action_message,
            },
        ),
        (
            action_is("approve_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "approve_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
                "message": union("approved", "unapproved"),
            },
        ),
        (
            action_is("purge_run"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "purge_run",
                "username": username,
                "run_id": run_id,
                "run": run_name,
                "message": action_message,
            },
        ),
        (
            action_is("block_user"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "block_user",
                "username": username,
                "user": str,
                "message": union("blocked", "unblocked"),
            },
        ),
        (
            action_is("accept_user"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "accept_user",
                "username": username,
                "user": str,
                "message": "accepted",
            },
        ),
        (
            action_is("block_worker"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "block_worker",
                "username": username,
                "worker": short_worker_name,
                "message": union("blocked", "unblocked"),
            },
        ),
        (
            action_is("log_message"),
            {
                "_id?": ObjectId,
                "time": float,
                "action": "log_message",
                "username": username,
                "message": action_message,
            },
        ),
        # we should never get here
        (anything, nothing),
    ),
)


worker_info_schema_api = {
    "uname": str,
    "architecture": [str, str],
    "concurrency": suint,
    "max_memory": uint,
    "min_threads": suint,
    "username": username,
    "version": uint,
    "python_version": [uint, uint, uint],
    "gcc_version": [uint, uint, uint],
    "compiler": union("clang++", "g++"),
    "unique_key": uuid,
    "modified": bool,
    "ARCH": str,
    "nps": unumber,
    "near_github_api_limit": bool,
}

worker_info_schema_runs = copy.deepcopy(worker_info_schema_api)
worker_info_schema_runs.update(
    {"remote_addr": ip_address, "country_code": union(country_code, "?")}
)


def valid_results(R):
    l, d, w = R["losses"], R["draws"], R["wins"]
    R = R["pentanomial"]
    return (
        l + d + w == 2 * sum(R)
        and w - l == 2 * R[4] + R[3] - R[1] - 2 * R[0]
        and R[3] + 2 * R[2] + R[1] >= d >= R[3] + R[1]
    )


results_schema = intersect(
    {
        "wins": uint,
        "losses": uint,
        "draws": uint,
        "crashes": uint,
        "time_losses": uint,
        "pentanomial": [uint, uint, uint, uint, uint],
    },
    valid_results,
)


def valid_spsa_results(R):
    return R["wins"] + R["losses"] + R["draws"] == R["num_games"]


api_access_schema = lax({"password": str, "worker_info": {"username": username}})

api_schema = intersect(
    {
        "password": str,
        "run_id?": run_id,
        "task_id?": uint,
        "pgn?": str,
        "message?": str,
        "worker_info": worker_info_schema_api,
        "spsa?": intersect(
            {
                "wins": uint,
                "losses": uint,
                "draws": uint,
                "num_games": intersect(uint, even),
            },
            valid_spsa_results,
        ),
        "stats?": results_schema,
    },
    ifthen(keys("task_id"), keys("run_id")),
)


zero_results = {
    "wins": 0,
    "draws": 0,
    "losses": 0,
    "crashes": 0,
    "time_losses": 0,
    "pentanomial": 5 * [0],
}


if_bad_then_zero_stats_and_not_active = ifthen(
    keys("bad"), lax({"active": False, "stats": quote(zero_results)})
)


def compute_results(run):
    rr = copy.deepcopy(zero_results)
    for t in run["tasks"]:
        r = t["stats"]
        for k in r:
            if k != "pentanomial":
                rr[k] += r[k]
            else:
                for i, p in enumerate(r["pentanomial"]):
                    rr[k][i] += p
    return rr


def compute_cores(run):
    cores = 0
    for t in run["tasks"]:
        if t["active"]:
            cores += t["worker_info"]["concurrency"]
    return cores


def compute_workers(run):
    workers = 0
    for t in run["tasks"]:
        if t["active"]:
            workers += 1
    return workers


def compute_committed_games(run):
    committed_games = 0
    for task in run["tasks"]:
        if not task["active"]:
            if "stats" in task:
                stats = task["stats"]
                committed_games += stats["wins"] + stats["losses"] + stats["draws"]
        else:
            committed_games += task["num_games"]
    return committed_games


def compute_total_games(run):
    total_games = 0
    for t in run["tasks"]:
        total_games += t["num_games"]
    return total_games


def final_results_must_match(run):
    results = compute_results(run)
    if results != run["results"]:
        raise Exception(
            f"The final results {run['results']} do not match the computed results {results}"
        )

    return True


def cores_must_match(run):
    cores = compute_cores(run)
    if cores != run["cores"]:
        raise Exception(
            f"Cores from tasks: {cores}. Cores from " f"run: {run['cores']}"
        )

    return True


def workers_must_match(run):
    workers = compute_workers(run)
    if workers != run["workers"]:
        raise Exception(
            f"Workers mismatch. Workers from tasks: {workers}. Workers from "
            f"run: {run['workers']}"
        )

    return True


def committed_games_must_match(run):
    committed_games = compute_committed_games(run)
    if committed_games != run["committed_games"]:
        raise Exception(
            f"Committed games mismatch. Committed games from tasks: {committed_games}. Committed games from "
            f"run: {run['committed_games']}"
        )

    return True


def total_games_must_match(run):
    total_games = compute_total_games(run)
    if total_games != run["total_games"]:
        raise Exception(
            f"Total games mismatch. Total games from tasks: {total_games}. Total games from "
            f"run: {run['total_games']}"
        )

    return True


valid_aggregated_data = intersect(
    final_results_must_match,
    cores_must_match,
    workers_must_match,
    committed_games_must_match,
    total_games_must_match,
)

# The following schema only matches new runs. The old runs
# are not compatible with it. For documentation purposes
# it would also be useful to have a "universal schema"
# that matches all the runs in the db.

# Please increment this if the format of the run schema
# changes. This will suppress spurious event log messages
# about non-validation of runs created with the prior
# schema.

RUN_VERSION = 1

runs_schema = intersect(
    {
        "_id?": ObjectId,
        "version": uint,
        "start_time": datetime_utc,
        "last_updated": datetime_utc,
        "tc_base": unumber,
        "base_same_as_master": bool,
        "rescheduled_from?": run_id,
        "approved": bool,
        "approver": union(username, ""),
        "finished": bool,
        "deleted": bool,
        "failed": bool,
        "is_green": bool,
        "is_yellow": bool,
        "workers": uint,
        "cores": uint,
        "committed_games": uint,
        "total_games": uint,
        "results": results_schema,
        "results_info?": {
            "style": str,
            "info": [str, ...],
        },
        "args": intersect(
            {
                "base_tag": str,
                "new_tag": str,
                "base_nets": [net_name, ...],
                "new_nets": [net_name, ...],
                "num_games": intersect(uint, even),
                "tc": tc,
                "new_tc": tc,
                "book": union(epd_file, pgn_file),
                "book_depth": str_int,
                "threads": suint,
                "resolved_base": sha,
                "resolved_new": sha,
                "master_sha": sha,
                "official_master_sha": sha,
                "msg_base": str,
                "msg_new": str,
                "base_options": str,
                "new_options": str,
                "info": str,
                "base_signature": str_int,
                "new_signature": str_int,
                "username": username,
                "tests_repo": url,
                "auto_purge": bool,
                "throughput": unumber,
                "itp": unumber,
                "priority": number,
                "adjudication": bool,
                "sprt?": intersect(
                    {
                        "alpha": 0.05,
                        "beta": 0.05,
                        "elo0": number,
                        "elo1": number,
                        "elo_model": "normalized",
                        "state": union("", "accepted", "rejected"),
                        "llr": number,
                        "batch_size": suint,
                        "lower_bound": -math.log(19),
                        "upper_bound": math.log(19),
                        "lost_samples?": uint,
                        "illegal_update?": uint,
                        "overshoot?": {
                            "last_update": uint,
                            "skipped_updates": uint,
                            "ref0": number,
                            "m0": number,
                            "sq0": unumber,
                            "ref1": number,
                            "m1": number,
                            "sq1": unumber,
                        },
                    },
                    one_of("overshoot", "lost_samples"),
                ),
                "spsa?": {
                    "A": unumber,
                    "alpha": unumber,
                    "gamma": unumber,
                    "raw_params": str,
                    "iter": uint,
                    "num_iter": uint,
                    "params": [
                        {
                            "name": str,
                            "start": number,
                            "min": number,
                            "max": number,
                            "c_end": sunumber,
                            "r_end": unumber,
                            "c": sunumber,
                            "a_end": unumber,
                            "a": unumber,
                            "theta": number,
                        },
                        ...,
                    ],
                    "param_history?": [
                        [
                            {"theta": number, "R": unumber, "c": unumber},
                            ...,
                        ],
                        ...,
                    ],
                },
            },
            at_most_one_of("sprt", "spsa"),
        ),
        "tasks": [
            intersect(
                {
                    "num_games": intersect(uint, even),
                    "active": bool,
                    "last_updated": datetime_utc,
                    "start": uint,
                    "residual?": number,
                    "residual_color?": str,
                    "bad?": True,
                    "stats": results_schema,
                    "worker_info": worker_info_schema_runs,
                },
                if_bad_then_zero_stats_and_not_active,
            ),
            ...,
        ],
        "bad_tasks?": [
            {
                "num_games": intersect(uint, even),
                "active": False,
                "last_updated": datetime_utc,
                "start": uint,
                "residual": number,
                "residual_color": str,
                "bad": True,
                "task_id": uint,
                "stats": results_schema,
                "worker_info": worker_info_schema_runs,
            },
            ...,
        ],
    },
    lax(ifthen({"approved": True}, {"approver": username}, {"approver": ""})),
    lax(ifthen({"is_green": True}, {"is_yellow": False})),
    lax(ifthen({"is_yellow": True}, {"is_green": False})),
    lax(
        ifthen(
            {"finished": False},
            {"is_green": False, "is_yellow": False, "failed": False, "deleted": False},
        )
    ),
    lax(
        ifthen(
            {"finished": True},
            {"workers": 0, "cores": 0, "tasks": [{"active": False}, ...]},
        )
    ),
    valid_aggregated_data,
)

cache_schema = {
    run_id: {
        "run": set_label(runs_schema, "runs_schema"),
        "is_changed": bool,  # Indicates if the run has changed since last_sync_time.
        "last_sync_time": ufloat,  # Last sync time (reading from or writing to db). If never synced then creation time.
        "last_access_time": ufloat,  # Last time the cache entry was touched (via buffer() or get_run()).
    },
}
