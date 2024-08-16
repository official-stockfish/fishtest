import logging  # noqa: F401
import os
import platform
import subprocess
import sys
import time
import unittest
from pathlib import Path

from openlock import (
    FileLock,
    InvalidLockFile,
    InvalidOption,
    InvalidRelease,
    Timeout,
    get_defaults,
    logger,
    set_defaults,
)

logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(process)s:%(message)s")
logger.setLevel(logging.DEBUG)

IS_MACOS = "darwin" in platform.system().lower()
IS_WINDOWS = "windows" in platform.system().lower()

lock_file = "test.lock"
other_lock_file = "test1.lock"
defaults = get_defaults()


def show(mc):
    exception = mc.exception
    logger.debug(f"{exception.__class__.__name__}: {str(exception)}")


class TestOpenLock(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.DEBUG)
        for L in (lock_file, other_lock_file):
            try:
                os.remove(L)
            except OSError:
                pass
        set_defaults(**defaults)

    def test_acquire_release(self):
        r = FileLock(lock_file)
        self.assertFalse(r.locked())
        r.acquire(timeout=0)
        self.assertTrue(os.path.exists(lock_file))
        self.assertTrue(r.locked())
        self.assertTrue(r.getpid() == os.getpid())
        r.release()
        self.assertFalse(os.path.exists(lock_file))
        self.assertFalse(r.locked())

    def test_double_acquire(self):
        r = FileLock(lock_file)
        r.acquire(timeout=0)
        with self.assertRaises(Timeout):
            r.acquire(timeout=0)

    def test_invalid_release(self):
        r = FileLock(lock_file)
        with self.assertRaises(InvalidRelease):
            r.release()
        r.acquire(timeout=0)
        r.release()
        with self.assertRaises(InvalidRelease):
            r.release()

    def test_invalid_lock_file(self):
        with open(lock_file, "w") as f:
            pass
        r = FileLock(lock_file)
        r.acquire(timeout=0)
        r.release()
        with open(lock_file, "w") as f:
            f.write(f"{os.getpid()}\ndummy.py\n")
        r.acquire(timeout=0)
        self.assertTrue(os.getpid() == r.getpid())
        r.release()
        with open(lock_file, "w") as f:
            f.write("1\ntest_openlock.py\n")
        r.acquire(timeout=0)
        self.assertTrue(os.getpid() == r.getpid())
        r.release()

    def test_timeout(self):
        r = FileLock(lock_file)
        t = time.time()
        r.acquire(timeout=0)
        with self.assertRaises(Timeout):
            r.acquire(timeout=2)
        self.assertTrue(time.time() - t >= 2)

    def test_different_lock_files(self):
        r = FileLock(lock_file)
        s = FileLock(other_lock_file)
        r.acquire(timeout=0)
        s.acquire(timeout=0)
        self.assertTrue(r.locked())
        self.assertTrue(s.locked())

    def test_second_process(self):
        r = FileLock(lock_file)
        r.acquire(timeout=0)
        p = subprocess.run(
            [sys.executable, "_helper.py", lock_file, "1"], stdout=subprocess.PIPE
        )
        self.assertTrue(p.stdout.decode().strip() == "1")
        r.release()
        p = subprocess.Popen(
            [sys.executable, "_helper.py", lock_file, "2"], stdout=subprocess.PIPE
        )
        time.sleep(1)
        with self.assertRaises(Timeout):
            r.acquire(timeout=0)
        out, err = p.communicate()
        self.assertTrue(out.decode().strip() == "2")
        r.acquire(timeout=0)

    def test_invalid_exception(self):
        with open(lock_file, "w") as f:
            f.write("1\ntest_openlock.py\n")
        set_defaults(tries=0)
        r = FileLock(lock_file)
        with self.assertRaises(InvalidLockFile):
            r.acquire(timeout=0)

    def test_options(self):
        option_keys = set(get_defaults().keys())
        self.assertTrue(option_keys == {"tries", "retry_period", "race_delay"})
        options = {
            "tries": 5,
            "retry_period": 100.0,
            "race_delay": 100,
        }
        set_defaults(**options)
        options_ = get_defaults()
        self.assertTrue(options == options_)
        option_keys = set(options_)
        self.assertTrue(option_keys == {"tries", "retry_period", "race_delay"})

    def test_slow_system(self):
        r = FileLock(lock_file)
        r.acquire(timeout=0)
        r.release()
        set_defaults(race_delay=0)
        r = FileLock(lock_file)
        with self.assertWarns(UserWarning):
            with open(lock_file, "w") as f:
                f.write("1\ntest_openlock.py\n")
            r.acquire(timeout=0)

    def test_invalid_option(self):
        with self.assertRaises(InvalidOption) as e:
            set_defaults(tris=1)
        self.assertTrue("tris" in str(e.exception))

    def test_default_lock_file(self):
        r = FileLock()
        self.assertTrue(r.lock_file == Path("openlock.lock"))

    def test_latency(self):
        set_defaults(race_delay=1.0)
        r = FileLock(lock_file)
        t = time.time()
        r.acquire()
        tt = time.time()
        self.assertTrue(tt - t < 0.2)
        t = time.time()
        try:
            r.acquire(timeout=0)
        except Timeout:
            pass
        tt = time.time()
        self.assertTrue(tt - t < 0.2)
        r.release()
        with open(lock_file, "w") as f:
            f.write("1\ntest_openlock.py\n")
        t = time.time()
        r.acquire()
        tt = time.time()
        self.assertTrue(tt - t > 0.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
