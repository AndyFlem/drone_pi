# sdlog.py -- mounts the microSD card and writes MAVLink frames as a
# QGroundControl-compatible .tlog: each record is an 8-byte big-endian
# microsecond timestamp followed by the raw MAVLink2 frame bytes. Also
# provides TextLogWriter, a plaintext companion log (logNNNN.txt) on the
# same card for the REPL debug/flight-event messages -- see pico_log.py.

import os
from machine import SPI, Pin

import sdcard  # mip.install("sdcard"), see main.py header


class TlogWriter:
    def __init__(self, spi_id, sck, mosi, miso, cs, mount_point="/sd", sync_interval_ms=1500):
        import time

        spi = SPI(spi_id, baudrate=1_000_000, sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self.sd = sdcard.SDCard(spi, Pin(cs))
        self.mount_point = mount_point
        os.mount(self.sd, mount_point)

        self._time = time
        self.session_id = self._next_session_id()
        self._path = "%s/log%04d.tlog" % (mount_point, self.session_id)
        self._file = open(self._path, "wb")
        self._sync_interval_ms = sync_interval_ms
        self._last_sync = time.ticks_ms()

    def _next_session_id(self):
        existing = {f for f in os.listdir(self.mount_point) if f.startswith("log") and f.endswith(".tlog")}
        n = 1
        while "log%04d.tlog" % n in existing:
            n += 1
        return n

    @property
    def path(self):
        return self._path

    def write_frame(self, frame, timestamp_us):
        self._file.write(timestamp_us.to_bytes(8, "big"))
        self._file.write(frame)

        now = self._time.ticks_ms()
        if self._time.ticks_diff(now, self._last_sync) >= self._sync_interval_ms:
            self._file.flush()
            os.sync()
            self._last_sync = now

    def close(self):
        self._file.flush()
        self._file.close()


class TextLogWriter:
    """Plaintext debug/flight-event log alongside the .tlog, sharing the SD
    mount TlogWriter already established -- must be constructed after it."""

    def __init__(self, mount_point, session_id, sync_interval_ms=1500):
        import time

        self._time = time
        self._path = "%s/log%04d.txt" % (mount_point, session_id)
        self._file = open(self._path, "a")
        self._sync_interval_ms = sync_interval_ms
        self._last_sync = time.ticks_ms()

    @property
    def path(self):
        return self._path

    def write(self, line):
        self._file.write(line + "\n")

        now = self._time.ticks_ms()
        if self._time.ticks_diff(now, self._last_sync) >= self._sync_interval_ms:
            self._file.flush()
            os.sync()
            self._last_sync = now

    def close(self):
        self._file.flush()
        self._file.close()
