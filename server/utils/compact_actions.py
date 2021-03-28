#!/usr/bin/env python3

from fishtest.actiondb import ActionDb
from pymongo import MongoClient

conn = MongoClient()
db = conn["fishtest_new"]
actiondb = ActionDb(db)


def compact_actions():
    for a in actiondb.actions.find():
        update = False
        if "tasks" in a["data"]:
            del a["data"]["tasks"]
            print(a["data"]["_id"])
            update = True
        if "before" in a["data"]:
            del a["data"]["before"]["tasks"]
            print("before")
            update = True
        if "after" in a["data"]:
            del a["data"]["after"]["tasks"]
            print("after")
            update = True

        if update:
            actiondb.actions.replace_one({"_id": a["_id"]}, a)


def main():
    compact_actions()


if __name__ == "__main__":
    main()
