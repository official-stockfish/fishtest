from datetime import datetime, timezone

from fishtest.util import hex_print, worker_name
from fishtest.validate import union, validate
from pymongo import DESCENDING

schema = union(
    {
        "action": "failed_task",
        "username": str,
        "worker": str,
        "run_id": str,
        "run": str,
        "task_id": int,
        "message": str,
    },
    {
        "action": "crash_or_time",
        "username": str,
        "worker": str,
        "run_id": str,
        "run": str,
        "task_id": int,
        "message": str,
    },
    {
        "action": "dead_task",
        "username": str,
        "worker": str,
        "run_id": str,
        "run": str,
        "task_id": int,
    },
    {"action": "system_event", "username": "fishtest.system", "message": str},
    {
        "action": "new_run",
        "username": str,
        "run_id": str,
        "run": str,
        "message": str,
    },
    {"action": "upload_nn", "username": str, "nn": str},
    {
        "action": "modify_run",
        "username": str,
        "run_id": str,
        "run": str,
        "message": str,
    },
    {"action": "delete_run", "username": str, "run_id": str, "run": str},
    {
        "action": "stop_run",
        "username": str,
        "worker": str,
        "run_id": str,
        "run": str,
        "task_id": int,
        "message": str,
    },
    {
        "action": "stop_run",
        "username": str,
        "run_id": str,
        "run": str,
        "message": str,
    },
    {
        "action": "finished_run",
        "username": str,
        "run_id": str,
        "run": str,
        "message": str,
    },
    {"action": "approve_run", "username": str, "run_id": str, "run": str},
    {"action": "purge_run", "username": str, "run_id": str, "run": str, "message": str},
    {
        "action": "block_user",
        "username": str,
        "user": str,
        "message": union("blocked", "unblocked"),
    },
    {
        "action": "block_worker",
        "username": str,
        "worker": str,
        "message": union("blocked", "unblocked"),
    },
)


def run_name(run):
    run_id = str(run["_id"])
    run = run["args"]["new_tag"]
    return run[:23] + "-" + hex_print(run_id)[0:7]


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
        run_id=None,
        max_actions=None,
    ):
        q = {}
        if action:
            # update_stats is no longer used, but included for backward compatibility
            if action == "system_event":
                q["action"] = {"$in": ["system_event", "update_stats"]}
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
        if run_id:
            q["run_id"] = str(run_id)

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
            run=run_name(run),
            task_id=task_id,
            message=message[:1024],
        )

    def crash_or_time(self, username=None, run=None, task_id=None, message=None):
        task = run["tasks"][task_id]
        self.insert_action(
            action="crash_or_time",
            username=username,
            worker=worker_name(task["worker_info"]),
            run_id=run["_id"],
            run=run_name(run),
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
                run=run_name(run),
                task_id=task_id,
                message=message[:1024],
            )
        else:
            self.insert_action(
                action="stop_run",
                username=username,
                run_id=run["_id"],
                run=run_name(run),
                message=message[:1024],
            )

    def dead_task(self, username=None, run=None, task_id=None):
        task = run["tasks"][task_id]
        self.insert_action(
            action="dead_task",
            username=username,
            worker=worker_name(task["worker_info"]),
            run_id=run["_id"],
            run=run_name(run),
            task_id=task_id,
        )

    def system_event(self, message=None):
        self.insert_action(
            action="system_event",
            username="fishtest.system",
            message=message,
        )

    def new_run(self, username=None, run=None, message=None):
        self.insert_action(
            action="new_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
            message=message,
        )

    def finished_run(self, username=None, run=None, message=None):
        self.insert_action(
            action="finished_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
            message=message,
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
            run=run_name(run),
            message=message,
        )

    def delete_run(self, username=None, run=None):
        self.insert_action(
            action="delete_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
        )

    def approve_run(self, username=None, run=None):
        self.insert_action(
            action="approve_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
        )

    def purge_run(self, username=None, run=None, message=None):
        self.insert_action(
            action="purge_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
            message=message,
        )

    def block_user(self, username=None, user=None, message=None):
        self.insert_action(
            action="block_user",
            username=username,
            user=user,
            message=message,
        )

    def block_worker(self, username=None, worker=None, message=None):
        self.insert_action(
            action="block_worker",
            username=username,
            worker=worker,
            message=message,
        )

    def insert_action(self, **action):
        if "run_id" in action:
            action["run_id"] = str(action["run_id"])
        ret = validate(schema, action, "action", strict=True)
        if ret == "":
            action["time"] = datetime.now(timezone.utc).timestamp()
            self.actions.insert_one(action)
        else:
            raise Exception("Validation failed with error '{}'".format(ret))
