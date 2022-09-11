from datetime import datetime

from pymongo import DESCENDING


class ActionDb:
    def __init__(self, db):
        self.db = db
        self.actions = self.db["actions"]

    def get_actions(self, max_num, action=None, username=None, before=None):
        q = {}
        if action:
            q["action"] = action
        else:
            q["action"] = {"$nin": ["update_stats", "dead_task"]}
        if username:
            q["username"] = username
        if before:
            q["time"] = {"$lte": before}
        return self.actions.find(q, sort=[("_id", DESCENDING)], limit=max_num)

    def update_stats(self):
        self._new_action("fishtest.system", "update_stats", "")

    def new_run(self, username, run):
        self._new_action(username, "new_run", run)

    def upload_nn(self, username, network):
        self._new_action(username, "upload_nn", network)

    def modify_run(self, username, before, after):
        self._new_action(username, "modify_run", {"before": before, "after": after})

    def delete_run(self, username, run):
        self._new_action(username, "delete_run", run)

    def stop_run(self, username, run):
        self._new_action(username, "stop_run", run)

    def approve_run(self, username, run):
        self._new_action(username, "approve_run", run)

    def purge_run(self, username, run):
        self._new_action(username, "purge_run", run)

    def block_user(self, username, data):
        self._new_action(username, "block_user", data)

    def change_group(self, username, data):
        self._new_action(username, "change_group", data)

    def failed_task(self, username, run):
        self._new_action(username, "failed_task", run)

    def dead_task(self, username, run):
        self._new_action(username, "dead_task", run)

    def _new_action(self, username, action, data):
        self.actions.insert_one(
            {
                "username": username,
                "action": action,
                "data": data,
                "time": datetime.utcnow(),
            }
        )
