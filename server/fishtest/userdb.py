from pymongo import ASCENDING
from vtjson import ValidationError, validate

from fishtest.lru_cache import lru_cache
import secrets
from fishtest.schemas import user_schema
from fishtest.lru_cache import lru_cache
import secrets
from datetime import UTC, datetime


DEFAULT_MACHINE_LIMIT = 16


def validate_user(user):
    try:
        validate(user_schema, user, "user")
    except ValidationError as e:
        message = f"The user object does not validate: {str(e)}"
        print(message, flush=True)
        raise ValidationError(message) from None


class UserDb:
    def __init__(self, db):
        self.db = db
        self.users = self.db["users"]
        self.user_cache = self.db["user_cache"]
        self.top_month = self.db["top_month"]

    def clear_cache(self):
        self.get_pending.cache_clear()
        self.get_blocked.cache_clear()
        self.find_by_username.cache_clear()

    @lru_cache(
        expiration=120, refresh=False, filter=lambda f, args, kw, val: val is not None
    )
    def find_by_username(self, name):
        return self.users.find_one({"username": name})

    def find_by_email(self, email):
        return self.users.find_one({"email": email})

    def authenticate(self, username, password):
        def fail(*, user_message: str, code: str, log_message: str | None = None):
            print(log_message or user_message, flush=True)
            return {"error": user_message, "error_code": code}

        user = self.get_user(username)
        if user is None:
            # Avoid username enumeration: user-facing message is identical to wrong-password.
            return fail(
                user_message="Invalid username or password.",
                code="invalid_credentials",
                log_message=f"Login failed (unknown user): '{username}'",
            )

        if user.get("password") != password:
            return fail(
                user_message="Invalid username or password.",
                code="invalid_credentials",
                log_message=f"Login failed (wrong password): '{username}'",
            )

        if user.get("blocked"):
            return fail(
                user_message="Your account is blocked.",
                code="blocked",
                log_message=f"Login rejected (account blocked): '{username}'",
            )

        if user.get("pending"):
            return fail(
                user_message="Your account is pending approval.",
                code="pending",
                log_message=f"Login rejected (pending approval): '{username}'",
            )

        return {"username": username, "authenticated": True}

    def is_account_restricted(self, user):
        if "blocked" in user and user["blocked"]:
            return "blocked"
        if "pending" in user and user["pending"]:
            return "pending"
        return None

    def get_users(self):
        return self.users.find(sort=[("_id", ASCENDING)])

    @lru_cache(expiration=1, refresh=False)
    def get_pending(self):
        return list(self.users.find({"pending": True}, sort=[("_id", ASCENDING)]))

    @lru_cache(expiration=1, refresh=False)
    def get_blocked(self):
        return list(self.users.find({"blocked": True}, sort=[("_id", ASCENDING)]))

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
                "api_key": self._generate_api_key(),
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
            self.clear_cache()

            return True
        except Exception:
            return None

    def save_user(self, user):
        validate_user(user)
        self.users.replace_one({"_id": user["_id"]}, user)
        self.clear_cache()

    def generate_api_key(self):
        return self._generate_api_key()

    def _generate_api_key(self):
        return f"ft_{secrets.token_urlsafe(32)}"

    def remove_user(self, user, rejector):
        result = self.users.delete_one({"_id": user["_id"]})
        if result.deleted_count > 0:
            # User successfully deleted
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
