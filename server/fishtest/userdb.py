import sys
import threading
import time
from datetime import datetime, timezone

from fishtest.schemas import user_schema
from pymongo import ASCENDING
from vtjson import ValidationError, validate

DEFAULT_MACHINE_LIMIT = 16


def validate_user(user):
    try:
        validate(user_schema, user, "user")
    except ValidationError as e:
        message = f"The user object does not validate: {str(e)}"
        print(message, flush=True)
        raise Exception(message)


class UserDb:
    def __init__(self, db):
        self.db = db
        self.users = self.db["users"]
        self.user_cache = self.db["user_cache"]
        self.top_month = self.db["top_month"]

    # Cache user lookups for 120s
    user_lock = threading.Lock()
    cache = {}

    def find_by_username(self, name):
        with self.user_lock:
            user = self.cache.get(name)
            if user and time.time() < user["time"] + 120:
                return user["user"]
            user = self.users.find_one({"username": name})
            if user is not None:
                self.cache[name] = {"user": user, "time": time.time()}
            return user

    def find_by_email(self, email):
        return self.users.find_one({"email": email})

    def clear_cache(self):
        with self.user_lock:
            self.cache.clear()

    def authenticate(self, username, password):
        user = self.get_user(username)
        if not user or user["password"] != password:
            sys.stderr.write("Invalid login: '{}' '{}'\n".format(username, password))
            return {"error": "Invalid password for user: {}".format(username)}
        if "blocked" in user and user["blocked"]:
            sys.stderr.write("Blocked account: '{}' '{}'\n".format(username, password))
            return {"error": "Account blocked for user: {}".format(username)}
        if "pending" in user and user["pending"]:
            sys.stderr.write("Pending account: '{}' '{}'\n".format(username, password))
            return {"error": "Account pending for user: {}".format(username)}

        return {"username": username, "authenticated": True}

    def get_users(self):
        return self.users.find(sort=[("_id", ASCENDING)])

    # Cache pending for 1s
    last_pending_time = 0
    last_blocked_time = 0
    last_pending = None
    pending_lock = threading.Lock()
    blocked_lock = threading.Lock()

    def get_pending(self):
        with self.pending_lock:
            if time.time() > self.last_pending_time + 1:
                self.last_pending = list(
                    self.users.find({"pending": True}, sort=[("_id", ASCENDING)])
                )
                self.last_pending_time = time.time()
            return self.last_pending

    def get_blocked(self):
        with self.blocked_lock:
            if time.time() > self.last_blocked_time + 1:
                self.last_blocked = list(
                    self.users.find({"blocked": True}, sort=[("_id", ASCENDING)])
                )
                self.last_blocked_time = time.time()
            return self.last_blocked

    def get_user(self, username):
        return self.find_by_username(username)

    def get_user_groups(self, username):
        user = self.get_user(username)
        if user is not None:
            groups = user["groups"]
            return groups

    def add_user_group(self, username, group):
        user = self.get_user(username)
        user["groups"].append(group)
        validate_user(user)
        self.users.replace_one({"_id": user["_id"]}, user)
        self.clear_cache()

    def create_user(self, username, password, email, tests_repo):
        try:
            if self.find_by_username(username) or self.find_by_email(email):
                return False
            # insert the new user in the db
            user = {
                "username": username,
                "password": password,
                "registration_time": datetime.now(timezone.utc),
                "pending": True,
                "blocked": False,
                "email": email,
                "groups": [],
                "tests_repo": tests_repo,
                "machine_limit": DEFAULT_MACHINE_LIMIT,
            }
            validate_user(user)
            self.users.insert_one(user)
            self.last_pending_time = 0
            self.last_blocked_time = 0

            return True
        except:
            return None

    def save_user(self, user):
        validate_user(user)
        self.users.replace_one({"_id": user["_id"]}, user)
        self.last_pending_time = 0
        self.last_blocked_time = 0
        self.clear_cache()

    def remove_user(self, user, rejector):

        result = self.users.delete_one({"_id": user["_id"]})
        if result.deleted_count > 0:
            # User successfully deleted
            self.last_pending_time = 0
            self.clear_cache()
            # logs rejected users to the server
            print(
                f"user: {user['username']} with email: {user['email']} was rejected by: {rejector}",
                flush=True,
            )
            return True
        else:
            # User not found
            return False

    def get_machine_limit(self, username):
        user = self.get_user(username)
        if user and "machine_limit" in user:
            return user["machine_limit"]
        return DEFAULT_MACHINE_LIMIT
