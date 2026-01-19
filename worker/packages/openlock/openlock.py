from __future__ import annotations

import atexit
import copy
import logging
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    from typing import TypedDict, Unpack

__version__ = "1.2.1"

logger = logging.getLogger(__name__)

IS_WINDOWS = "windows" in platform.system().lower()


def _pid_valid_windows(pid: int, name: str) -> bool:
    cmdlet = (
        "(Get-CimInstance Win32_Process " "-Filter 'ProcessId = {}').CommandLine"
    ).format(pid)
    cmd = [
        "powershell",
        cmdlet,
    ]
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )
    out = p.stdout.lower()
    if name.lower() in out and "python" in out:
        return True
    return False


def _pid_valid_posix(pid: int, name: str) -> bool:
    # for busybox these options are undocumented...
    cmd = ["ps", "-f", str(pid)]

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    ) as p:
        assert p.stdout is not None
        read_header = True
        for line in iter(p.stdout.readline, ""):
            line = line.lower()
            line_ = line.split()
            if len(line_) == 0:
                continue
            if "pid" in line_ and read_header:
                # header
                index = line_.index("pid")
                read_header = False
                continue
            try:
                pid_ = int(line_[index])
            except ValueError:
                continue
            if name.lower() in line and "python" in line and pid == pid_:
                return True
    return False


def _pid_valid(pid: int, name: str) -> bool:
    if IS_WINDOWS:
        return _pid_valid_windows(pid, name)
    else:
        return _pid_valid_posix(pid, name)


class OpenLockException(Exception):
    """
    Base exception raised by the openlock library.
    """

    pass


class Timeout(OpenLockException):
    """
    Raised when the waiting time for acquiring a
    :py:class:`openlock.FileLock` has expired.
    """

    pass


class InvalidRelease(OpenLockException):
    """
    Raised when :py:meth:`openlock.FileLock.release` is called
    on a lock we do not own.
    """

    pass


class InvalidLockFile(OpenLockException):
    """
    Raised when openlock is unable to create a
    valid lock file in :py:meth:`openlock.FileLock.acquire`.
    """

    pass


class InvalidOption(OpenLockException):
    """
    Raised when :py:func:`openlock.set_defaults` is used to set
    a non-existing option.
    """

    pass


if sys.version_info >= (3, 11):

    class _LockState(TypedDict, total=False):
        state: str
        reason: str
        pid: int
        name: str

    class Defaults(TypedDict, total=False):
        """
        Default options.
        """

        race_delay: float
        """
        delay before we check that we still have the lock file
        """
        tries: int
        """
        number of attempts to create a valid lock file
        """
        retry_period: float
        """
        delay before reattempting to acquire a lock
        """


_defaults: Defaults = {
    "race_delay": 0.2,
    "tries": 2,
    "retry_period": 0.3,
}


def get_defaults() -> Defaults:
    """
    Get defaults.
    """
    return copy.copy(_defaults)


def set_defaults(**kw: Unpack[Defaults]) -> None:
    """
    Set defaults.

    :param kw: default parameters

    :raises InvalidOption: raised when trying to set a non-existing
      option
    """
    dk = _defaults.keys()
    for k in kw.keys():
        if k not in dk:
            raise InvalidOption(f"Invalid option: '{k}'")
    _defaults.update(kw)


