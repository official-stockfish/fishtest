import threading
import time
from enum import IntEnum

from bson.errors import InvalidId
from bson.objectid import ObjectId
from vtjson import validate

from fishtest.lru_cache import lru_cache
from fishtest.schemas import cache_schema
from fishtest.schemas import run_id as run_id_schema


class Prio(IntEnum):
    NORMAL = 0
    MEDIUM = 1
    HIGH = 2
    SAVE_NOW = 1000


class RunCache:
    def __init__(self, runs):
        # For documentation of the cache format see "cache_schema" in schemas.py.
        self.runs = runs
        self.run_cache_lock = threading.Lock()
        self.run_cache = {}

    def active_run_lock(self, run_id):
        run_id = str(run_id)
        return self.__active_run_lock(run_id)

    @lru_cache(expiration=10000)
    def __active_run_lock(self, run_id):
        # assertion!
        validate(run_id_schema, run_id)
        return threading.RLock()

    def buffer(self, run, *, priority=Prio.NORMAL, create=False):
        """
        Guidelines for priority
        =======================
        Prio.MEDIUM: finished task
        Prio.HIGH: new task
        Prio.SAVE_NOW: new run (combined with create=True),
                       finished run, modify/approve/purge run
        Prio.NORMAL: all other uses
        """
        if create and priority != Prio.SAVE_NOW:
            print(
                "Warning: setting create=True in buffer() without",
                "using priority=Prio.SAVE_NOW has no effect.",
                flush=True,
            )
            return

        flush = priority == Prio.SAVE_NOW
        run_id = str(run["_id"])
        with self.run_cache_lock:
            if flush:
                self.run_cache[run_id] = {
                    "is_changed": False,
                    "last_access_time": time.time(),
                    "last_sync_time": time.time(),
                    "priority": 0,
                    "run": run,
                }
            else:
                if run_id in self.run_cache:
                    last_sync_time = self.run_cache[run_id]["last_sync_time"]
                    priority = max(priority, self.run_cache[run_id]["priority"])
                else:
                    last_sync_time = time.time()
                self.run_cache[run_id] = {
                    "is_changed": True,
                    "last_access_time": time.time(),
                    "last_sync_time": last_sync_time,
                    "priority": priority,
                    "run": run,
                }
        if flush:
            with self.active_run_lock(run_id):
                r = self.runs.replace_one({"_id": ObjectId(run_id)}, run, upsert=create)
                if not create and r.matched_count == 0:
                    print(f"Buffer: update of {run_id} failed", flush=True)

    def get_run(self, run_id):
        run_id = str(run_id)
        try:
            run_id_obj = ObjectId(run_id)
        except InvalidId:
            return None

        with self.run_cache_lock:
            if run_id in self.run_cache:
                self.run_cache[run_id]["last_access_time"] = time.time()
                return self.run_cache[run_id]["run"]
            run = self.runs.find_one({"_id": run_id_obj})
            if run is not None:
                self.run_cache[run_id] = {
                    "last_access_time": time.time(),
                    "last_sync_time": time.time(),
                    "priority": 0,
                    "run": run,
                    "is_changed": False,
                }
                return run
        return None

    def flush_buffers(self):
        oldest_entry = None
        old = float("inf")
        with self.run_cache_lock:
            for cache_entry in self.run_cache.values():
                # Make sure that every run will be saved to disk eventually,
                # even if there are always cache entries with priority 1.
                t = -60 * cache_entry["priority"] + cache_entry["last_sync_time"]
                if cache_entry["is_changed"] and t < old:
                    old = t
                    oldest_entry = cache_entry
            if oldest_entry is not None:
                oldest_run = oldest_entry["run"]
                oldest_run_id = oldest_run["_id"]
                oldest_entry["is_changed"] = False
                oldest_entry["last_sync_time"] = time.time()
                oldest_entry["priority"] = 0

        if oldest_entry is not None:
            with self.active_run_lock(str(oldest_run_id)):
                self.runs.replace_one({"_id": oldest_run_id}, oldest_run)

    def flush_all(self):
        flush_list = []
        with self.run_cache_lock:
            for run_id, entry in self.run_cache.items():
                if entry["is_changed"]:
                    entry["is_changed"] = False
                    entry["last_sync_time"] = time.time()
                    entry["priority"] = 0
                    flush_list.append((run_id, entry))
        for run_id, entry in flush_list:
            with self.active_run_lock(run_id):
                self.runs.replace_one({"_id": ObjectId(run_id)}, entry["run"])

    def clean_cache(self):
        now = time.time()
        with self.run_cache_lock:
            # We make this a list to be able to change run_cache during iteration
            for run_id, cache_entry in list(self.run_cache.items()):
                run = cache_entry["run"]
                # Presently run["finished"] implies run["cores"]==0 but
                # this was not always true in the past.
                if (
                    not cache_entry["is_changed"]
                    and (run["cores"] <= 0 or run["finished"])
                    and cache_entry["last_access_time"] < now - 300
                ):
                    del self.run_cache[run_id]

    def validate(self):
        with self.run_cache_lock:
            validate(
                cache_schema,
                self.run_cache,
                name="run_cache",
                subs={"runs_schema": dict},
            )
