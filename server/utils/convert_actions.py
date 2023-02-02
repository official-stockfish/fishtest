import datetime

import pymongo
from bson.objectid import ObjectId
from fishtest.actiondb import run_name
from fishtest.util import hex_print

if __name__ == "__main__":
    client = pymongo.MongoClient()
    actions_collection = client["fishtest_new"]["actions"]
    runs_collection = client["fishtest_new"]["runs"]
    actions = actions_collection.find({}).sort("_id", 1)
    count = 0
    print("Starting conversion...")
    t0 = datetime.datetime.utcnow()
    for action in actions:
        count += 1
        action_id = action["_id"]
        if "time" in action and isinstance(action["time"], datetime.datetime):
            action["time"] = (
                action["time"].replace(tzinfo=datetime.timezone.utc).timestamp()
            )
        if "run_id" in action and isinstance(action["run_id"], ObjectId):
            action["run_id"] = str(action["run_id"])
        actions_collection.replace_one({"_id": action_id}, action)
        print("Actions converted: {}.".format(count), end="\r")
    t1 = datetime.datetime.utcnow()
    duration = (t1 - t0).total_seconds()
    time_per_run = duration / count
    print("")
    print(
        "Conversion finished in {:.2f} seconds. Time per run: {:.2f}ms.".format(
            duration, 1000 * time_per_run
        )
    )
    actions.close()
    client.close()
