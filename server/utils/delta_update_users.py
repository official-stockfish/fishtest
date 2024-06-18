#!/usr/bin/env python3

import sys
from datetime import datetime, timedelta, timezone

from fishtest.rundb import RunDb
from fishtest.util import delta_date, diff_date, estimate_game_duration
from pymongo import DESCENDING


def initialize_info(rundb, clear_stats):
    utc_datetime_min = datetime.min.replace(tzinfo=timezone.utc)
    info_total = {}
    info_top_month = {}
    diff_ini = diff_date(utc_datetime_min).total_seconds()
    last_ini = delta_date(diff_date(utc_datetime_min))

    for u in rundb.userdb.get_users():
        username = u["username"]
        # Initialize info_top_month with cleared contribution values
        info_top_month[username] = {
            "username": username,
            "cpu_hours": 0,
            "games": 0,
            "games_per_hour": 0.0,
            "tests": 0,
            "tests_repo": u.get("tests_repo", ""),
            "last_updated": utc_datetime_min,
            "diff": diff_ini,
            "str_last_updated": last_ini,
        }
        if clear_stats:
            info_total[username] = info_top_month[username].copy()
        else:
            # Load user data from the user_cache
            info_total[username] = rundb.userdb.user_cache.find_one(
                {"username": username}
            )
            if info_total[username]:
                info_total[username]["games_per_hour"] = 0.0
            else:
                # No "user_cache" entry, initialize with cleared contribution
                info_total[username] = info_top_month[username].copy()
    return info_total, info_top_month


