from datetime import datetime

from pymongo import DESCENDING

"""
schema = {
"action" : str,
"username" : str,
"time" : datetime.datetime,
optional_key("message") : str,
optional_key("user") : str,
optional_key("run_id") : ObjectId,
optional_key("run") : str,
optional_key("worker") : str,
optional_key("nn") : str,
}
"""


def expand_action(action):
    action["message"] = ""
    if action["action"] == "update_stats":
        action["message"] = "Update user statistics"
    elif action["action"] == "upload_nn":
        action["nn"] = action["data"]
    elif action["action"] == "block_user":
        action["message"] = "blocked" if action["data"]["blocked"] else "unblocked"
        action["user"] = action["data"]["user"]
    elif action["action"] == "modify_run":
        action["run"] = action["data"]["before"]["args"]["new_tag"]
        action["run_id"] = action["data"]["before"]["_id"]
        message = []

        for k in ("priority", "num_games", "throughput", "auto_purge"):
            try:
                before = action["data"]["before"]["args"][k]
                after = action["data"]["after"]["args"][k]
            except KeyError:
                pass
            else:
                if before != after:
                    message.append(
                        "{} changed from {} to {}".format(
                            k.replace("_", "-"), before, after
                        )
                    )

        action["message"] = "modify: " + ", ".join(message)
    else:
        action["run"] = action["data"]["args"]["new_tag"]
        action["run_id"] = action["data"]["_id"]
        message = ""
        if action["action"] == "failed_task":
            message = action["data"].get("failure_reason", "Unknown reason")
        if action["action"] == "dead_task":
            message = action["data"].get("dead_task")
        if action["action"] == "stop_run":
            message = action["data"].get("stop_reason", "User stop")
        # Dirty hack (will be changed)
        try:
            chunks = message.split()
            if len(chunks) > 2:
                action["task_id"] = int(chunks[1][:-1])
                action["worker"] = chunks[3][:-1]
                proto_message = " ".join(chunks[5:])
                # get rid of ' '.
                if "not authorized" not in proto_message:
                    action["message"] = proto_message[1:-1]
                else:
                    action["message"] = proto_message.replace("'", "")
            else:
                action["message"] = message
        except Exception as e:
            action["message"] = message


class ActionDb:
    def __init__(self, db):
        self.db = db
        self.actions = self.db["actions"]

    def get_actions(
        self,
        username=None,
        action=None,
        limit=0,
        skip=0,
        utc_before=None,
        max_actions=None,
    ):
        q = {}
        if action:
            q["action"] = action
        else:
            q["action"] = {"$nin": ["update_stats", "dead_task"]}
        if username:
            q["username"] = username
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

    def failed_task(self, username, run):
        self._new_action(username, "failed_task", run)

    def dead_task(self, username, run):
        self._new_action(username, "dead_task", run)

    def _new_action(self, username, action, data):
        action = {
            "username": username,
            "action": action,
            "data": data,
            "time": datetime.utcnow(),
        }
        expand_action(action)
        self.actions.insert_one(action)
