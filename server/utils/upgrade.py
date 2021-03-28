import copy
import datetime
import math
import os
import pprint
import uuid

import pymongo
from fishtest.stats import stat_util
from fishtest.util import format_results, worker_name


def show(p):
    pprint.pprint(p)


# for documentation
run_default = {
    "_id": "?",
    "args": {
        "base_tag": "?",
        "new_tag": "?",
        "base_net": "?",
        "new_net": "?",
        "num_games": 400000,
        "tc": "?",
        "new_tc": "?",
        "book": "?",
        "book_depth": "8",
        "threads": 1,
        "resolved_base": "?",
        "resolved_new": "?",
        "msg_base": "?",
        "msg_new": "?",
        "base_options": "?",
        "new_options": "?",
        "base_signature": "?",
        "new_signature": "?",
        "username": "Unknown user",
        "tests_repo": "?",
        "auto_purge": False,
        "throughput": 100,
        "itp": 100.0,
        "priority": 0,
        "adjudication": True,
    },
    "start_time": datetime.datetime.min,
    "last_updated": datetime.datetime.min,
    "tc_base": -1.0,
    "base_same_as_master": True,
    "results_stale": False,
    "finished": True,
    "approved": True,
    "approver": "?",
    "cores": 0,
    "results": {
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "crashes": 0,
        "time_losses": 0,
    },
}

worker_info_default = {
    "uname": "?",
    "architecture": ["?", "?"],
    "concurrency": 0,
    "max_memory": 0,
    "min_threads": 1,
    "username": "Unknown_worker",
    "version": 0,
    "python_version": [],
    "gcc_version": [],
    "unique_key": "xxxxxxxx",
    "rate": {"limit": 5000, "remaining": 5000},
    "ARCH": "?",
    "nps": 0.0,
    "remote_addr": "?.?.?.?",
    "country_code": "?",
}

worker_dict = {}

<<<<<<< HEAD
=======
def convert_task_list(run, tasks):
    newtt = []
    task_id = -1
    game_count = 0
    for task in tasks:
        task_id += 1
        task = copy.deepcopy(task)

        # Workaround for bug in my local db
        if "residual" in task and isinstance(task["residual"], dict):
            game_count += task["num_games"]
            continue

        if not "stats" in task:  # dummy task
            game_count += task["num_games"]
            continue

        if "pending" in task:
            del task["pending"]

        if "start" not in task:
            task["start"] = game_count

        if "stats" in task:
            stats = task["stats"]
            if "crashes" not in stats:
                stats["crashes"] = 0
            if "time_losses" not in stats:
                stats["time_losses"] = 0

        if "last_updated" not in task:
            if "last_updated" in run:
                task["last_updated"] = run["last_updated"]
            elif "start_time" in run:
                task["last_updated"] = run["start_time"]
            else:
                task["last_updated"] = datetime.datetime.min

        if "worker_info" not in task:
            task["worker_info"] = copy.deepcopy(worker_info_default)

        worker_info = task["worker_info"]
        # in old tests concurrency was a string
        worker_info["concurrency"] = int(worker_info["concurrency"])

        if (
            "uname" in worker_info
            and isinstance(worker_info["uname"], list)
            and len(worker_info["uname"]) >= 3
        ):
            uname = worker_info["uname"]
            worker_info["uname"] = uname[0] + " " + uname[2]

        # A bunch of things that changed at the same time
        if "gcc_version" in worker_info:
            gcc_version_ = worker_info["gcc_version"]
            if isinstance(gcc_version_, str):
                gcc_version = [int(k) for k in gcc_version_.split(".")]
                worker_info["gcc_version"] = gcc_version

        if "python_version" not in worker_info:
            if "version" in worker_info:
                if ":" in str(worker_info["version"]):
                    version_ = worker_info["version"].split(":")
                    version = int(version_[0])
                    python_version = [int(k) for k in version_[1].split(".")]
                    worker_info["python_version"] = python_version
                    worker_info["version"] = version
                else:
                    version = int(worker_info["version"])
                    worker_info["version"] = version

        # Two other things that changed
        if "ARCH" not in worker_info:
            if "ARCH" in task:
                worker_info["ARCH"] = task["ARCH"]
                del task["ARCH"]
            if "nps" in task:
                worker_info["nps"] = task["nps"]
                del task["nps"]
>>>>>>> 1f00e05... Clean up utils scripts and update to pymongo 4.x

def convert_task_list(tasks):
    for task in tasks:
        if task["worker_info"]["unique_key"] == "xxxxxxxx":
            name = worker_name(task["worker_info"])
            if name not in worker_dict:
                worker_dict[name] = str(uuid.uuid4())
            task["worker_info"]["unique_key"] = worker_dict[name]


def convert_run(run):
    for k, v in run["args"].items():
        if v == "?":
            run["args"][k] = ""

    for flag in ["finished", "failed", "deleted", "is_green", "is_yellow"]:
        if flag not in run:
            run[flag] = False


if __name__ == "__main__":
    client = pymongo.MongoClient()
    runs_collection = client["fishtest_new"]["runs"]
    runs = runs_collection.find({}).sort("_id", 1)
    count = 0
    print("Starting conversion...")
    t0 = datetime.datetime.utcnow()
    for r in runs:
        count += 1
        r_id = r["_id"]
        convert_run(r)
        convert_task_list(r["tasks"])
        runs_collection.replace_one({"_id": r_id}, r)
        print("Runs converted: {}.".format(count), end="\r")
    t1 = datetime.datetime.utcnow()
    duration = (t1 - t0).total_seconds()
    time_per_run = duration / count
    print("")
    print(
        "Conversion finished in {:.2f} seconds. Time per run: {:.2f}ms.".format(
            duration, 1000 * time_per_run
        )
    )
    runs.close()
    client.close()
