#!/usr/bin/env python3

import re
from datetime import datetime, timedelta

from fishtest.rundb import RunDb
from pymongo import DESCENDING

rundb = RunDb()


def purge_pgn(days):
    """Purge old PGNs except LTC (>= 20s) runs"""

    deleted_runs = 0
    deleted_tasks = 0
    saved_runs = 0
    saved_tasks = 0
    now = datetime.utcnow()

    run_count = 0
    for run in rundb.runs.find(
        {"finished": True, "deleted": False},
        sort=[("last_updated", DESCENDING)],
    ):

        if (now - run["start_time"]).days > 30:
            break

        run_count += 1
        if run_count % 10 == 0:
            print("Run: {:05d}".format(run_count), end="\r")

        skip = False
        if (
            re.match("^([2-9][0-9])|(1[0-9][0-9])", run["args"]["tc"])
            and run["last_updated"] > datetime.utcnow() - timedelta(days=5 * days)
        ) or run["last_updated"] > datetime.utcnow() - timedelta(days=days):
            saved_runs += 1
            skip = True
        else:
            deleted_runs += 1

        for idx, task in enumerate(run["tasks"]):
            key = str(run["_id"]) + "-" + str(idx)
            for pgn in rundb.pgndb.find(
                {"run_id": key}
            ):  # We can have multiple PGNs per task
                if skip:
                    saved_tasks += 1
                else:
                    rundb.pgndb.delete_one({"_id": pgn["_id"]})
                    deleted_tasks += 1

    print("PGN runs/tasks saved:  {:5d}/{:7d}".format(saved_runs, saved_tasks))
    print("PGN runs/tasks purged: {:5d}/{:7d}".format(deleted_runs, deleted_tasks))


def main():
    purge_pgn(days=2)


if __name__ == "__main__":
    main()
