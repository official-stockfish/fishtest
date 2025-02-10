import atexit

from fishtest.rundb import RunDb


def get_rundb():
    rundb = RunDb(db_name="fishtest_tests")
    atexit.register(rundb.conn.close)
    return rundb


def find_run(arg="username", value="travis"):
    rundb = RunDb(db_name="fishtest_tests")
    atexit.register(rundb.conn.close)
    for run in rundb.get_unfinished_runs():
        if run["args"][arg] == value:
            return run
    return None
