import sys
import threading
import time
from datetime import datetime
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, HashingError, InvalidHash, VerificationError
from pymongo import ASCENDING


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

    def hash_password(self, password,
        time_cost: int = 3, memory_cost: int = 12288, parallelism: int = 1,
        hash_len: int = 32, salt_len: int = 16):
        return PasswordHasher().hash(password)

    @lru_cache(maxsize=128)
    def check_password(self, hashed_password, password):
        try:
            return PasswordHasher().verify(hashed_password, password)
        except InvalidHash as e:
            print("InvalidHash:", e, sep="\n")
        except VerifyMismatchError as e:
            print("VerifyMismatchError:", e, sep="\n")
        except HashingError as e:
            print("HashingError:", e, sep="\n")
        except VerificationError as e:
            print("VerificationError:", e, sep="\n")
        except Exception as e:
            print("Exception:", e, sep="\n")
        return False

    def authenticate(self, username, password):
        user = self.find(username)
        if user:
            if "blocked" in user and user["blocked"]:
                sys.stderr.write("Blocked login attempt: '{}'\n".format(username))
                return {"error": "Account blocked for user: {}".format(username)}
            if self.check_password(user["password"], password):
                return {"username": username, "authenticated": True}
            # remove elif logic after all the passwords in userdb are hashed
            elif user["password"] == password:
                user["password"] = self.hash_password(user["password"])
                self.save_user(user)
                return {"username": username, "authenticated": True}
            else:
                return {"error": "Invalid password"}
        else:
            return {"error": "Invalid username"}

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
        self.users.replace_one({"_id": user["_id"]}, user)
        self.clear_cache()

    def create_user(self, username, password, email):
        try:
            if self.find(username):
                return False
            # insert the new user in the db
            self.users.insert_one(
                {
                    "username": username,
                    "password": password,
                    "registration_time": datetime.utcnow(),
                    "blocked": True,
                    "email": email,
                    "groups": [],
                    "tests_repo": "",
                }
            )
            self.last_pending_time = 0

            return True
        except:
            return False

    def save_user(self, user):
        self.users.replace_one({"_id": user["_id"]}, user)
        self.last_pending_time = 0
        self.clear_cache()

    def get_machine_limit(self, username):
        user = self.find(username)
        if user and "machine_limit" in user:
            return user["machine_limit"]
        return 16
