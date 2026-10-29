# camera.py -- AKASO EK7000 control through its gutted 2.4 GHz remote.
#
# The remote's photo/video tactile switches each short a pad to ground; a
# Pico pin wired to the non-ground leg "presses" the button by pulling it low
# and releases it by floating it again (open-drain, so the remote's own
# pull-up sets the idle level and the Pico never drives it high). Presses are
# non-blocking -- poll() ends them -- and queued one at a time with a gap, so
# the remote never sees both buttons at once.

import time
from machine import Pin

PHOTO = "photo"
VIDEO = "video"


class CameraRemote:
    def __init__(self, photo_pin, video_pin, press_ms=150, gap_ms=250):
        # value=1 -> released (high-Z) from the moment the pin is claimed, so
        # boot never fires a spurious press.
        self._pins = {
            PHOTO: Pin(photo_pin, Pin.OPEN_DRAIN, value=1),
            VIDEO: Pin(video_pin, Pin.OPEN_DRAIN, value=1),
        }
        self.press_ms = press_ms
        self.gap_ms = gap_ms
        self._queue = []
        self._held = None  # button currently pulled low
        self._until = time.ticks_ms()  # end of the current press, or of the gap after it

    def press(self, button):
        if len(self._queue) < 8:
            self._queue.append(button)
        self.poll()

    def poll(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._until) < 0:
            return
        if self._held is not None:
            self._pins[self._held].value(1)
            self._held = None
            self._until = time.ticks_add(now, self.gap_ms)
            return
        if self._queue:
            self._held = self._queue.pop(0)
            self._pins[self._held].value(0)
            self._until = time.ticks_add(now, self.press_ms)


class RcSwitch:
    # Two-position view of one RC channel, with hysteresis so a switch
    # sitting near mid-stick doesn't chatter. update() returns the new
    # position (True = high) on a change, else None. A position only counts
    # once `confirm` RC_CHANNELS readings in a row agree, so one bad packet
    # can't fire the shutter. The first confirmed position only sets the
    # baseline -- booting with a switch already up mustn't count as a flip.
    def __init__(self, channel, high_us=1700, low_us=1300, confirm=3,
                 min_us=800, max_us=2200):
        self.index = channel - 1
        self.high_us = high_us
        self.low_us = low_us
        self.confirm = confirm
        self.min_us = min_us
        self.max_us = max_us
        self.state = None
        self._pending = None
        self._count = 0

    def update(self, channels):
        pwm = channels[self.index]
        # 0 = channel unused, 65535 = invalid (MAVLink RC_CHANNELS spec);
        # anything else outside a real servo pulse range is garbage too.
        # Mid-stick readings are ambiguous. All of these break the run.
        if pwm < self.min_us or pwm > self.max_us:
            new = None
        elif pwm >= self.high_us:
            new = True
        elif pwm <= self.low_us:
            new = False
        else:
            new = None
        if new is None or new == self.state:
            self._pending = None
            self._count = 0
            return None
        if new != self._pending:
            self._pending = new
            self._count = 0
        self._count += 1
        if self._count < self.confirm:
            return None
        self._pending = None
        self._count = 0
        baseline = self.state is None
        self.state = new
        return None if baseline else new
