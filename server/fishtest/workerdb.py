from datetime import datetime, timezone

from fishtest.schemas import worker_schema
from vtjson import validate


class WorkerDb:
    def __init__(self, db):
        self.db = db
        self.workers = self.db["workers"]

    def get_worker(
        self,
        worker_name,
    ):
        q = {"worker_name": worker_name}
        r = self.workers.find_one(
            q,
        )
        if r is None:
            return {
                "worker_name": worker_name,
                "blocked": False,
                "message": "",
                "last_updated": None,
            }
        else:
            return r

    def update_worker(self, worker_name, blocked=None, message=None):
        r = {
            "worker_name": worker_name,
            "blocked": blocked,
            "message": message,
            "last_updated": datetime.now(timezone.utc),
        }
        validate(worker_schema, r, "worker")  # may throw exception
        self.workers.replace_one({"worker_name": worker_name}, r, upsert=True)

    def get_blocked_workers(self):
        q = {"blocked": True}
        return list(self.workers.find(q))
