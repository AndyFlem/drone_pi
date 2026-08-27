# util.py -- small helpers shared across the logger modules.

import time


class MonotonicUs:
    """Ever-growing microsecond counter, safe across time.ticks_us() wraparound.

    Must be polled more often than the port's ticks_us() wrap period (usually
    tens of minutes) -- fine here since it's read every main-loop iteration.
    """

    def __init__(self):
        self._last = time.ticks_us()
        self._total = 0

    def now(self):
        t = time.ticks_us()
        self._total += time.ticks_diff(t, self._last)
        self._last = t
        return self._total
