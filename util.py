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


class LoopProfiler:
    """Worst-case duration per named main-loop section, for finding what
    stalls the loop long enough to overflow the UART RX buffer.

    t = prof.start(); ...work...; prof.stop("name", t) -- keeps the max
    microseconds seen per name since the last report(), which returns a
    one-line summary (ms) and resets.
    """

    def __init__(self):
        self._max = {}

    def start(self):
        return time.ticks_us()

    def stop(self, name, t0):
        d = time.ticks_diff(time.ticks_us(), t0)
        if d > self._max.get(name, 0):
            self._max[name] = d

    def note(self, name, us):
        # For durations measured elsewhere (e.g. os.sync inside sdlog).
        if us > self._max.get(name, 0):
            self._max[name] = us

    def report(self):
        s = " ".join("%s=%.1f" % (k, v / 1000) for k, v in sorted(self._max.items()))
        self._max = {}
        return s


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
