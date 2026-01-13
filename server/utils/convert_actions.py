from datetime import UTC, datetime

import pymongo
from bson.objectid import ObjectId

if __name__ == "__main__":
    client = pymongo.MongoClient()
    actions_collection = client["fishtest_new"]["actions"]
    runs_collection = client["fishtest_new"]["runs"]
    actions = actions_collection.find({}).sort("_id", 1)
    count = 0
    print("Starting conversion...")
    t0 = datetime.now(UTC)
    for action in actions:
        count += 1
        action_id = action["_id"]
        if "time" in action and isinstance(action["time"], datetime):
            action["time"] = action["time"].replace(tzinfo=UTC).timestamp()
        if "run_id" in action and isinstance(action["run_id"], ObjectId):
            action["run_id"] = str(action["run_id"])
        actions_collection.replace_one({"_id": action_id}, action)
        print(f"Actions converted: {count}.", end="\r")
    t1 = datetime.now(UTC)
    duration = (t1 - t0).total_seconds()
    time_per_run = duration / count
    print()
    print(
        f"Conversion finished in {duration:.2f} seconds. Time per run: {1000 * time_per_run:.2f}ms.",
    )
    actions.close()
    client.close()
