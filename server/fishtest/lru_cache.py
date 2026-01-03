import threading
import time
from collections import OrderedDict
from collections.abc import MutableMapping


class LRUCache(MutableMapping):
    def __init__(self, size=None, expiration=None, refresh_on_access=True):
        if size is not None and size < 0:
            raise ValueError("size must be >= 0 or None (default)")
        self.__size = size
        self.__expiration = expiration
        self.__refresh_on_access = refresh_on_access
        self.__dict = OrderedDict()

        # All methods that modify the internal state of the
        # object are protected by this lock.
        # In addition the lock is exported as a property
        # so that it can be used to make combinations of
        # the methods atomic, if needed.
        self.__lock = threading.RLock()

    def __getitem__(self, key):
        with self.__lock:
            current_time = time.monotonic()
            v, atime = self.__dict[key]
            if (
                self.__expiration is not None
                and atime < current_time - self.__expiration
            ):
                del self.__dict[key]
                raise KeyError(key)
            if self.__refresh_on_access:
                self.__dict.move_to_end(key)
                self.__dict[key] = (v, current_time)
            return v

    def __setitem__(self, key, value):
        with self.__lock:
            self.__dict[key] = (value, time.monotonic())
            self.__dict.move_to_end(key)
            self.__purge()

    def __delitem__(self, key):
        with self.__lock:
            del self.__dict[key]

    def __len__(self):
        with self.__lock:
            self.__purge()
            return len(self.__dict)

    def get(self, *args, refresh=True, **kw):
        with self.__lock:
            saved_refresh_on_access = self.__refresh_on_access
            self.__refresh_on_access = refresh
            try:
                return super().get(*args, **kw)
            finally:
                self.__refresh_on_access = saved_refresh_on_access

    # the default implementation is very inefficient
    def clear(self):
        with self.__lock:
            self.__dict.clear()

    # the default implementation of __contains__ calls
    # self.__getitem__ and hence it modifies the access time,
    # which is semantically incorrect for a pure containment
    # check
    def __contains__(self, key):
        with self.__lock:
            if key not in self.__dict:
                return False
            current_time = time.monotonic()
            v, atime = self.__dict[key]
            if (
                self.__expiration is not None
                and atime < current_time - self.__expiration
            ):
                del self.__dict[key]
                return False
            return True

    def __iter__(self):
        with self.__lock:
            self.__purge()
            return iter(list(self.__dict))

    # we cannot use the default implementation of values() and items()
    # since these modify self.__dict during iteration (via the
    # calls to self.__getitem__)

    def values(self):
        with self.__lock:
            self.__purge()
            return iter([v[0] for v in self.__dict.values()])

    def items(self):
        with self.__lock:
            self.__purge()
            return iter([(k, v[0]) for (k, v) in self.__dict.items()])

    def purge(self):
        with self.__lock:
            self.__purge()

    def __purge(self):
        if self.__size is not None:
            while len(self.__dict) > self.__size:
                self.__dict.popitem(last=False)
        if self.__expiration is not None:
            expired = []
            cutoff_time = time.monotonic() - self.__expiration
            for k, v in self.__dict.items():
                atime = v[1]
                if atime >= cutoff_time:
                    break
                expired.append(k)
            for k in expired:
                del self.__dict[k]

    @property
    def size(self):
        return self.__size

    @size.setter
    def size(self, val):
        if val is not None and val < 0:
            raise ValueError("size must be >= 0 or None (default)")
        with self.__lock:
            self.__size = val
            self.__purge()

    @property
    def expiration(self):
        return self.__expiration

    @expiration.setter
    def expiration(self, val):
        with self.__lock:
            self.__expiration = val
            self.__purge()

    @property
    def refresh_on_access(self):
        return self.__refresh_on_access

    @refresh_on_access.setter
    def refresh_on_access(self, val):
        with self.__lock:
            self.__refresh_on_access = val

    @property
    def lock(self):
        return self.__lock
