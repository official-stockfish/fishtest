#!/usr/bin/env python3

import sys
from datetime import datetime, timedelta

from fishtest.rundb import RunDb
from fishtest.util import delta_date, diff_date, estimate_game_duration
from pymongo import DESCENDING

new_deltas = {}
skip = False


def process_run(run, info, deltas=None):
    global skip
    if deltas and (skip or str(run["_id"]) in deltas):
        skip = True
        return
    if deltas is not None and str(run["_id"]) in new_deltas:
        print("Warning: skipping repeated run!")
        return
    if "username" in run["args"]:
        username = run["args"]["username"]
        if username in info:
            info[username]["tests"] += 1
        else:
            print("not in info:", username)
            return

    tc = estimate_game_duration(run["args"]["tc"])
    for task in run["tasks"]:
        if "worker_info" not in task:
            continue
        username = task["worker_info"].get("username", None)
        if username is None:
            continue
        if username not in info:
            print("not in info:", username)
            continue

        if "stats" in task:
            stats = task["stats"]
            num_games = stats["wins"] + stats["losses"] + stats["draws"]
        else:
            num_games = 0

        try:
            info[username]["last_updated"] = max(
                task["last_updated"], info[username]["last_updated"]
            )
            info[username]["task_last_updated"] = max(
                task["last_updated"], info[username]["last_updated"]
            )
        except (TypeError, KeyError) as e:
            # Comparison between a datetime and a string as "6 hours ago"
            info[username]["last_updated"] = task["last_updated"]
        except Exception as e:
            print("Exception updating info[username]:", e, sep="\n", file=sys.stderr)

        info[username]["cpu_hours"] += float(
            num_games * int(run["args"].get("threads", 1)) * tc / (60 * 60)
        )
        info[username]["games"] += num_games
    if deltas is not None:
        new_deltas.update({str(run["_id"]): None})


def build_users(machines, info):
    for machine in machines:
        games_per_hour = (
            (machine["nps"] / 1328000.0)
            * (3600.0 / estimate_game_duration(machine["run"]["args"]["tc"]))
            * (int(machine["concurrency"]) // machine["run"]["args"].get("threads", 1))
        )
        info[machine["username"]]["games_per_hour"] += games_per_hour

    users = []
    for u in info.keys():
        user = info[u]
        try:
            # eg "11 minutes ago", "6 hours ago", "Never"
            if isinstance(user["last_updated"], str):
                if "task_last_updated" in user:
                    diff = diff_date(user["task_last_updated"])
                    user["diff"] = diff.total_seconds()
                    user["last_updated"] = delta_date(diff)
            else:
                # eg "2022-08-30 01:05:23.656000", "0001-01-01 00:00:00"
                diff = diff_date(user["last_updated"])
                user["diff"] = diff.total_seconds()
                user["last_updated"] = delta_date(diff)
        except Exception as e:
            print("Exception updating user['diff']:", e, sep="\n", file=sys.stderr)
        users.append(user)

    users = [u for u in users if u["games"] > 0 or u["tests"] > 0]
    return users


def update_users():
    rundb = RunDb()

    deltas = {}
    info = {}
    top_month = {}

    clear_stats = True
    if len(sys.argv) > 1:
        print("scan all")
    else:
        deltas = rundb.deltas.find_one()
        if deltas:
            clear_stats = False
        else:
            deltas = {}

    for u in rundb.userdb.get_users():
        username = u["username"]
        top_month[username] = {
            "username": username,
            "cpu_hours": 0,
            "games": 0,
            "tests": 0,
            "tests_repo": u.get("tests_repo", ""),
            "last_updated": datetime.min,
            "games_per_hour": 0.0,
        }
        if clear_stats:
            info[username] = top_month[username].copy()
        else:
            info[username] = rundb.userdb.user_cache.find_one({"username": username})
            if info[username]:
                info[username]["games_per_hour"] = 0.0
            else:
                info[username] = top_month[username].copy()

    for run in rundb.get_unfinished_runs():
        try:
            process_run(run, top_month)
        except Exception as e:
            print(
                "Exception processing run {} for top_month:".format(run["_id"]),
                e,
                sep="\n",
                file=sys.stderr,
            )

    # Step through these in small batches (step size 100) to save RAM
    step_size = 100

    now = datetime.utcnow()
    more_days = True
    last_updated = None
    while more_days:
        q = {"finished": True}
        if last_updated:
            q["last_updated"] = {"$lt": last_updated}
        runs = list(
            rundb.runs.find(q, sort=[("last_updated", DESCENDING)], limit=step_size)
        )
        if len(runs) == 0:
            break
        for run in runs:
            try:
                process_run(run, info, deltas)
            except Exception as e:
                print(
                    "Exception processing run {} for deltas:".format(run["_id"]),
                    e,
                    sep="\n",
                    file=sys.stderr,
                )
            if (now - run["start_time"]).days < 30:
                try:
                    process_run(run, top_month)
                except Exception as e:
                    print(
                        "Exception on run {} for top_month:".format(run["_id"]),
                        e,
                        sep="\n",
                        file=sys.stderr,
                    )
            elif not clear_stats:
                more_days = False
        last_updated = runs[-1]["last_updated"]

    if new_deltas:
        new_deltas.update(deltas)
        rundb.deltas.delete_many({})
        rundb.deltas.insert_many([{k: v} for k, v in new_deltas.items()])

    machines = rundb.get_machines()

    rundb.userdb.user_cache.delete_many({})
    users = build_users(machines, info)
    if users:
        rundb.userdb.user_cache.insert_many(users)
        rundb.userdb.user_cache.create_index("username", unique=True)

    rundb.userdb.top_month.delete_many({})
    users_top = build_users(machines, top_month)
    if users_top:
        rundb.userdb.top_month.insert_many(users_top)

    # Delete users that have never been active and old admins group
    idle = {}
    for u in rundb.userdb.get_users():
        update = False
        while "group:admins" in u["groups"]:
            u["groups"].remove("group:admins")
            update = True
        if update:
            rundb.userdb.save_user(u)
        if "registration_time" not in u or u[
            "registration_time"
        ] < datetime.utcnow() - timedelta(days=28):
            idle[u["username"]] = u
    for u in rundb.userdb.user_cache.find():
        if u["username"] in idle:
            del idle[u["username"]]
    for u in idle.values():
        # A safe guard against deleting long time users
        if "registration_time" not in u or u[
            "registration_time"
        ] < datetime.utcnow() - timedelta(days=38):
            print("Warning: Found old user to delete:", str(u["_id"]))
        else:
            print("Delete:", str(u["_id"]))
            rundb.userdb.users.delete_one({"_id": u["_id"]})

    print("Successfully updated {} users".format(len(users)))

    # record this update run
    rundb.actiondb.system_event(message="Update user statistics")


if __name__ == "__main__":
    update_users()
