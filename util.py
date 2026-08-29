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


class WallClock:
    """Microsecond clock for .tlog frame timestamps.

    Starts out ticking the same boot-relative microsecond counter as
    MonotonicUs -- there's nothing better to stamp frames with before the FC
    has a real time source. Call sync() with a SYSTEM_TIME.time_unix_usec
    value (nonzero only once the FC has derived wall time from the GPS) to
    latch an epoch offset; from that point on, now() returns true UNIX
    epoch microseconds instead of time-since-boot. Frames already written
    keep whatever timestamp they got at write time -- only sync() changes.
    Safe to call sync() again on later SYSTEM_TIME messages to correct for
    drift between the Pico's clock and the FC's.
    """

    def __init__(self):
        self._mono = MonotonicUs()
        self._offset_us = 0
        self.synced = False

    def now(self):
        return self._mono.now() + self._offset_us

    def sync(self, unix_usec):
        self._offset_us = unix_usec - self._mono.now()
        self.synced = True
