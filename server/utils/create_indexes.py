#!/usr/bin/env python3

# create_indexes.py - (re-)create indexes
#
# Run this script manually to create the indexes, it could take a few
# seconds/minutes to run.

import os
import pprint
import sys

from pymongo import ASCENDING, DESCENDING, MongoClient

db_name = "fishtest_new"

# MongoDB server is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
conn = MongoClient(os.getenv("FISHTEST_HOST") or "localhost")
db = conn[db_name]


def create_runs_indexes():
    print("Creating indexes on runs collection")
    db["runs"].create_index(
        [("finished", ASCENDING)],
        name="unfinished_runs",
        partialFilterExpression={"finished": False},
    )
    db["runs"].create_index(
        [("finished", ASCENDING), ("last_updated", DESCENDING)],
        name="finished_runs",
        partialFilterExpression={"finished": True},
    )
    db["runs"].create_index(
        [
            ("finished", ASCENDING),
            ("is_green", DESCENDING),
            ("last_updated", DESCENDING),
        ],
        name="finished_green_runs",
        partialFilterExpression={"finished": True, "is_green": True},
    )
    db["runs"].create_index(
        [
            ("finished", ASCENDING),
            ("is_yellow", DESCENDING),
            ("last_updated", DESCENDING),
        ],
        name="finished_yellow_runs",
        partialFilterExpression={"finished": True, "is_yellow": True},
    )
    db["runs"].create_index(
        [
            ("finished", ASCENDING),
            ("last_updated", DESCENDING),
            ("tc_base", DESCENDING),
        ],
        name="finished_ltc_runs",
        partialFilterExpression={"finished": True, "tc_base": {"$gte": 40}},
    )
    db["runs"].create_index(
        [("args.username", DESCENDING), ("last_updated", DESCENDING)], name="user_runs"
    )

    db["runs"].create_index(
        [
            ("args.username", DESCENDING),
            ("finished", ASCENDING),
            ("last_updated", DESCENDING),
        ],
        name="finished_user_runs",
        partialFilterExpression={"finished": True},
    )


def create_pgns_indexes():
    print("Creating indexes on pgns collection")
    db["pgns"].create_index([("run_id", DESCENDING)])


def create_nns_indexes():
    print("Creating indexes on nns collection")
    db["nns"].create_index([("name", DESCENDING)])


def create_users_indexes():
    db["users"].create_index("username", unique=True)


def create_workers_indexes():
    db["workers"].create_index("worker_name", unique=True)


def create_actions_indexes():
    db["actions"].create_index([("username", ASCENDING), ("_id", DESCENDING)])
    db["actions"].create_index([("action", ASCENDING), ("_id", DESCENDING)])
    db["actions"].create_index([("run_id", ASCENDING), ("_id", DESCENDING)])
    db["actions"].create_index(
        [
            ("action", "text"),
            ("username", "text"),
            ("worker", "text"),
            ("message", "text"),
            ("run", "text"),
            ("user", "text"),
            ("nn", "text"),
            ("_id", DESCENDING),
        ],
        default_language="none",
    )


def print_current_indexes():
    for collection_name in db.list_collection_names():
        c = db[collection_name]
        print("Current indexes on " + collection_name + ":")
        pprint.pprint(
            c.index_information(), stream=None, indent=2, width=110, depth=None
        )
        print("")


def drop_indexes(collection_name):
    # Drop all indexes on collection except _id_
    print("\nDropping indexes on {}".format(collection_name))
    collection = db[collection_name]
    index_keys = list(collection.index_information().keys())
    print("Current indexes: {}".format(index_keys))
    for idx in index_keys:
        if idx != "_id_":
            print("Dropping " + collection_name + " index " + idx + " ...")
            collection.drop_index(idx)


if __name__ == "__main__":
    # Takes a list of collection names as arguments.
    # For each collection name, this script drops indexes and re-creates them.
    # With no argument, indexes are printed, but no indexes are re-created.
    collection_names = sys.argv[1:]
    if collection_names:
        print("Re-creating indexes...")
        for collection_name in collection_names:
            if collection_name == "users":
                drop_indexes("users")
                create_users_indexes()
            if collection_name == "workers":
                drop_indexes("workers")
                create_workers_indexes()
            elif collection_name == "actions":
                drop_indexes("actions")
                create_actions_indexes()
            elif collection_name == "runs":
                drop_indexes("runs")
                create_runs_indexes()
            elif collection_name == "pgns":
                drop_indexes("pgns")
                create_pgns_indexes()
            elif collection_name == "nns":
                drop_indexes("nns")
                create_nns_indexes()
        print("Finished creating indexes!\n")
    print_current_indexes()
    if not collection_names:
        print("Collections in {}: {}".format(db_name, db.list_collection_names()))
        print(
            "Give a list of collection names as arguments to re-create indexes. For example:\n"
        )
        print(
            "  python3 create_indexes.py users runs - drops and creates indexes for runs and users\n"
        )
