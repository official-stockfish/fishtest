from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database
from vtjson import validate

from fishtest.schemas import worker_schema


class WorkerDb:
    def __init__(self, db: Database[dict[str, Any]]) -> None:
        self.db: Database[dict[str, Any]] = db
        self.workers: Collection[dict[str, Any]] = self.db["workers"]

    def get_worker(
        self,
        worker_name: str,
    ) -> dict[str, Any]:
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

    def update_worker(
        self,
        worker_name: str,
        blocked: bool | None = None,
        message: str | None = None,
    ) -> None:
        r = {
            "worker_name": worker_name,
            "blocked": blocked,
            "message": message,
            "last_updated": datetime.now(UTC),
        }
        validate(worker_schema, r, "worker")  # may throw exception
        self.workers.replace_one({"worker_name": worker_name}, r, upsert=True)

    def get_blocked_workers(self) -> list[dict[str, Any]]:
        q = {"blocked": True}
        return list(self.workers.find(q))
