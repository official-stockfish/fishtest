def synchronized(lock):
    """ Synchronization decorator """
    def wrap(f):
        def threadSafeFunction(*args, **kw):
            with lock:
                return f(*args, **kw)
        return threadSafeFunction
    return wrap
