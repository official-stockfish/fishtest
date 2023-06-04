#!/usr/bin/env python3
import re
from datetime import datetime, timedelta

from fishtest.rundb import RunDb
from pymongo import DESCENDING


def purge_pgn(rundb, finished, deleted, days):
    saved_runs, saved_tasks, saved_pgns = 0, 0, 0
    deleted_runs, deleted_tasks, deleted_pgns = 0, 0, 0
    now = datetime.utcnow()
    cutoff_date_ltc = now - timedelta(days=5 * days)
    cutoff_date = now - timedelta(days=days)
    tc_regex = re.compile("^([2-9][0-9])|([1-9][0-9][0-9])")
    runs_query = {
        "finished": finished,
        "deleted": deleted,
        "last_updated": {"$gte": now - timedelta(days=60)},
    }
    for run in rundb.db.runs.find(runs_query, sort=[("last_updated", DESCENDING)]):
        skip = (
            not deleted
            and finished
            and tc_regex.match(run["args"]["tc"])
            and run["last_updated"] > cutoff_date_ltc
        ) or run["last_updated"] > cutoff_date

        if skip:
            saved_runs += 1
        else:
            deleted_runs += 1

        tasks_count = len(run["tasks"])
        pgns_query = {
            "run_id": {"$in": [f"{run['_id']}-{idx}" for idx in range(tasks_count)]}
        }
        pgns_count = rundb.pgndb.count_documents(pgns_query)
        if skip:
            saved_tasks += tasks_count
            saved_pgns += pgns_count
        else:
            rundb.pgndb.delete_many(pgns_query)
            deleted_tasks += tasks_count
            deleted_pgns += pgns_count

    return (
        saved_runs,
        saved_tasks,
        saved_pgns,
        deleted_runs,
        deleted_tasks,
        deleted_pgns,
    )


def report(
    run_type,
    saved_runs,
    saved_tasks,
    saved_pgns,
    deleted_runs,
    deleted_tasks,
    deleted_pgns,
):
    template = "{:5d} runs, {:7d} tasks, {:7d} pgns"
    print(run_type)
    print("saved :", template.format(saved_runs, saved_tasks, saved_pgns))
    print("purged:", template.format(deleted_runs, deleted_tasks, deleted_pgns))


def main():
    # Process the runs in descending order of last_updated for the
    # last 60 days and purge the pgns collection for:
    # - runs that are finished and not deleted, and older than 2 days for STC
    # - runs that are finished and not deleted, and older than 10 days for LTC
    # - runs that are finished and deleted, and older than 10 days
    # - runs that are not finished and not deleted, and older than 50 days

    rundb = RunDb()
    out = purge_pgn(rundb=rundb, finished=True, deleted=False, days=2)
    report("Finished runs:", *out)
    out = purge_pgn(rundb=rundb, finished=True, deleted=True, days=10)
    report("Deleted runs:", *out)
    out = purge_pgn(rundb=rundb, finished=False, deleted=False, days=50)
    report("Unfinished runs:", *out)
    msg = rundb.db.command({"compact": "pgns"})
    print(msg)


if __name__ == "__main__":
    main()