class FileLock:
    """
    The lock constructor. An :py:class:`openlock.FileLock` object
    supports the context manager protocol.
    """

    lock_file: Path
    """
    The `Path` object representing the lock file.
    """
    timeout: float | None
    """
    The value of the timeout parameter.
    """
    __lock: threading.Lock
    __acquired: bool
    __retry_period: float
    __race_delay: float
    __tries: int

    def __init__(
        self,
        lock_file: str = "openlock.lock",
        timeout: float | None = None,
    ) -> None:
        """
        :param lock_file: the underlying file used for locking;
          the calling process should have read/write access
        :param timeout: the default for the corresponding argument of
          :py:meth:`openlock.acquire`
        """
        self.lock_file = Path(lock_file)
        self.timeout = timeout
        self.__lock = threading.Lock()
        self.__acquired = False
        self.__retry_period = _defaults["retry_period"]
        self.__race_delay = _defaults["race_delay"]
        self.__tries = _defaults["tries"]
        logger.debug(f"{self} created")

    def __lock_state(self, verify_pid_valid: bool = True) -> _LockState:
        try:
            with open(self.lock_file) as f:
                s = f.readlines()
        except FileNotFoundError:
            return {
                "state": "unlocked",
                "reason": "file not found",
            }
        except Exception as e:
            logger.exception(f"Error accessing '{self.lock_file}': {str(e)}")
            raise
        try:
            pid = int(s[0])
            name = s[1].strip()
        except (ValueError, IndexError):
            return {
                "state": "unlocked",
                "reason": "invalid lock file",
            }

        if not verify_pid_valid:
            return {
                "state": "locked",
                "pid": pid,
                "name": name,
            }
        else:
            if not _pid_valid(pid, name):
                retry = self.__lock_state(verify_pid_valid=False)
                if retry["state"] == "locked" and (
                    retry["pid"] != pid or retry["name"] != name
                ):
                    logger.debug(
                        f"Lock file '{self.lock_file}' has changed "
                        f"from {{'pid': {pid}, 'name': '{name}'}} to {{'pid': "
                        f"{retry['pid']}, 'name': {repr(retry['name'])}}} "
                    )
                    return retry
                else:
                    return {
                        "state": "unlocked",
                        "reason": "pid not valid",
                        "pid": pid,
                        "name": name,
                    }

        return {"state": "locked", "pid": pid, "name": name}

    def __remove_lock_file(self) -> None:
        try:
            os.remove(self.lock_file)
            logger.debug(f"Lock file '{self.lock_file}' removed")
        except OSError:
            pass

    def __create_lock_file(self, pid: int, name: str) -> bool:
        if self.lock_file.exists():
            return False

        temp_file = tempfile.NamedTemporaryFile(
            dir=os.path.dirname(self.lock_file), delete=False
        )
        temp_file.write(f"{pid}\n{name}\n".encode())
        temp_file.close()

        locked = True
        # try linking, which is atomic, and will fail if the file exists
        try:
            os.link(temp_file.name, self.lock_file)
            logger.debug(f"Lock file '{self.lock_file}' created")
        except FileExistsError:
            locked = False
        except OSError as e:
            logger.error(f"Error creating '{self.lock_file}': {str(e)}")
            locked = False

        # Remove the temporary file
        os.remove(temp_file.name)

        return locked

    def __write_lock_file(self, pid: int, name: str) -> None:
        temp_file = tempfile.NamedTemporaryFile(
            dir=os.path.dirname(self.lock_file), delete=False
        )
        temp_file.write(f"{pid}\n{name}\n".encode())
        temp_file.close()
        os.replace(temp_file.name, self.lock_file)

    def __acquire_once(self) -> None:
        pid, name = os.getpid(), sys.argv[0]
        name_ = name.split()
        if len(name_) >= 1:
            name = Path(name_[0]).stem

        if self.__create_lock_file(pid, name):
            logger.debug(f"{self} acquired")
            self.__acquired = True
            atexit.register(self.__remove_lock_file)
            return

        lock_state = self.__lock_state()
        logger.debug(f"{self}: {lock_state}")
        for _ in range(0, self.__tries):
            if lock_state["state"] == "locked":
                return
            t = time.time()
            self.__write_lock_file(pid, name)
            tt = time.time()
            logger.debug(
                f"Lock file '{self.lock_file}' with contents {{'pid': {pid}, "
                f"'name': '{name}'}} written in {tt-t:#.2g} seconds"
            )
            if tt - t >= (2 / 3) * self.__race_delay:
                message = (
                    "Slow system detected!! Consider increasing the "
                    "'race_delay' parameter "
                    f"(current value: {self.__race_delay:#.2g}, used: {tt-t:#.2g})."
                )
                warnings.warn(message)
            time.sleep(self.__race_delay)
            lock_state = self.__lock_state(verify_pid_valid=False)
            logger.debug(f"{self}: {lock_state}")
            if lock_state["state"] == "locked":
                if lock_state["pid"] == os.getpid():
                    logger.debug(f"{self} acquired")
                    self.__acquired = True
                    atexit.register(self.__remove_lock_file)
                return
        raise InvalidLockFile("Unable to obtain a valid lock file")

    def acquire(self, timeout: float | None = None) -> None:
        """
        Attempts to acquires the lock.

        :param timeout: specifies the maximum waiting time in seconds
          before a :py:exc:`Timeout` exception is raised

        :raises Timeout: raised when the waiting time for acquiring
          the lock has expired
        :raises InvalidLockFile: raised when openlock is unable to create a
          valid lock file
        """
        if timeout is None:
            timeout = self.timeout
        start_time = time.time()
        with self.__lock:
            while True:
                if not self.__acquired:
                    self.__acquire_once()
                    if self.__acquired:
                        break
                now = time.time()
                if timeout is not None and now - start_time >= timeout:
                    raise Timeout(f"Unable to acquire {self}")
                time.sleep(self.__retry_period)

    def release(self) -> None:
        """
        Releases the lock.

        :raises InvalidRelease: raised when we don't own the lock
        """
        with self.__lock:
            if not self.__acquired:
                raise InvalidRelease(f"Attempt at releasing {self} which we do not own")
            self.__acquired = False
            self.__remove_lock_file()
            atexit.unregister(self.__remove_lock_file)
            logger.debug(f"{self} released")

    def locked(self) -> bool:
        """
        True if we hold the lock.
        """
        with self.__lock:
            if self.__acquired:
                return True
            lock_state = self.__lock_state()
            return lock_state["state"] == "locked"

    def getpid(self) -> int | None:
        """
        The PID of the process that holds the lock, if any. Otherwise returns `None`.
        """
        with self.__lock:
            if self.__acquired:
                return os.getpid()
            lock_state = self.__lock_state()
            if lock_state["state"] == "locked":
                return lock_state["pid"]
            else:
                return None

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.release()

    def __str__(self) -> str:
        return f"FileLock('{self.lock_file}')"

    __repr__ = __str__
