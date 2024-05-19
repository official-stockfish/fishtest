#!/usr/bin/env python3
import re
from datetime import datetime, timedelta, timezone

from fishtest.rundb import RunDb
from pymongo import DESCENDING


def purge_pgns(rundb, finished, deleted, days, days_ltc=60):
    kept_runs = kept_tasks = kept_pgns = 0
    purged_runs = purged_tasks = purged_pgns = 0
    now = datetime.now(timezone.utc)
    cutoff_date_ltc = now - timedelta(days=days_ltc)
    cutoff_date = now - timedelta(days=days)
    tc_regex = re.compile("^([2-9][0-9])|([1-9][0-9][0-9])")
    runs_query = {
        "finished": finished,
        "deleted": deleted,
        "last_updated": {"$gte": now - timedelta(days=60)},
    }
    for run in rundb.db.runs.find(runs_query, sort=[("last_updated", DESCENDING)]):
        keep = (
            not deleted
            and finished
            and tc_regex.match(run["args"]["tc"])
            and run["last_updated"] > cutoff_date_ltc
        ) or run["last_updated"] > cutoff_date

        if keep:
            kept_runs += 1
        else:
            purged_runs += 1

        tasks_count = len(run["tasks"])
        pgns_query = {"run_id": {"$regex": f"^{run['_id']}-\\d+"}}
        pgns_count = rundb.pgndb.count_documents(pgns_query)
        if keep:
            kept_tasks += tasks_count
            kept_pgns += pgns_count
        else:
            rundb.pgndb.delete_many(pgns_query)
            purged_tasks += tasks_count
            purged_pgns += pgns_count

    return (
        kept_runs,
        kept_tasks,
        kept_pgns,
        purged_runs,
        purged_tasks,
        purged_pgns,
    )


def report(
    runs_type,
    kept_runs,
    kept_tasks,
    kept_pgns,
    purged_runs,
    purged_tasks,
    purged_pgns,
):
    template = "{:5d} runs, {:7d} tasks, {:7d} pgns"
    print(runs_type)
    print("kept  :", template.format(kept_runs, kept_tasks, kept_pgns))
    print("purged:", template.format(purged_runs, purged_tasks, purged_pgns))


def main():
    # Process the runs in descending order of last_updated for the
    # last 60 days and purge the pgns collection for:
    # - runs that are finished and not deleted, and older than 1 days for STC
    # - runs that are finished and not deleted, and older than 10 days for LTC
    # - runs that are finished and deleted, and older than 10 days
    # - runs that are not finished and not deleted, and older than 50 days

    rundb = RunDb()
    out = purge_pgns(rundb=rundb, finished=True, deleted=False, days=1, days_ltc=10)
    report("Finished runs:", *out)
    out = purge_pgns(rundb=rundb, finished=True, deleted=True, days=10)
    report("Deleted runs:", *out)
    out = purge_pgns(rundb=rundb, finished=False, deleted=False, days=50)
    report("Unfinished runs:", *out)
    msg = rundb.db.command({"compact": "pgns"})
    print(msg)


if __name__ == "__main__":
    main()
