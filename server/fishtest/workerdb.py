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

    def update_worker(self, worker_name, blocked=None, message=None, username=None):
        current_worker = self.get_worker(worker_name)

        new_note = None
        if message:
            time = datetime.now(timezone.utc)
            new_note = {
                "time": time,
                "username": username,
                "message": message,
            }

        if current_worker:
            notes = current_worker.get("notes", [])
            if new_note:
                notes.append(new_note)
        else:
            notes = [new_note] if new_note else []

        r = {
            "worker_name": worker_name,
            "blocked": blocked,
            "notes": notes,
            "last_updated": datetime.now(timezone.utc),
        }
        validate(worker_schema, r, "worker")  # may throw exception
        self.workers.replace_one({"worker_name": worker_name}, r, upsert=True)

    def get_blocked_workers(self):
        q = {"blocked": True}
        return list(self.workers.find(q))
