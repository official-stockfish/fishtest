#!/usr/bin/env python3
"""Compute full and incremental user contributions.

This script supports two modes:
  • Full scan: processes all runs from scratch.
  • Update scan: processes only newly finished runs since the last run.

Note:
  • Update scan does not capture runs that flip between unfinished and finished.
  • It may underestimate monthly contributions due to the exit condition.

User data is stored in two dictionaries:
  info_total:
    Data from all finished runs.
  info_top_month:
    Data from unfinished runs and finished runs started within 30 days.

Each user record includes:
  "username", "cpu_hours", "games", "games_per_hour",
  "tests", "tests_repo", "last_updated".

Deltas:
  The new_deltas dict holds IDs of newly finished runs.
  The deltas dict contains all finish IDs processed previously,
  avoiding duplicate processing.

"""

import logging
import sys
from datetime import UTC, datetime, timedelta

from pymongo import DESCENDING
from pymongo.collection import Collection

from fishtest.rundb import RunDb
from fishtest.util import estimate_game_duration

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

MAX_SKIP_COUNT = 10
RECENT_DAYS_THRESHOLD = 30
REFERENCE_CORE_NPS = 628000


def initialize_info(rundb: RunDb, *, clear_stats: bool) -> tuple[dict, dict]:
    """Initialize user statistics dictionaries with default or cached values.

    Args:
        rundb: The database object containing user data.
        clear_stats (bool): If True, reset stats to default values.

    Returns:
        tuple: Two dictionaries, (info_total, info_top_month), with user statistics.

    """
    utc_datetime_min = datetime.min.replace(tzinfo=UTC)
    info_total = {}
    info_top_month = {}

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
        }
        if clear_stats:
            info_total[username] = info_top_month[username].copy()
        else:
            # Load user data from the user_cache
            info_total[username] = rundb.userdb.user_cache.find_one(
                {"username": username},
            )
            if info_total[username]:
                info_total[username]["games_per_hour"] = 0.0
            else:
                # No "user_cache" entry, initialize with cleared contribution
                info_total[username] = info_top_month[username].copy()
    return info_total, info_top_month