def compute_games_rates(rundb, info_tuple):
    # use the reference core nps, also set in rundb.py and games.py
    for machine in rundb.get_machines():
        games_per_hour = (
            (machine["nps"] / 368174)
            * (3600.0 / estimate_game_duration(machine["run"]["args"]["tc"]))
            * (int(machine["concurrency"]) // machine["run"]["args"].get("threads", 1))
        )
        for info in info_tuple:
            info[machine["username"]]["games_per_hour"] += games_per_hour


def process_run(run, info):
    # Update the number of tests contributed by the user
    r_username = run["args"].get("username")
    if r_username in info:
        info[r_username]["tests"] += 1
    else:
        print(f"not in userdb: {r_username=}; {run['_id']=}")
        return

    # Update the information for the workers contributed by the users
    tc = estimate_game_duration(run["args"]["tc"])
    for task in run["tasks"]:
        if "worker_info" not in task:
            continue
        t_username = task["worker_info"].get("username")
        if t_username is None:
            continue
        if t_username not in info:
            print(
                f"not in userdb: {t_username=}; {run['_id']=}; {task['worker_info']=}"
            )
            continue

        if "stats" in task:
            stats = task["stats"]
            num_games = stats["wins"] + stats["losses"] + stats["draws"]
        else:
            num_games = 0

        info_user = info[t_username]
        info_user["last_updated"] = max(
            info_user["last_updated"],
            task.get("last_updated", datetime.min.replace(tzinfo=timezone.utc)),
        )
        info_user["cpu_hours"] += float(
            num_games * int(run["args"].get("threads", 1)) * tc / (60 * 60)
        )
        info_user["games"] += num_games


def update_info(rundb, clear_stats, deltas, info_total, info_top_month):
    for run in rundb.get_unfinished_runs():
        try:
            # Update info_top_month with the contribution of the unfinished runs
            process_run(run, info_top_month)
        except Exception as e:
            print(f"Exception on unfinished run {run['_id']=} for info_top_month:\n{e}")

    now = datetime.now(timezone.utc)
    skip = False
    skip_count = 0
    new_deltas = {}

    for run in rundb.runs.find({"finished": True}, sort=[("last_updated", DESCENDING)]):
        if str(run["_id"]) in new_deltas:
            # Lazy reads of an indexed collection, skip a repeated new finished run
            print("Warning: skipping repeated finished run!")
            continue

        if not clear_stats and not skip and str(run["_id"]) in deltas:
            # The run is in deltas, skip for info_total because we have already
            # processed this run in previous script executions
            skip = True
        if not skip:
            new_deltas |= {str(run["_id"]): None}
            try:
                # Update info_total with the contribution of the finished runs
                process_run(run, info_total)
            except Exception as e:
                print(f"Exception on finished run {run['_id']=} for info_total:\n{e}")
        if skip and skip_count < 10:
            skip = False
            skip_count += 1

        # Update info_top_month with finished runs having start_time in the last 30 days
        if (now - run["start_time"]).days < 30:
            try:
                process_run(run, info_top_month)
            except Exception as e:
                print(
                    f"Exception on finished run {run['_id']=} for info_top_month:\n{e}"
                )
        elif not clear_stats and skip:
            break

    compute_games_rates(rundb, (info_total, info_top_month))
    return new_deltas


def build_users(info):
    users = []
    # diff_date(given_date) = datetime.now(timezone.utc) - given_date
    # delta_date(diff: timedelta) -> str:
    for username, info_user in info.items():
        try:
            diff = diff_date(info_user["last_updated"])
            info_user["diff"] = diff.total_seconds()
            info_user["str_last_updated"] = delta_date(diff)
        except Exception as e:
            print(f"Exception updating 'diff' for {username=}:\n{e}")
        users.append(info_user)

    return [u for u in users if u["games"] > 0 or u["tests"] > 0]


def update_deltas(rundb, deltas, new_deltas):
    # Write the new deltas to the database in batches to speed up the collection operations,
    # set directly the value to None for speed, change to new_deltas[k] if needed
    print("update deltas:")
    print(f"{len(new_deltas)=}\n{next(iter(new_deltas))=}")
    new_deltas |= deltas
    print(f"{len(new_deltas)=}\n{next(iter(new_deltas))=}")
    rundb.deltas.delete_many({})
    n = 10000
    keys = tuple(new_deltas.keys())
    docs = (
        {k: None for k in keys_batch}
        for keys_batch in (keys[i : i + n] for i in range(0, len(new_deltas), n))
    )
    rundb.deltas.insert_many(docs)


def update_users(rundb, users_total, users_top_month):
    rundb.userdb.user_cache.delete_many({})
    if users_total:
        rundb.userdb.user_cache.insert_many(users_total)
        rundb.userdb.user_cache.create_index("username", unique=True)
        print(f"Successfully updated {len(users_total)} users")
    rundb.userdb.top_month.delete_many({})
    if users_top_month:
        rundb.userdb.top_month.insert_many(users_top_month)
        print(f"Successfully updated {len(users_top_month)} top month users")


def cleanup_users(rundb):
    # Delete users that have never been active and old admins group
    idle = {}
    now = datetime.now(timezone.utc)
    for u in rundb.userdb.get_users():
        update = False
        while "group:admins" in u["groups"]:
            u["groups"].remove("group:admins")
            update = True
        if update:
            rundb.userdb.save_user(u)
        if "registration_time" not in u or u["registration_time"] < now - timedelta(
            days=28
        ):
            idle[u["username"]] = u
    for u in rundb.userdb.user_cache.find():
        if u["username"] in idle:
            del idle[u["username"]]
    for u in idle.values():
        # A safe guard against deleting long time users
        if "registration_time" not in u or u["registration_time"] < now - timedelta(
            days=38
        ):
            print("Warning: Found old user to delete:", str(u["_id"]))
        else:
            print("Delete:", str(u["_id"]))
            rundb.userdb.users.delete_one({"_id": u["_id"]})


def main():
    # The script computes the total and top month contributions of all users in two modes:
    # - full scan  : from scratch, starting from a clean status.
    # - update scan: incrementally, using the status from previous executions of the script
    # Note that the update scan is not perfect:
    # - It does not account for the additional contribution of runs that have switched
    #   from finished to unfinished and back to finished in the meantime.
    # - It underestimates the top month contribution compared to the full scan
    #   due to the exit condition.

    # "info_total" and "info_top_month" are dictionaries with the username as the key.
    # They are used to collect information about the contributions of each user for these runs
    # "info_total"    : all finished runs.
    # "info_top_month": unfinished runs and finished runs started within the previous 30 days.
    # Each username/key has a nested dictionary with the following structure:
    # info[username] = {
    #     "username": username,
    #     "cpu_hours": 0,
    #     "games": 0,
    #     "games_per_hour": 0.0,
    #     "tests": 0,
    #     "tests_repo": u.get("tests_repo", ""),
    #     "last_updated": utc_datetime_min,    # latest datetime of all user's tasks
    #     "diff": diff_date(utc_datetime_min), # used to sort in the users table
    #     "str_last_updated": delta_date(diff_date(utc_datetime_min)), # e.g. "Never", "12 days ago"

    # "new_deltas": dictionary with keys representing the IDs of newly finished runs
    # since the previous script execution. It is used to update the "deltas" collection.
    # "deltas"    : dictionary with keys representing the IDs of all finished runs that
    # have already been processed in previous script executions to avoid double counting.
    # It is loaded from the "deltas" collection in update scan mode,
    # it is an empty dictionary in full scan mode.

    rundb = RunDb()
    deltas = {}
    if len(sys.argv) == 1:
        # No guarantee that the returned natural order will be the insertion order
        for doc in rundb.deltas.find({}, {"_id": 0}):
            deltas |= doc

    if deltas:
        print("update scan")
        clear_stats = False
        print("load deltas:")
        print(f"{len(deltas)=}\n{next(iter(deltas))=}")
    else:
        print("full scan")
        clear_stats = True

    info_total, info_top_month = initialize_info(rundb, clear_stats)
    new_deltas = update_info(rundb, clear_stats, deltas, info_total, info_top_month)
    if new_deltas:
        update_deltas(rundb, deltas, new_deltas)

    users_total = build_users(info_total)
    users_top_month = build_users(info_top_month)
    update_users(rundb, users_total, users_top_month)
    cleanup_users(rundb)
    # Record this update run
    rundb.actiondb.system_event(message="Update user statistics")


if __name__ == "__main__":
    main()
