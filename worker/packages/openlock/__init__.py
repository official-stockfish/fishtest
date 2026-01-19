import sys

from .openlock import (  # noqa: F401
    FileLock,
    InvalidLockFile,
    InvalidOption,
    InvalidRelease,
    OpenLockException,
    Timeout,
    __version__,
    get_defaults,
    logger,
    set_defaults,
)

if sys.version_info >= (3, 11):
    from .openlock import Defaults  # noqa: F401
