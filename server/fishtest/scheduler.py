import copy
import threading
from datetime import datetime, timedelta, timezone
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
            datetime.now(timezone.utc)
            + initial_delay
            + uniform(-self.__rel_jitter, self.__rel_jitter)
        )
        self.one_shot = one_shot
        self.__expired = False
        self.__scheduler = scheduler
        self.__lock = threading.Lock()
        self.args = args
        self.kwargs = kwargs

    def _do_work(self):
        if not self.__expired:
            try:
                self.worker(*self.args, *self.kwargs)
            except Exception as e:
                print(f"{type(e).__name__} while executing task: {str(e)}", flush=True)
            if not self.one_shot:
                jitter = uniform(-self.__rel_jitter, self.__rel_jitter)
                with self.__lock:
                    self.__next_schedule = (
                        max(
                            self.__next_schedule + self.period,
                            datetime.now(timezone.utc) + self.min_delay,
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
                self.__next_schedule = datetime.now(timezone.utc)
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
            args=args,
            kwargs=kwargs,
        )
        self.__tasks.append(task)
        self._refresh()
        return task

    def stop(self):
        """This stops the scheduler"""
        self.__thread_stopped = True
        self._refresh()

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
                delay = (next_schedule - datetime.now(timezone.utc)).total_seconds()
                self.__event.wait(delay)
                if not self.__event.is_set():
                    next_task._do_work()
            else:
                self.__event.wait()
            self.__event.clear()
