from datetime import UTC, datetime

from bson.objectid import ObjectId
from pymongo import DESCENDING
from pymongo.errors import OperationFailure
from vtjson import ValidationError, validate

from fishtest.schemas import ACTION_MESSAGE_SIZE, action_schema
from fishtest.util import hex_print, worker_name


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

        # Prefer time-based pagination indexes for the common $nin case.
        hint = None
        if "$text" not in q:
            if username:
                hint = "actions_user_time_id"
            elif run_id:
                hint = "actions_run_time_id"
            elif action and action != "system_event":
                hint = "actions_action_time_id"
            else:
                hint = "actions_time_id"

        if max_actions:
            count_kwargs = {"limit": max_actions}
            if hint:
                count_kwargs["hint"] = hint
            try:
                count = self.actions.count_documents(q, **count_kwargs)
            except OperationFailure as e:
                # Be resilient if indexes haven't been created yet (bad hint).
                print(
                    f"ActionDb.get_actions: count_documents hint={hint!r} failed ({e}); retrying without hint",
                    flush=True,
                )
                self.log_message(
                    username="fishtest.system",
                    message=f"ActionDb.get_actions: count_documents hint={hint!r} failed; retrying without hint"[
                        :ACTION_MESSAGE_SIZE
                    ],
                )
                count = self.actions.count_documents(q, limit=max_actions)
            limit = max(0, min(limit, max_actions - skip))

            # Avoid find(limit=0): Mongo treats that as "no limit".
            if skip >= max_actions or limit <= 0:
                return [], count
        else:
            count = self.actions.count_documents(q)

        find_kwargs = {
            "limit": limit,
            "skip": skip,
            "sort": [("time", DESCENDING), ("_id", DESCENDING)],
        }
        if hint:
            find_kwargs["hint"] = hint
        try:
            actions_list = self.actions.find(q, **find_kwargs)
        except OperationFailure as e:
            # Be resilient if indexes haven't been created yet (bad hint).
            print(
                f"ActionDb.get_actions: find hint={hint!r} failed ({e}); retrying without hint",
                flush=True,
            )
            self.log_message(
                username="fishtest.system",
                message=f"ActionDb.get_actions: find hint={hint!r} failed; retrying without hint"[
                    :ACTION_MESSAGE_SIZE
                ],
            )
            find_kwargs.pop("hint", None)
            actions_list = self.actions.find(q, **find_kwargs)

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
            message=message[:ACTION_MESSAGE_SIZE],
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
            message=message[:ACTION_MESSAGE_SIZE],
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
                message=message[:ACTION_MESSAGE_SIZE],
            )
        else:
            self.insert_action(
                action="stop_run",
                username=username,
                run_id=run["_id"],
                run=run_name(run),
                message=message[:ACTION_MESSAGE_SIZE],
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

    def approve_run(self, username=None, run=None, message=None):
        self.insert_action(
            action="approve_run",
            username=username,
            run_id=run["_id"],
            run=run_name(run),
            message=message,
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

    def accept_user(self, username=None, user=None, message=None):
        self.insert_action(
            action="accept_user",
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

    def log_message(self, username=None, worker=None, message=None):
        if worker is None:
            self.insert_action(
                action="log_message",
                username=username,
                message=message,
            )
        else:
            self.insert_action(
                action="log_message",
                username=username,
                worker=worker,
                message=message,
            )

    def insert_action(self, **action):
        if "run_id" in action:
            action["run_id"] = str(action["run_id"])
        action["time"] = datetime.now(UTC).timestamp()
        action["_id"] = ObjectId()
        try:
            validate(action_schema, action, "action")
        except ValidationError as e:
            message = (
                f"Internal Error. Request {str(action)} does not validate: {str(e)}"
            )
            print(message, flush=True)
            self.log_message(
                username="fishtest.system",
                message=message,
            )
            return
        self.actions.insert_one(action)
