from datetime import UTC, datetime

from fishtest.lru_cache import LRUCache
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
        self.cache = LRUCache(expiration=120)
        # Cache pending/blocked for 1s
        self.pending = LRUCache(size=1, expiration=1)
        self.blocked = LRUCache(size=1, expiration=1)

    def find_by_username(self, name):
        with self.cache.lock:
            if name not in self.cache:
                user = self.users.find_one({"username": name})
                if user is not None:
                    self.cache[name] = user
            return self.cache.get(name, refresh=False)

    def find_by_email(self, email):
        return self.users.find_one({"email": email})

    def authenticate(self, username, password):
        user = self.get_user(username)
        if not user or user["password"] != password:
            print(f"Invalid login: '{username}' '{password}", flush=True)
            return {"error": f"Invalid password for user: {username}"}
        if "blocked" in user and user["blocked"]:
            print(f"Blocked account: '{username}' '{password}'", flush=True)
            return {"error": f"Account blocked for user: {username}"}
        if "pending" in user and user["pending"]:
            print(f"Pending account: '{username}' '{password}'", flush=True)
            return {"error": f"Account pending for user: {username}"}

        return {"username": username, "authenticated": True}

    def get_users(self):
        return self.users.find(sort=[("_id", ASCENDING)])

    def get_pending(self):
        with self.pending.lock:
            if "value" not in self.pending:
                self.pending["value"] = list(
                    self.users.find({"pending": True}, sort=[("_id", ASCENDING)])
                )
            return self.pending.get("value", refresh=False)

    def get_blocked(self):
        with self.blocked.lock:
            if "value" not in self.blocked:
                self.blocked["value"] = list(
                    self.users.find({"blocked": True}, sort=[("_id", ASCENDING)])
                )
            return self.blocked.get("value", refresh=False)

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
        self.cache.clear()

    def create_user(self, username, password, email, tests_repo):
        try:
            if self.find_by_username(username) or self.find_by_email(email):
                return False
            # insert the new user in the db
            user = {
                "username": username,
                "password": password,
                "registration_time": datetime.now(UTC),
                "pending": True,
                "blocked": False,
                "email": email,
                "groups": [],
                "tests_repo": tests_repo,
                "machine_limit": DEFAULT_MACHINE_LIMIT,
            }
            validate_user(user)
            self.users.insert_one(user)
            self.pending.clear()
            self.blocked.clear()

            return True
        except Exception:
            return None

    def save_user(self, user):
        validate_user(user)
        self.users.replace_one({"_id": user["_id"]}, user)
        self.pending.clear()
        self.blocked.clear()
        self.cache.clear()

    def remove_user(self, user, rejector):
        result = self.users.delete_one({"_id": user["_id"]})
        if result.deleted_count > 0:
            # User successfully deleted
            self.pending.clear()
            self.cache.clear()
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
