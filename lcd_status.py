# lcd_status.py -- 240x240 ST7789 IPS status screen (ZJY-IPS130 V2.0):
# mode/armable, GPS fix, battery voltage, uptime/RSSI, and SD logging status.
# Same interface as oled_status.StatusDisplay; config.DISPLAY_TYPE picks one.

import time

import rp2
from machine import Pin

import st7789
from st7789 import WHITE, RED, GREEN, YELLOW, CYAN, GREY

_MODE_LABEL = {"STABILIZE": "STAB"}  # everything else (ALT_HOLD, LOITER, ...) shown as-is

# Pixel rows of the five text lines -- 16px-tall text spread over 240px.
_ROW_Y = (12, 60, 108, 156, 204)


# Write-only SPI mode 3, MSB first: data changes on the falling edge, the
# panel samples on the rising one, 2 PIO cycles per bit plus 2 per byte. SCK
# must idle high between bytes -- with no CS pin the panel only stays in
# step if the clock rests high, so the SM waits on `pull` with SCK high
# rather than stalling mid-bit.
@rp2.asm_pio(out_init=rp2.PIO.OUT_LOW, sideset_init=rp2.PIO.OUT_HIGH,
             out_shiftdir=rp2.PIO.SHIFT_LEFT, fifo_join=rp2.PIO.JOIN_TX)
def _spi_tx():
    pull().side(1)
    set(x, 7).side(1)
    label("bit")
    out(pins, 1).side(0)
    jmp(x_dec, "bit").side(1)


class PioSpiTx:
    # Stand-in for machine.SPI with just the write() st7789 uses. Replaces
    # SoftSPI, whose bit-banged ~0.5 Mbit/s held the main loop for ~125 ms
    # per text row and overflowed the UART RX buffer (log0103 [loop] stats).
    def __init__(self, sm_id, sck, mosi, baudrate):
        self._sm = rp2.StateMachine(sm_id, _spi_tx, freq=2 * baudrate,
                                    sideset_base=Pin(sck), out_base=Pin(mosi))
        self._sm.active(1)
        # Time for the last byte to leave the OSR once the FIFO reads empty.
        # 9 bit-times per byte (8 bits + pull/set).
        self._drain_us = 9_000_000 // baudrate + 1

    def write(self, buf):
        self._sm.put(buf, 24)  # one byte per FIFO word, moved to the top bits
        # Block until it's all on the wire: st7789 flips DC straight after.
        while self._sm.tx_fifo():
            pass
        time.sleep_us(self._drain_us)


class StatusDisplay:
    def __init__(self, sck, mosi, dc, rst, bl=None, rotation=0,
                 pio_sm=0, baudrate=20_000_000):
        # PIO rather than a hardware bus: SPI0 (SD) and SPI1 (radio) are both
        # taken, and this CS-less panel can't share either of them.
        spi = PioSpiTx(pio_sm, sck, mosi, baudrate)
        self.lcd = st7789.ST7789(spi, Pin(dc), Pin(rst),
                                 bl=Pin(bl) if bl is not None else None,
                                 rotation=rotation)
        self.state = {
            "mode": "?", "armable": None,
            "fix_type": 0, "satellites": 0,
            "voltage_v": 0.0, "battery_pct": -1, "uptime_s": 0,
            "log_path": "-", "frames": 0,
            "heading_deg": 0, "rssi_pct": None, "rc_ok": None,
            "lora_rssi": None,
        }
        self._blink = False
        # Last parts drawn per row -- only rows that changed get re-sent,
        # since every row push holds the CPU until its ~7.7 KB is on the wire.
        self._drawn = [None] * len(_ROW_Y)

    def update(self, **kwargs):
        self.state.update(kwargs)

    def _row(self, i, *parts):
        if parts != self._drawn[i]:
            self.lcd.text_row(_ROW_Y[i], parts)
            self._drawn[i] = parts

    def _right(self, text):
        # Column that right-aligns text on the row.
        return self.lcd.cols - len(text)

    def render(self):
        # 8x8 font doubled to 16x16; at 240px wide that's 15 chars/line max --
        # keep every line under that or it silently clips off the right edge.
        s = self.state

        mode_text = _MODE_LABEL.get(s["mode"], s["mode"])[:11]
        if s["armable"] is True:
            armable_text, armable_col = "RDY", GREEN
        elif s["armable"] is False:
            armable_text, armable_col = "BAD", RED
        else:
            armable_text, armable_col = "?", GREY
        self._row(0, (0, mode_text, CYAN),
                  (self._right(armable_text), armable_text, armable_col))

        if s["fix_type"] < 2:
            gps_text, gps_col = "No-fix", RED
        else:
            gps_text, gps_col = "Fix (%d)" % s["satellites"], GREEN
        # No degree glyph in the built-in 8x8 font -- plain zero-padded number.
        heading_text = "%03d" % (s["heading_deg"] % 360)
        self._row(1, (0, gps_text, gps_col),
                  (self._right(heading_text), heading_text, WHITE))

        pct_text = "%d%%" % s["battery_pct"] if s["battery_pct"] >= 0 else "?%"
        self._row(2, (0, "Batt:%.1fV %s" % (s["voltage_v"], pct_text), YELLOW))

        uptime_text = "%02d:%02d" % (s["uptime_s"] // 60, s["uptime_s"] % 60)
        if s["rc_ok"] is False:
            # ArduPilot doesn't reset RC_CHANNELS.rssi on failsafe -- it just
            # stops updating, so a stale reading would otherwise linger here.
            rssi_text, rssi_col = "RSSI:LOST", RED
        elif s["rssi_pct"] is not None:
            rssi_text, rssi_col = "RSSI:%d%%" % s["rssi_pct"], WHITE
        else:
            rssi_text, rssi_col = "RSSI:--", GREY
        self._row(3, (0, uptime_text, WHITE),
                  (self._right(rssi_text), rssi_text, rssi_col))

        if s["log_path"] in (None, "no SD"):
            sd_text, sd_col = "No SD", RED
        else:
            sd_text, sd_col = ("Logging." if self._blink else "Logging"), GREEN
        self._blink = not self._blink

        # RSSI (dBm) of the last LoRa packet from the ground; "--" once no
        # packet has been heard for a few seconds (or no radio fitted).
        if s["lora_rssi"] is None:
            lora_text, lora_col = "L:--", GREY
        else:
            lora_text, lora_col = "L:%d" % s["lora_rssi"], WHITE
        self._row(4, (0, sd_text, sd_col),
                  (self._right(lora_text), lora_text, lora_col))
