# pico_log.py -- log() replaces print() everywhere: always writes to the
# REPL, and once attach() has been called with a sdlog.TextLogWriter (SD
# card mounted, session file open), also appends the same line to it,
# timestamped with GPS-derived UTC date/time once available (see
# attach_clock()) or elapsed boot time before that.

import time

_writer = None
_clock = None
_boot_ms = time.ticks_ms()


def attach(writer):
    global _writer
    _writer = writer


def attach_clock(clock):
    """clock: a util.WallClock. Once it's synced (GPS-derived UNIX time seen
    in a SYSTEM_TIME message), log lines get a real UTC date/time instead of
    an elapsed-boot-seconds counter."""
    global _clock
    _clock = clock


def _timestamp():
    if _clock is not None and _clock.synced:
        # This board's time.gmtime() takes standard Unix-epoch seconds
        # directly (confirmed empirically -- some other embedded MicroPython
        # ports instead use a 2000-01-01 epoch and would need an offset here).
        unix_s = _clock.now() // 1_000_000
        y, mo, d, h, mi, s, *_rest = time.gmtime(unix_s)
        return "%04d-%02d-%02d %02d:%02d:%02dZ" % (y, mo, d, h, mi, s)
    return "+%9.3f" % (time.ticks_diff(time.ticks_ms(), _boot_ms) / 1000)


def log(msg):
    print(msg)
    if _writer is not None:
        try:
            _writer.write("[%s] %s" % (_timestamp(), msg))
        except OSError:
            pass
