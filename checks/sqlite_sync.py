"""Force a bad interleaving of concurrent database access without relying on timing.

While armed, every thread stops after each SELECT until the other thread has reached the
same point. Two threads that read before they write therefore always see the same data.
Code that serialises correctly (BEGIN IMMEDIATE, an atomic UPDATE, a lock) makes one thread
wait for the other instead. The barrier then times out and the threads run one after the
other, so the outcome only depends on the code under test.
"""
import sqlite3
import threading
from contextlib import contextmanager

_real_connect = sqlite3.connect


class _Controller:
    def __init__(self):
        self.barrier = None

    def pause(self, sql):
        barrier = self.barrier
        if barrier is None or not str(sql).lstrip().upper().startswith("SELECT"):
            return
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass


_controller = _Controller()


class _Cursor(sqlite3.Cursor):
    def execute(self, sql, *args):
        result = super().execute(sql, *args)
        _controller.pause(sql)
        return result


class _Connection(sqlite3.Connection):
    def execute(self, sql, *args):
        result = super().execute(sql, *args)
        _controller.pause(sql)
        return result

    def cursor(self, factory=_Cursor):
        return super().cursor(factory)


def _connect(*args, **kwargs):
    kwargs["factory"] = _Connection
    return _real_connect(*args, **kwargs)


@contextmanager
def instrumented():
    """Connections opened inside this block can be paused."""
    sqlite3.connect = _connect
    try:
        yield
    finally:
        sqlite3.connect = _real_connect
        _controller.barrier = None


def arm(parties=2, timeout=2.0):
    _controller.barrier = threading.Barrier(parties, timeout=timeout)


def disarm():
    barrier = _controller.barrier
    _controller.barrier = None
    if barrier is not None:
        barrier.abort()
