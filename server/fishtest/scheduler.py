import copy
import threading
from datetime import UTC, datetime, timedelta
from random import uniform

"""
The following scheduling code should be thread safe.

- First and foremost, all tasks are executed in a single main thread.
So they are atomic. In particular, during its lifetime, a task will be
executed exactly once at each scheduling point.

- The main thread maintains a list of scheduled tasks. To safely manipulate
this list outside the main thread we rely on the atomicity of in-place
list operations in Python.

- To signal the main thread that the task list has changed, which should
be acted upon as soon as possible as it might affect the next task to
be executed, we use a threading.Event.

Example

s=Scheduler()
s.add_task(3, task1)
s.add_task(2, task2)

When the second task is scheduled, the scheduler will interrupt the
3s wait for the first task and replace it by a 2s wait for the second task.
"""


def _execute(worker, *args, _background=False, **kwargs):
    if not _background:
        try:
            worker(*args, **kwargs)
        except Exception as e:
            print(f"{e.__class__.__name__} in {worker.__name__}: {str(e)}", flush=True)
    else:
        kwargs["_background"] = False
        args = (worker,) + args
        t = threading.Thread(target=_execute, args=args, kwargs=kwargs, daemon=True)
        t.start()


class Task:
    """This is an opaque class representing a task. Instances should be created via
    Scheduler.create_task(). Some public methods are documented below.
    """

    def __init__(
        self,
        period,
        worker,
        initial_delay=None,
        min_delay=0.0,
        one_shot=False,
        jitter=0.0,
        scheduler=None,
        background=False,
        args=(),
        kwargs={},
    ):
        self.period = timedelta(seconds=period)
        self.worker = worker
        if initial_delay is None:
            initial_delay = self.period
        else:
            initial_delay = timedelta(seconds=initial_delay)
        self.min_delay = timedelta(seconds=min_delay)
        self.__rel_jitter = jitter * self.period
        self.__next_schedule = (
            datetime.now(UTC)
            + initial_delay
            + uniform(-self.__rel_jitter, self.__rel_jitter)
        )
        self.one_shot = one_shot
        self.__expired = False
        self.__scheduler = scheduler
        self.__lock = threading.Lock()
        self.__background = background
        self.args = args
        self.kwargs = kwargs

    def _do_work(self):
        if not self.__expired:
            _execute(
                self.worker, *self.args, _background=self.__background, **self.kwargs
            )
            if not self.one_shot:
                jitter = uniform(-self.__rel_jitter, self.__rel_jitter)
                with self.__lock:
                    self.__next_schedule = (
                        max(
                            self.__next_schedule + self.period,
                            datetime.now(UTC) + self.min_delay,
                        )
                        + jitter
                    )
            else:
                self.__expired = True

    def _next_schedule(self):
        return self.__next_schedule

    def schedule_now(self):
        """Schedule the task now. Note that this happens asynchronously."""
        if not self.__expired:
            with self.__lock:
                self.__next_schedule = datetime.now(UTC)
            self.__scheduler._refresh()

    def expired(self):
        """Indicates if the task has stopped

        :rtype: bool
        """
        return self.__expired

    def stop(self):
        """This stops the task"""
        if self.__expired:
            return
        self.__expired = True
        self.__scheduler._refresh()


class Scheduler:
    """This creates a scheduler

    :param jitter: the default value for the task jitter (see below), defaults to 0.0
    :type jitter: float, optional
    """

    def __init__(self, jitter=0.0):
        """Constructor method"""
        self.jitter = jitter
        self.__tasks = []
        self.__event = threading.Event()
        self.__thread_stopped = False
        self.__worker_thread = threading.Thread(target=self.__next_schedule)
        self.__worker_thread.start()

    def create_task(
        self,
        period,
        worker,
        initial_delay=None,
        min_delay=0.0,
        one_shot=False,
        jitter=None,
        background=False,
        args=(),
        kwargs={},
    ):
        """This schedules a new task.

        :param period: The period after which the task will repeat
        :type period: float

        :param worker: A callable that executes the task
        :type worker: Callable

        :param initial_delay: The delay before the first execution of the task, defaults to period
        :type initial_delay: float, optional

        :param min_delay: The minimum delay before the same task is repeated, defaults to 0.0
        :type min_delay: float, optional

        :param one_shot: If true, execute the task only once, defaults to False
        :type one_shot: bool, optional

        :param jitter: Add random element of [-jitter*period, jitter*period] to delays, defaults to self.jitter
        :type jitter: float, optional

        :param args: Arguments passed to the worker, defaults to ()
        :type args: tuple, optional

        :param kwargs: Keyword arguments passed to the worker, defaults to {}
        :type kwargs: dict, optional

        :rtype: Task
        """
        if jitter is None:
            jitter = self.jitter
        task = Task(
            period,
            worker,
            initial_delay=initial_delay,
            min_delay=min_delay,
            one_shot=one_shot,
            jitter=jitter,
            scheduler=self,
            background=background,
            args=args,
            kwargs=kwargs,
        )
        self.__tasks.append(task)
        self._refresh()
        return task

    def join(self):
        """Join worker thread - if possible"""
        if threading.current_thread() != self.__worker_thread:
            self.__worker_thread.join()

    def stop(self):
        """This stops the scheduler"""
        self.__thread_stopped = True
        self._refresh()
        self.join()

    def _refresh(self):
        self.__event.set()

    def _del_task(self, task):
        self.__del_task(task)
        self._refresh()

    def __del_task(self, task):
        try:
            self.__tasks.remove(task)
        except Exception:
            pass

    def __next_schedule(self):
        while not self.__thread_stopped:
            next_schedule = None
            for task in copy.copy(self.__tasks):
                if task.expired():
                    self.__del_task(task)
                else:
                    if next_schedule is None or task._next_schedule() < next_schedule:
                        next_task = task
                        next_schedule = task._next_schedule()
            if next_schedule is not None:
                delay = (next_schedule - datetime.now(UTC)).total_seconds()
                self.__event.wait(delay)
                if not self.__event.is_set():
                    next_task._do_work()
            else:
                self.__event.wait()
            self.__event.clear()
