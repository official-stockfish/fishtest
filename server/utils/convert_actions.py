import datetime

import pymongo

if __name__ == "__main__":
    client = pymongo.MongoClient()
    actions_collection = client["fishtest_new"]["actions"]
    actions = actions_collection.find({}).sort("_id", 1)
    count = 0
    print("Starting conversion...")
    t0 = datetime.datetime.utcnow()
    for action in actions:
        count += 1
        action_id = action["_id"]
        if "data" in action:
            del action["data"]
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
