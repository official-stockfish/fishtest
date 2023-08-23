import pprint
import uuid
from datetime import datetime, timezone

import pymongo
from fishtest.util import worker_name


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
    "start_time": datetime.min,
    "last_updated": datetime.min,
    "tc_base": -1.0,
    "base_same_as_master": True,
    "results_stale": False,
    "finished": True,
    "approved": True,
    "approver": "?",
    "workers": 0,
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
    t0 = datetime.now(timezone.utc)
    for r in runs:
        count += 1
        r_id = r["_id"]
        convert_run(r)
        convert_task_list(r["tasks"])
        runs_collection.replace_one({"_id": r_id}, r)
        print("Runs converted: {}.".format(count), end="\r")
    t1 = datetime.now(timezone.utc)
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
