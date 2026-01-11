import functools
import threading
import time
from collections import OrderedDict
from collections.abc import MutableMapping


class LRUCache(MutableMapping):
    __slots__ = (
        "__size",
        "__expiration",
        "__refresh",
        "__data",
        "__lock",
        "__lock_depth",
    )

    def __init__(self, maxsize=None, expiration=None, refresh=True):
        if maxsize is not None and maxsize < 0:
            raise ValueError("maxsize must be >= 0 or None (default)")
        self.__size = maxsize
        self.__expiration = expiration
        self.__refresh = refresh
        self.__data = OrderedDict()

        # The internal state of the object is protected by this lock.
        # The lock can be acquired externally by using self (or equivalently
        # self.lock) as a context manager. In that case the object
        # is inaccessible from other threads until the context
        # manager exits.
        # Note, to preserve atomicity, entries do not expire
        # when the lock is acquired through the context manager.
        self.__lock = threading.RLock()
        self.__lock_depth = 0

    def __enter__(self):
        self.acquire()

    def __exit__(self, *args):
        self.release()
        return False

    def acquire(self, blocking=True, timeout=-1):
        acquired = self.__lock.acquire(blocking=blocking, timeout=timeout)
        if not acquired:
            return False
        self.__purge()
        self.__lock_depth += 1
        return True

    def release(self):
        acquired = self.__lock.acquire(blocking=False)
        if not acquired:
            raise RuntimeError("Attempt to release a lock we do not own")
        try:
            if self.__lock_depth == 0:
                raise RuntimeError("Attempt to release an unlocked lock")
        finally:
            self.__lock.release()
        self.__lock_depth -= 1
        self.__purge()
        self.__lock.release()

    def __getitem__(self, key):
        with self.__lock:
            current_time = time.monotonic()
            v, atime = self.__data[key]
            if self.__expiration is not None and self.__lock_depth == 0:
                if atime < current_time - self.__expiration:
                    del self.__data[key]
                    raise KeyError(key)
            if self.__refresh:
                self.__data.move_to_end(key)
                self.__data[key] = (v, current_time)
            return v

    def __setitem__(self, key, value):
        with self.__lock:
            self.__data[key] = (value, time.monotonic())
            self.__data.move_to_end(key)
            self.__purge()

    def __delitem__(self, key):
        with self.__lock:
            del self.__data[key]

    def __len__(self):
        with self.__lock:
            self.__purge()
            return len(self.__data)

    def get(self, *args, refresh=True, **kw):
        with self.__lock:
            saved_refresh = self.__refresh
            self.__refresh = refresh
            try:
                return super().get(*args, **kw)
            finally:
                self.__refresh = saved_refresh

    # the default implementation is very inefficient
    def clear(self):
        with self.__lock:
            self.__data.clear()

    # the default implementation of __contains__ calls
    # self.__getitem__ and hence it modifies the access time,
    # which is semantically incorrect for a pure containment
    # check
    def __contains__(self, key):
        with self.__lock:
            if key not in self.__data:
                return False
            if self.__expiration is not None and self.__lock_depth == 0:
                current_time = time.monotonic()
                v, atime = self.__data[key]
                if atime < current_time - self.__expiration:
                    del self.__data[key]
                    return False
            return True

    def __iter__(self):
        with self.__lock:
            self.__purge()
            return iter(list(self.__data))

    # we cannot use the default implementation of values() and items()
    # since these modify self.__data during iteration (via the
    # calls to self.__getitem__)

    def values(self):
        with self.__lock:
            self.__purge()
            return iter([v[0] for v in self.__data.values()])

    def items(self):
        with self.__lock:
            self.__purge()
            return iter([(k, v[0]) for (k, v) in self.__data.items()])

    def purge(self):
        with self.__lock:
            self.__purge()

    def __purge(self):
        # Helper method. Not synchronized!
        if self.__lock_depth == 0:
            if self.__size is not None:
                while len(self.__data) > self.__size:
                    self.__data.popitem(last=False)
            if self.__expiration is not None:
                expired = []
                cutoff_time = time.monotonic() - self.__expiration
                for k, v in self.__data.items():
                    atime = v[1]
                    if atime >= cutoff_time:
                        break
                    expired.append(k)
                for k in expired:
                    del self.__data[k]

    @property
    def maxsize(self):
        with self.__lock:
            return self.__size

    @maxsize.setter
    def maxsize(self, val):
        if val is not None and val < 0:
            raise ValueError("maxsize must be >= 0 or None (default)")
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
    def refresh(self):
        with self.__lock:
            return self.__refresh

    @refresh.setter
    def refresh(self, val):
        with self.__lock:
            self.__refresh = val

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


# This mimics to some extent the decorator "functools.lru_cache". It has however
# the extra options "expiration" and "refresh". Furthermore it is possible
# to use a previously defined LRUCache object as cache. The "key" parameter
# allows customizing how cache keys are constructed from (f, args, kw), and the
# "filter" parameter controls, based on (f, args, kw, val), whether a computed
# result should be stored in the cache.
class lru_cache:
    def __init__(
        self,
        maxsize=None,
        expiration=None,
        refresh=None,
        cache=None,
        key=lambda f, args, kw: (f, tuple(kw.items())) + args,
        filter=lambda f, args, kw, val: True,
    ):
        if cache is not None:
            if any((x is not None for x in (maxsize, expiration, refresh))):
                raise ValueError(
                    "You cannot specify maxsize, expiration or "
                    "refresh for a pre-constructed LRUCache object",
                )
            self.__cache = cache
        else:
            if refresh is None:
                refresh = True
            self.__cache = LRUCache(
                maxsize=maxsize, expiration=expiration, refresh=refresh
            )
        self.__key = key
        self.__filter = filter

    def __call__(self, f):
        @functools.wraps(f)
        def wrapper(*args, **kw):
            key = self.__key(f, args, kw)
            try:
                return self.__cache[key]
            except KeyError:
                pass
            ret = f(*args, **kw)
            with self.__cache.lock:
                try:
                    return self.__cache[key]
                except KeyError:
                    pass
                if self.__filter(f, args, kw, ret):
                    self.__cache[key] = ret
                return ret

        wrapper.lock = self.__cache.lock
        wrapper.cache = self.__cache
        wrapper.key = self.__key
        wrapper.filter = self.__filter

        # for compatibility with the built-in functools.lru_cache
        wrapper.cache_clear = self.__cache.clear
        return wrapper
