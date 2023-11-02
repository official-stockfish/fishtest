import sys
import threading
import time
from datetime import datetime, timezone

from bson.objectid import ObjectId
from fishtest.util import optional_key, validate
from pymongo import ASCENDING

schema = {
    optional_key("_id"): ObjectId,
    "username": str,
    "password": str,
    "registration_time": datetime,
    "blocked": bool,
    "email": str,
    "groups": list,
    "tests_repo": str,
    "machine_limit": int,
}

DEFAULT_MACHINE_LIMIT = 16


class UserDb:
    def __init__(self, db):
        self.db = db
        self.users = self.db["users"]
        self.user_cache = self.db["user_cache"]
        self.top_month = self.db["top_month"]

    # Cache user lookups for 120s
    user_lock = threading.Lock()
    cache = {}

    def find(self, name):
        with self.user_lock:
            if name in self.cache:
                u = self.cache[name]
                if u["time"] > time.time() - 120:
                    return u["user"]
            user = self.users.find_one({"username": name})
            if not user:
                return None
            self.cache[name] = {"user": user, "time": time.time()}
            return user

    def clear_cache(self):
        with self.user_lock:
            self.cache.clear()

    def authenticate(self, username, password):
        user = self.find(username)
        if not user or user["password"] != password:
            print("Invalid login: '{}' '{}'\n".format(username, password), flush=True)
            return {"error": "Invalid password for user: {}".format(username)}
        if "blocked" in user and user["blocked"]:
            print("Blocked login: '{}' '{}'\n".format(username, password), flush=True)
            return {"error": "Account blocked for user: {}".format(username)}

        return {"username": username, "authenticated": True}

    def get_users(self):
        return self.users.find(sort=[("_id", ASCENDING)])

    # Cache pending for 1s
    last_pending_time = 0
    last_pending = None
    pending_lock = threading.Lock()

    def get_pending(self):
        with self.pending_lock:
            if time.time() > self.last_pending_time + 1:
                self.last_pending = list(
                    self.users.find({"blocked": True}, sort=[("_id", ASCENDING)])
                )
                self.last_pending_time = time.time()
            return self.last_pending

    def get_user(self, username):
        return self.find(username)

    def get_user_groups(self, username):
        user = self.find(username)
        if user:
            groups = user["groups"]
            return groups

    def add_user_group(self, username, group):
        user = self.find(username)
        user["groups"].append(group)
        assert validate(schema, user, "user", strict=True) == ""
        self.users.replace_one({"_id": user["_id"]}, user)
        self.clear_cache()

    def create_user(self, username, password, email):
        try:
            if self.find(username):
                return False
            # insert the new user in the db
            user = {
                "username": username,
                "password": password,
                "registration_time": datetime.now(timezone.utc),
                "blocked": True,
                "email": email,
                "groups": [],
                "tests_repo": "",
                "machine_limit": DEFAULT_MACHINE_LIMIT,
            }
            assert validate(schema, user, "user", strict=True) == ""
            self.users.insert_one(user)
            self.last_pending_time = 0

            return True
        except:
            return False

    def save_user(self, user):
        assert validate(schema, user, "user", strict=True) == ""
        self.users.replace_one({"_id": user["_id"]}, user)
        self.last_pending_time = 0
        self.clear_cache()

    def get_machine_limit(self, username):
        user = self.find(username)
        if user and "machine_limit" in user:
            return user["machine_limit"]
        return DEFAULT_MACHINE_LIMIT
