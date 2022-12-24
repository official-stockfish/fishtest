from datetime import datetime

from bson.objectid import ObjectId
from fishtest.util import optional_key, union, validate, worker_name
from pymongo import DESCENDING

schema = union(
    {
        "action": "failed_task",
        "username": str,
        "worker": str,
        "run_id": ObjectId,
        "run": str,
        "task_id": int,
        "message": str,
    },
    {
        "action": "dead_task",
        "username": str,
        "worker": str,
        "run_id": ObjectId,
        "run": str,
        "task_id": int,
    },
    {"action": "system_event", "username": "fishtest.system", "message": str},
    {"action": "new_run", "username": str, "run_id": ObjectId, "run": str},
    {"action": "upload_nn", "username": str, "nn": str},
    {
        "action": "modify_run",
        "username": str,
        "run_id": ObjectId,
        "run": str,
        "message": str,
    },
    {"action": "delete_run", "username": str, "run_id": ObjectId, "run": str},
    {
        "action": "stop_run",
        "username": str,
        "worker": str,
        "run_id": ObjectId,
        "run": str,
        "task_id": int,
        "message": str,
    },
    {
        "action": "stop_run",
        "username": str,
        "run_id": ObjectId,
        "run": str,
        "message": str,
    },
    {"action": "approve_run", "username": str, "run_id": ObjectId, "run": str},
    {"action": "purge_run", "username": str, "run_id": ObjectId, "run": str},
    {
        "action": "block_user",
        "username": str,
        "user": str,
        "message": union("blocked", "unblocked"),
    },
)


class ActionDb:
    def __init__(self, db):
        self.db = db
        self.actions = self.db["actions"]

    def get_actions(
        self,
        username=None,
        action=None,
        text=None,
        limit=0,
        skip=0,
        utc_before=None,
        max_actions=None,
    ):
        q = {}
        if action:
            # update_stats is no longer used, but included for backward compatibility
            if action == "system_event":
                q["action"] = {"$in" : ["system_event", "update_stats"]}
            else:
                q["action"] = action
        else:
            q["action"] = {"$nin": ["system_event", "update_stats", "dead_task"]}
        if username:
            q["username"] = username
        if text:
            q["$text"] = {"$search": text}
        if utc_before:
            q["time"] = {"$lte": utc_before}

        if max_actions:
            count = self.actions.count_documents(q, limit=max_actions)
            limit = min(limit, max_actions - skip)
        else:
            count = self.actions.count_documents(q)

        actions_list = self.actions.find(
            q, limit=limit, skip=skip, sort=[("_id", DESCENDING)]
        )

        return actions_list, count

    def failed_task(self, username=None, run=None, task_id=None, message=None):
        task = run["tasks"][task_id]
        self.insert_action(
            action="failed_task",
            username=username,
            worker=worker_name(task["worker_info"]),
            run_id=run["_id"],
            run=run["args"]["new_tag"],
            task_id=task_id,
            message=message[:1024],
        )

    def stop_run(self, username=None, run=None, task_id=None, message=None):
        if task_id is not None:
            task = run["tasks"][task_id]
            self.insert_action(
                action="stop_run",
                username=username,
                worker=worker_name(task["worker_info"]),
                run_id=run["_id"],
                run=run["args"]["new_tag"],
                task_id=task_id,
                message=message[:1024],
            )
        else:
            self.insert_action(
                action="stop_run",
                username=username,
                run_id=run["_id"],
                run=run["args"]["new_tag"],
                message=message[:1024],
            )

    def dead_task(self, username=None, run=None, task_id=None):
        task = run["tasks"][task_id]
        self.insert_action(
            action="dead_task",
            username=username,
            worker=worker_name(task["worker_info"]),
            run_id=run["_id"],
            run=run["args"]["new_tag"],
            task_id=task_id,
        )

    def system_event(self, message=None):
        self.insert_action(
            action="system_event",
            username="fishtest.system",
            message=message,
        )

    def new_run(self, username=None, run=None):
        self.insert_action(
            action="new_run",
            username=username,
            run_id=run["_id"],
            run=run["args"]["new_tag"],
        )

    def upload_nn(self, username=None, nn=None):
        self.insert_action(
            action="upload_nn",
            username=username,
            nn=nn,
        )

    def modify_run(self, username=None, run=None, message=None):
        self.insert_action(
            action="modify_run",
            username=username,
            run_id=run["_id"],
            run=run["args"]["new_tag"],
            message=message,
        )

    def delete_run(self, username=None, run=None):
        self.insert_action(
            action="delete_run",
            username=username,
            run_id=run["_id"],
            run=run["args"]["new_tag"],
        )

    def approve_run(self, username=None, run=None):
        self.insert_action(
            action="approve_run",
            username=username,
            run_id=run["_id"],
            run=run["args"]["new_tag"],
        )

    def purge_run(self, username=None, run=None):
        self.insert_action(
            action="purge_run",
            username=username,
            run_id=run["_id"],
            run=run["args"]["new_tag"],
        )

    def block_user(self, username=None, user=None, message=None):
        self.insert_action(
            action="block_user",
            username=username,
            user=user,
            message=message,
        )

    def insert_action(self, **action):
        ret = validate(schema, action, "action", strict=True)
        if ret == "":
            action["time"] = datetime.utcnow()
            self.actions.insert_one(action)
        else:
            raise Exception("Validation failed with error '{}'".format(ret))
