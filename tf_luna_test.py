# tfluna_test.py -- bench test for a Benewake TF-Luna in UART mode.
#
# Wiring (TF-Luna -> Pico):
#   pin 1 VCC  -> VSYS / VBUS (5 V)
#   pin 2 RXD  -> GP12 (UART0 TX)
#   pin 3 TXD  -> GP13 (UART0 RX)
#   pin 4 GND  -> GND
#   pin 5      -> leave floating (UART mode)
#
# Usage from the REPL (stop main.py first with Ctrl-C -- it also uses UART0):
#   import tfluna_test
#   tfluna_test.run()                 # print readings at 115200
#   tfluna_test.run(seconds=10)       # stop after 10 s
#   tfluna_test.scan()                # try common baud rates
#   tfluna_test.factory_reset()       # restore defaults, then power-cycle

from machine import UART, Pin
import time

UART_ID = 0
TX_PIN = 12
RX_PIN = 13
DEFAULT_BAUD = 115200

_HEADER = b"\x59\x59"
_FRAME_LEN = 9


def _open(baud):
    return UART(UART_ID, baud, tx=Pin(TX_PIN), rx=Pin(RX_PIN))


def _parse(buf):
    """Return (frames, leftover_buf). Each frame is (dist_cm, strength, temp_c)."""
    frames = []
    while True:
        i = buf.find(_HEADER)
        if i < 0:
            # keep a trailing 0x59 in case it's the first half of a header
            return frames, buf[-1:] if buf[-1:] == b"\x59" else b""
        if len(buf) < i + _FRAME_LEN:
            return frames, buf[i:]
        f = buf[i:i + _FRAME_LEN]
        if sum(f[:8]) & 0xFF == f[8]:
            dist = f[2] | (f[3] << 8)
            strength = f[4] | (f[5] << 8)
            temp_c = (f[6] | (f[7] << 8)) / 8.0 - 256.0
            frames.append((dist, strength, temp_c))
            buf = buf[i + _FRAME_LEN:]
        else:
            buf = buf[i + 1:]  # bad checksum: resync on the next header


def run(baud=DEFAULT_BAUD, seconds=None, every_ms=200):
    """Print distance/strength/temperature until Ctrl-C (or `seconds` elapse)."""
    u = _open(baud)
    buf = b""
    good = 0
    raw_bytes = 0
    start = last_print = time.ticks_ms()
    print("TF-Luna on UART%d GP%d/GP%d @ %d baud -- Ctrl-C to stop" % (UART_ID, TX_PIN, RX_PIN, baud))
    try:
        while seconds is None or time.ticks_diff(time.ticks_ms(), start) < seconds * 1000:
            data = u.read()
            if data:
                raw_bytes += len(data)
                frames, buf = _parse(buf + data)
                good += len(frames)
                now = time.ticks_ms()
                if frames and time.ticks_diff(now, last_print) >= every_ms:
                    dist, strength, temp_c = frames[-1]
                    note = "  (weak/unreliable)" if strength < 100 or strength == 65535 else ""
                    print("dist %4d cm  strength %5d  temp %.1f C%s" % (dist, strength, temp_c, note))
                    last_print = now
            elif time.ticks_diff(time.ticks_ms(), last_print) >= 2000:
                print("... no data (raw bytes so far: %d)" % raw_bytes)
                last_print = time.ticks_ms()
            time.sleep_ms(10)
    except KeyboardInterrupt:
        pass
    print("done: %d good frames, %d raw bytes" % (good, raw_bytes))
    return good


def scan(bauds=(115200, 9600, 57600, 230400, 460800, 921600), seconds=2):
    """Listen at each baud rate and report which one yields valid frames."""
    found = None
    for b in bauds:
        u = _open(b)
        u.read()  # flush
        buf = b""
        good = 0
        raw = 0
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < seconds * 1000:
            data = u.read()
            if data:
                raw += len(data)
                frames, buf = _parse(buf + data)
                good += len(frames)
            time.sleep_ms(10)
        print("%7d baud: %4d valid frames, %5d raw bytes" % (b, good, raw))
        if good and found is None:
            found = b
    if found:
        print("-> sensor is talking at %d baud" % found)
    else:
        print("-> no valid frames at any baud (check TX/RX, pin 5 floating, power)")
    return found


def factory_reset(baud=DEFAULT_BAUD):
    """Send the TF-Luna 'restore factory settings' command. Power-cycle afterwards."""
    u = _open(baud)
    u.write(b"\x5A\x04\x10\x6E")
    time.sleep_ms(100)
    reply = u.read()
    print("reset sent at %d baud, reply: %r" % (baud, reply))
    print("power-cycle the TF-Luna, then run() again")