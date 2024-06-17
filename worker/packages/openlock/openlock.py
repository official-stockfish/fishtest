import atexit
import logging
import os
import threading
import time
from pathlib import Path

__version__ = "0.0.1"

logger = logging.getLogger(__name__)


class OpenLockException(Exception):
    pass


class Timeout(OpenLockException):
    pass


# These deal with stale lock file detection
_touch_period_default = 2.0
_stale_timeout_default = 3.0
_stale_race_delay_default = 0.5

# This deals with acquiring locks
_retry_period_default = 0.3


class FileLock:
    def __init__(
        self,
        lock_file,
        detect_stale=False,
        timeout=None,
        _retry_period=_retry_period_default,
        _touch_period=_touch_period_default,
        _stale_timeout=_stale_timeout_default,
        _stale_race_delay=_stale_race_delay_default,
    ):
        self.__lock_file = Path(lock_file)
        self.__timeout = timeout
        self.__detect_stale = detect_stale
        self.__lock = threading.Lock()
        self.__acquired = False
        self.__timer = None
        self.__retry_period = _retry_period
        self.__touch_period = _touch_period
        self.__stale_timeout = _stale_timeout
        self.__stale_race_delay = _stale_race_delay
        logger.debug(f"{self} created")

    def __touch(self):
        self.__lock_file.touch()
        self.__timer = threading.Timer(self.__touch_period, self.__touch)
        self.__timer.daemon = True
        self.__timer.start()
        if not self.__acquired:
            self.__timer.cancel()

    def __is_stale(self):
        try:
            mtime = os.path.getmtime(self.__lock_file)
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error(
                "Unable to get the modification time of the lock file "
                f"{self.__lock_file}: {str(e)}"
            )
            return False
        if mtime < time.time() - self.__stale_timeout:
            return True
        return False

    def __remove_lock_file(self):
        try:
            os.remove(self.__lock_file)
            logger.debug(f"Lock file '{self.__lock_file}' removed")
        except OSError:
            pass

    def acquire(self, detect_stale=None, timeout=None):
        with self.__lock:
            if timeout is None:
                timeout = self.__timeout
            if detect_stale is None:
                detect_stale = self.__detect_stale
            wait_time = 0
            while True:
                if detect_stale:
                    if self.__is_stale():
                        logger.debug(f"Removing stale lock file '{self.__lock_file}'")
                        self.__remove_lock_file()
                        time.sleep(self.__stale_race_delay)
                try:
                    fd = os.open(
                        self.__lock_file,
                        mode=0o644,
                        flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    )
                    os.write(fd, str(os.getpid()).encode())
                    os.close(fd)
                    atexit.register(self.__remove_lock_file)
                    logger.debug(f"{self} acquired")
                    self.__acquired = True
                    self.__touch()
                    break
                except FileExistsError:
                    pass

                if timeout is not None and wait_time >= timeout:
                    logger.debug(f"Unable to acquire {self}")
                    raise Timeout(f"Unable to acquire {self}") from None
                else:
                    wait_time += self.__retry_period
                    time.sleep(self.__retry_period)

    def release(self):
        with self.__lock:
            if not self.__acquired:
                logger.debug(
                    f"Ignoring attempt at releasing {self} which we do not own"
                )
                return
            self.__acquired = False
            if self.__timer is not None:
                self.__timer.cancel()
            self.__remove_lock_file()
            atexit.unregister(self.__remove_lock_file)
            logger.debug(f"{self} released")

    def locked(self):
        with self.__lock:
            return self.__acquired

    def getpid(self):
        with self.__lock:
            if self.__acquired:
                return os.getpid()
            if self.__is_stale():
                return None
            try:
                with open(self.__lock_file) as f:
                    return int(f.read())
            except Exception:
                return None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def __str__(self):
        return f"FileLock('{self.__lock_file}')"

    __repr__ = __str__
