# tfluna_i2c_test.py -- bench test for a Benewake TF-Luna in I2C mode.
#
# Wiring (TF-Luna -> Pico), same wires as the UART test:
#   pin 1 VCC     -> VSYS / VBUS (5 V)
#   pin 2 SDA     -> GP12 (I2C0 SDA)
#   pin 3 SCL     -> GP13 (I2C0 SCL)
#   pin 4 GND     -> GND
#   pin 5 CONFIG  -> GND   (selects I2C -- read at power-up, so power-cycle)
#   pin 6         -> not connected
# If scan() finds nothing, add 4.7k pull-ups from SDA and SCL to 3V3(OUT).
#
# Usage (Ctrl-C main.py first):
#   import tfluna_i2c_test as t
#   t.scan()            # expect 0x10
#   t.info()            # firmware, mode, frame rate, output enable
#   t.run()             # live distance readings
#   t.factory_reset()   # restore defaults + save + reboot sensor

from machine import I2C, Pin
import time

SDA_PIN = 12
SCL_PIN = 13
ADDR = 0x10  # TF-Luna default

# Register map (TF-Luna product manual, I2C register table)
REG_DIST = 0x00      # 0x00-0x01 distance cm, 0x02-0x03 strength, 0x04-0x05 temp
REG_VERSION = 0x0A   # 0x0A-0x0C firmware revision/minor/major
REG_SAVE = 0x20
REG_REBOOT = 0x21    # write 0x02
REG_MODE = 0x23      # 0 = continuous, 1 = trigger
REG_ENABLE = 0x25    # 1 = output enabled
REG_FPS = 0x26       # 0x26-0x27 frame rate, Hz
REG_RESTORE = 0x29   # write 0x01


def _bus():
    return I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=100_000)


def _u16(b, i):
    return b[i] | (b[i + 1] << 8)


def scan():
    found = _bus().scan()
    print("I2C devices:", [hex(a) for a in found] or "none")
    if ADDR in found:
        print("-> TF-Luna found at 0x%02X -- the sensor is alive and talking" % ADDR)
    elif found:
        print("-> something answered, but not at 0x10 (address may have been changed)")
    else:
        print("-> nothing: check pin 5 is grounded, power-cycle, add 4.7k pull-ups")
    return found


def info(addr=ADDR):
    i2c = _bus()
    v = i2c.readfrom_mem(addr, REG_VERSION, 3)
    mode = i2c.readfrom_mem(addr, REG_MODE, 1)[0]
    enable = i2c.readfrom_mem(addr, REG_ENABLE, 1)[0]
    fps = _u16(i2c.readfrom_mem(addr, REG_FPS, 2), 0)
    print("firmware  %d.%d.%d" % (v[2], v[1], v[0]))
    print("mode      %d (%s)" % (mode, "continuous" if mode == 0 else "TRIGGER -- no streaming output"))
    print("enable    %d (%s)" % (enable, "on" if enable else "OUTPUT DISABLED"))
    print("fps       %d Hz%s" % (fps, "  <- 0 = no streaming output" if fps == 0 else ""))
    if mode != 0 or not enable or fps == 0:
        print("-> this would explain silence in UART mode; run factory_reset()")


def run(addr=ADDR, seconds=None, every_ms=200):
    i2c = _bus()
    start = time.ticks_ms()
    print("TF-Luna I2C 0x%02X on GP%d/GP%d -- Ctrl-C to stop" % (addr, SDA_PIN, SCL_PIN))
    try:
        while seconds is None or time.ticks_diff(time.ticks_ms(), start) < seconds * 1000:
            try:
                b = i2c.readfrom_mem(addr, REG_DIST, 6)
            except OSError as e:
                print("read failed: %r" % e)
            else:
                dist, strength = _u16(b, 0), _u16(b, 2)
                temp_c = _u16(b, 4) / 100.0
                note = "  (weak/unreliable)" if strength < 100 or strength == 65535 else ""
                print("dist %4d cm  strength %5d  temp %.1f C%s" % (dist, strength, temp_c, note))
            time.sleep_ms(every_ms)
    except KeyboardInterrupt:
        pass


def factory_reset(addr=ADDR):
    i2c = _bus()
    i2c.writeto_mem(addr, REG_RESTORE, b"\x01")
    time.sleep_ms(200)
    i2c.writeto_mem(addr, REG_SAVE, b"\x01")
    time.sleep_ms(200)
    try:
        i2c.writeto_mem(addr, REG_REBOOT, b"\x02")
    except OSError:
        pass  # sensor may drop off the bus mid-reboot
    print("defaults restored and saved. Unground pin 5, power-cycle, then retry the UART test.")