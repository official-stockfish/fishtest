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

        # The internal state of the object is protected by this lock.
        # The lock can be acquired externally by using self (or equivalently
        # self.lock) as a context manager. In that case the object
        # is inaccessible from other threads until the context
        # manager exits.
        self.__lock = threading.RLock()

        # When the lock is acquired via the context manager,
        # entries do not expire.
        self.__relax_constraints = False

    def __enter__(self):
        self.acquire()

    def __exit__(self, *args):
        self.release()
        return False

    def acquire(self):
        self.__lock.acquire()
        if self.__relax_constraints:
            self.__lock.release()
            raise RuntimeError("Attempt to reacquire a lock")
        self.__purge()
        self.__relax_constraints = True

    def release(self):
        # This method should only be called when we hold the lock.
        # Otherwise it produces a race condition.
        if not self.__relax_constraints:
            raise RuntimeError("Attempt to release an unlocked LRUCache")
        self.__relax_constraints = False
        self.__purge()
        self.__lock.release()

    def __getitem__(self, key):
        with self.__lock:
            current_time = time.monotonic()
            v, atime = self.__dict[key]
            if self.__expiration is not None and not self.__relax_constraints:
                if atime < current_time - self.__expiration:
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
            if self.__expiration is not None and not self.__relax_constraints:
                current_time = time.monotonic()
                v, atime = self.__dict[key]
                if atime < current_time - self.__expiration:
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
        # Helper method. Not synchronized!
        if not self.__relax_constraints:
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
        with self.__lock:
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
        with self.__lock:
            return self.__expiration

    @expiration.setter
    def expiration(self, val):
        with self.__lock:
            self.__expiration = val
            self.__purge()

    @property
    def refresh_on_access(self):
        with self.__lock:
            return self.__refresh_on_access

    @refresh_on_access.setter
    def refresh_on_access(self, val):
        with self.__lock:
            self.__refresh_on_access = val

    # The "lock" property is an alias for self
    # so it is purely cosmetic. However writing:
    #
    # with lru_cache.lock:
    #   ...
    #
    # is clearer than
    #
    # with lru_cache:
    #   ...
    @property
    def lock(self):
        return self