def compute_games_rates(rundb: RunDb, info_total: dict, info_top_month: dict) -> None:
    """Compute the games per hour rate for each machine and update user info.

    Args:
        rundb: The database object.
        info_total (dict): Dictionary with total user stats.
        info_top_month (dict): Dictionary with top month user stats.

    """
    # Use the reference core nps, also set in rundb.py and games.py
    for machine in rundb.get_machines():
        games_per_hour = (
            (machine["nps"] / REFERENCE_CORE_NPS)
            * (3600 / estimate_game_duration(machine["run"]["args"]["tc"]))
            * (int(machine["concurrency"]) // machine["run"]["args"].get("threads", 1))
        )
        for info in (info_total, info_top_month):
            info[machine["username"]]["games_per_hour"] += games_per_hour


def process_run(run: dict, info: dict) -> None:
    """Process a single run and update corresponding user statistics.

    Args:
        run: A dictionary representing a run.
        info (dict): The user statistics dictionary to update.

    """
    # Update the number of tests contributed by the user
    r_username = run["args"].get("username")
    if r_username in info:
        info[r_username]["tests"] += 1
    else:
        logger.warning(
            "Not in userdb: r_username=%s; run['_id']=%s",
            r_username,
            run["_id"],
        )
        return

    # Update the information for the workers contributed by the users
    tc = estimate_game_duration(run["args"]["tc"])
    for task in run.get("tasks", {}):
        if "worker_info" not in task:
            continue
        t_username = task["worker_info"].get("username")
        if t_username is None:
            continue
        if t_username not in info:
            logger.warning(
                "Not in userdb: t_username=%s; run['_id']=%s; task['worker_info']=%s",
                t_username,
                run["_id"],
                task["worker_info"],
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
            task.get("last_updated", datetime.min.replace(tzinfo=UTC)),
        )
        info_user["cpu_hours"] += float(
            num_games * int(run["args"].get("threads", 1)) * tc / (60 * 60),
        )
        info_user["games"] += num_games


def update_info(
    rundb: RunDb,
    deltas: dict,
    info_total: dict,
    info_top_month: dict,
    *,
    clear_stats: bool,
) -> dict:
    """Update user statistics based on finished and unfinished runs.

    Args:
        rundb: The database object.
        deltas (dict): Previously processed run IDs.
        info_total (dict): Dictionary with total user stats.
        info_top_month (dict): Dictionary with top month user stats.
        clear_stats (bool): Flag to determine whether to reset stats.

    Returns:
        dict: New deltas containing newly processed run IDs.

    """
    for run in rundb.get_unfinished_runs():
        try:
            # Update info_top_month with the contribution of the unfinished run
            process_run(run, info_top_month)
        except Exception:
            logger.exception(
                "Exception on unfinished run run['_id']=%s for info_top_month:",
                run["_id"],
            )

    now = datetime.now(UTC)
    skip = False
    skip_count = 0
    new_deltas = {}

    for run in rundb.runs.find({"finished": True}, sort=[("last_updated", DESCENDING)]):
        if str(run["_id"]) in new_deltas:
            # Lazy reads of an indexed collection, skip a repeated new finished run
            logger.warning("Skipping repeated finished run!")
            continue

        if not clear_stats and not skip and str(run["_id"]) in deltas:
            # The run is in deltas, skip for info_total because we have already
            # processed this run in previous script executions
            skip = True
        if not skip:
            new_deltas |= {str(run["_id"]): None}
            try:
                # Update info_total with the contribution of the finished run
                process_run(run, info_total)
            except Exception:
                logger.exception(
                    "Exception on finished run run['_id']=%s for info_total:",
                    run["_id"],
                )
        if skip and skip_count < MAX_SKIP_COUNT:
            skip = False
            skip_count += 1

        # Update info_top_month with finished run having start_time
        # in the last RECENT_DAYS_THRESHOLD days
        if (now - run["start_time"]).days < RECENT_DAYS_THRESHOLD:
            try:
                process_run(run, info_top_month)
            except Exception:
                logger.exception(
                    "Exception on finished run run['_id']=%s for info_top_month:",
                    run["_id"],
                )
        elif not clear_stats and skip:
            break

    return new_deltas


def update_deltas(rundb: RunDb, deltas: dict, new_deltas: dict) -> None:
    """Update the database collection with new run deltas.

    Args:
        rundb: The database object.
        deltas (dict): Previously processed run IDs.
        new_deltas (dict): Newly processed run IDs.

    """
    logger.info("Update deltas:")
    logger.info(
        "len(new_deltas)=%s, next(iter(new_deltas))=%s",
        len(new_deltas),
        next(iter(new_deltas)),
    )
    new_deltas |= deltas
    logger.info(
        "len(new_deltas)=%s, next(iter(new_deltas))=%s",
        len(new_deltas),
        next(iter(new_deltas)),
    )
    rundb.deltas.delete_many({})
    n = 10000
    keys = tuple(new_deltas.keys())
    docs = (
        dict.fromkeys(keys_batch)
        for keys_batch in (keys[i : i + n] for i in range(0, len(new_deltas), n))
    )
    rundb.deltas.insert_many(docs)


def filter_users(info: dict) -> list[dict]:
    """Filter user records that have non-zero games or tests."""
    return [user for user in info.values() if user.get("games") or user.get("tests")]


def update_collection(
    collection: Collection,
    documents: list[dict],
) -> None:
    """Replace all documents in a collection and create a unique index."""
    collection.delete_many({})
    if documents:
        collection.insert_many(documents)
        collection.create_index("username", unique=True)
        logger.info(
            "Successfully updated %s documents in '%s'",
            len(documents),
            collection.name,
        )


def cleanup_users(rundb: RunDb) -> None:
    """Clean up inactive users and remove outdated admin group assignments."""
    idle = {}
    now = datetime.now(UTC)
    for u in rundb.userdb.get_users():
        update = False
        while "group:admins" in u["groups"]:
            u["groups"].remove("group:admins")
            update = True
        if update:
            rundb.userdb.save_user(u)
        if "registration_time" not in u or u["registration_time"] < now - timedelta(
            days=28,
        ):
            idle[u["username"]] = u
    for u in rundb.userdb.user_cache.find():
        if u["username"] in idle:
            del idle[u["username"]]
    for u in idle.values():
        # A safe guard against deleting long time users
        if "registration_time" not in u or u["registration_time"] < now - timedelta(
            days=38,
        ):
            logger.warning("Found old user to delete: %s", u["_id"])
        else:
            logger.info("Delete: %s", u["_id"])
            rundb.userdb.users.delete_one({"_id": u["_id"]})


def main() -> None:
    """Update user statistics.

    Reads command-line arguments, processes run deltas, updates user statistics,
    and records the update operation.
    """
    rundb = RunDb()
    deltas = {}
    if len(sys.argv) == 1:
        # No guarantee that the returned natural order will be the insertion order
        for doc in rundb.deltas.find({}, {"_id": 0}):
            deltas |= doc

    if deltas:
        logger.info("Update scan")
        clear_stats = False
        logger.info("Load deltas:")
        logger.info(
            "len(deltas)=%s, next(iter(deltas))=%s",
            len(deltas),
            next(iter(deltas)),
        )
    else:
        logger.info("Full scan")
        clear_stats = True

    info_total, info_top_month = initialize_info(rundb, clear_stats=clear_stats)
    new_deltas = update_info(
        rundb,
        deltas,
        info_total,
        info_top_month,
        clear_stats=clear_stats,
    )
    if new_deltas:
        update_deltas(rundb, deltas, new_deltas)
    compute_games_rates(rundb, info_total, info_top_month)
    update_collection(
        rundb.userdb.user_cache,
        filter_users(info_total),
    )
    update_collection(
        rundb.userdb.top_month,
        filter_users(info_top_month),
    )
    cleanup_users(rundb)
    # Record this update run
    rundb.actiondb.system_event(message="Update user statistics")


if __name__ == "__main__":
    main()
