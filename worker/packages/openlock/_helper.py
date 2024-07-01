import sys
import time

from openlock import FileLock, Timeout


def other_process1(lock_file):
    r = FileLock(lock_file)
    try:
        r.acquire(timeout=0)
    except Timeout:
        return 1
    return 0


def other_process2(lock_file):
    r = FileLock(lock_file)
    r.acquire(timeout=0)
    time.sleep(2)
    return 2


if __name__ == "__main__":
    lock_file = sys.argv[1]
    cmd = sys.argv[2]
    if cmd == "1":
        print(other_process1(lock_file))
    else:
        print(other_process2(lock_file))
