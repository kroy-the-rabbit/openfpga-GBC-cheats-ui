"""Run card I/O off the Tk thread.

Reading the card is slow and unpredictable: a cold walk of /Assets over USB can
take seconds, and doing it inline freezes the window mid-click, which looks
exactly like a crash. It is not, and it recovers, but there is no way for
anyone to tell that by looking at it.

Tk is not thread safe, so a worker only ever produces a value. The result comes
back on the main thread, where the callback is free to touch widgets.
"""
from __future__ import annotations

import queue
import threading


class Worker:
    """One job at a time, newest request wins.

    Clicking through a game list faster than the card can answer would
    otherwise pile up threads all racing to write the same panes. A request
    made while one is in flight replaces any other request waiting behind it,
    so the pane ends up showing whatever was asked for last.
    """

    POLL_MS = 40

    def __init__(self, widget) -> None:
        self.widget = widget
        self.results: queue.Queue = queue.Queue()
        self.busy = False
        self.pending: tuple | None = None
        self.generation = 0

    def submit(self, job, done, label: str = "") -> None:
        """Run job() in a thread, then done(value, error) on the Tk thread."""
        self.pending = (job, done, label)
        if not self.busy:
            self._start()

    def _start(self) -> None:
        if self.pending is None:
            return
        job, done, label = self.pending
        self.pending = None
        self.busy = True
        self.generation += 1
        gen = self.generation

        def body() -> None:
            try:
                self.results.put((gen, done, job(), None))
            except Exception as e:                           # noqa: BLE001
                self.results.put((gen, done, None, e))

        threading.Thread(target=body, daemon=True, name=label or "cheatgui").start()
        self.widget.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        try:
            gen, done, value, err = self.results.get_nowait()
        except queue.Empty:
            self.widget.after(self.POLL_MS, self._poll)
            return

        self.busy = False
        # A result from a superseded request is stale: something newer was
        # asked for while it ran, and that is what the panes should show.
        if gen == self.generation:
            try:
                done(value, err)
            finally:
                self._start()
        else:
            self._start()
