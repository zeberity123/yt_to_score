"""Pause between provider requests, retaining the running pipeline in memory."""
from contextlib import contextmanager
import threading
import time


class RequestGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.requested = False
        self.active = 0
        self.started = None
        self.elapsed = 0.

    def pause(self):
        with self.condition:
            self.requested = True
            if not self.active and self.started is None:
                self.started = time.monotonic()

    def resume(self):
        with self.condition:
            if self.started is not None:
                self.elapsed += time.monotonic()-self.started
                self.started = None
            self.requested = False
            self.condition.notify_all()

    def state(self):
        with self.condition:
            return dict(requested=self.requested, active=self.active,
                        seconds=self.elapsed+(time.monotonic()-self.started if self.started is not None else 0))

    def wait(self, cancel):
        from .providers import check_cancel
        with self.condition:
            while self.requested:
                check_cancel(cancel)
                self.condition.wait(.1)
            check_cancel(cancel)

    @contextmanager
    def request(self, cancel):
        from .providers import check_cancel
        with self.condition:
            while self.requested:
                check_cancel(cancel)
                self.condition.wait(.1)
            check_cancel(cancel)
            self.active += 1
        try:
            yield
        finally:
            with self.condition:
                self.active -= 1
                if self.requested and not self.active and self.started is None:
                    self.started = time.monotonic()
                self.condition.notify_all()
