import datetime
from fishtest.actiondb import run_name
from fishtest.util import hex_print
import pymongo

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
        if "data" in action:
            del action["data"]
        if "run" in action and "run_id" in action:
            run_id = action["run_id"]
            run = action["run"]
            if "-" in run:
                run = runs_collection.find_one({"_id": run_id})
                if run is None:
                    continue
                action["run"] = run_name(run)
            else:
                action["run"] = run[:23] + "-" + hex_print(run_id)[0:7]

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
