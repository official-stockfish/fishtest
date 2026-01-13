import atexit
import re

from fishtest.rundb import RunDb
from fishtest.util import FISHTEST, VALID_USERNAME_PATTERN


def get_rundb():
    rundb = RunDb(db_name=FISHTEST)
    atexit.register(rundb.conn.close)
    return rundb


def store_legacy_usernames(rundb):
    valid_user_regex = re.compile(VALID_USERNAME_PATTERN)
    users = rundb.userdb.users
    usernames = (doc["username"] for doc in users.find({}, {"username": 1, "_id": 0}))
    legacy_usernames = list(
        filter(lambda x: not valid_user_regex.fullmatch(x), usernames),
    )
    rundb.kvstore["legacy_usernames"] = legacy_usernames
    return legacy_usernames


if __name__ == "__main__":
    rundb = get_rundb()
    legacy_usernames = store_legacy_usernames(rundb)
    print("The following legacy usernames were found and stored:")
    for name in legacy_usernames:
        print(name)
