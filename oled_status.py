# oled_status.py -- 128x64 SSD1306 status screen: mode/armable, GPS fix,
# battery voltage, uptime/RSSI, and SD logging status.

from machine import I2C, Pin

import ssd1306  # mip.install("ssd1306"), see main.py header

_MODE_LABEL = {"STABILIZE": "STAB"}  # everything else (ALT_HOLD, LOITER, ...) shown as-is


class StatusDisplay:
    def __init__(self, i2c_id, sda, scl, addr=0x3C, width=128, height=64):
        i2c = I2C(i2c_id, sda=Pin(sda), scl=Pin(scl), freq=400_000)
        self.oled = ssd1306.SSD1306_I2C(width, height, i2c, addr=addr)
        self.state = {
            "mode": "?", "armable": None,
            "fix_type": 0, "satellites": 0,
            "voltage_v": 0.0, "battery_pct": -1, "uptime_s": 0,
            "log_path": "-", "frames": 0,
            "heading_deg": 0, "rssi_pct": None, "rc_ok": None,
        }
        self._blink = False

    def update(self, **kwargs):
        self.state.update(kwargs)

    def render(self):
        # Built-in font is 8x8px; at 128px wide that's 16 chars/line max --
        # keep every line under that or it silently clips off the right edge.
        #
        # This panel is a bi-colour SSD1306 (yellow rows 0-15, blue rows
        # 16-63) -- no line may cross row 16 or it prints half in each
        # colour. Row 0 is the only line in the yellow band; 16/28/40/52
        # stay clear of it in blue.
        s = self.state
        o = self.oled
        o.fill(0)

        mode_text = _MODE_LABEL.get(s["mode"], s["mode"])[:12]
        if s["armable"] is True:
            armable_text = "RDY"
        elif s["armable"] is False:
            armable_text = "BAD"
        else:
            armable_text = "?"
        o.text(mode_text, 0, 0)
        o.text(armable_text, 128 - len(armable_text) * 8, 0)

        if s["fix_type"] < 2:
            gps_text = "No-fix"
        else:
            gps_text = "Fix (%d)" % s["satellites"]
        o.text(gps_text, 0, 16)

        # No degree glyph in the built-in 8x8 font -- plain zero-padded number.
        heading_text = "%03d" % (s["heading_deg"] % 360)
        o.text(heading_text, 128 - len(heading_text) * 8, 16)

        pct_text = "%d%%" % s["battery_pct"] if s["battery_pct"] >= 0 else "?%"
        o.text("Batt:%.1fV %s" % (s["voltage_v"], pct_text), 0, 28)
        uptime_text = "%02d:%02d" % (s["uptime_s"] // 60, s["uptime_s"] % 60)
        if s["rc_ok"] is False:
            # ArduPilot doesn't reset RC_CHANNELS.rssi on failsafe -- it just
            # stops updating, so a stale reading would otherwise linger here.
            rssi_text = "RSSI:LOST"
        elif s["rssi_pct"] is not None:
            rssi_text = "RSSI:%d%%" % s["rssi_pct"]
        else:
            rssi_text = "RSSI:--"
        o.text(uptime_text, 0, 40)
        o.text(rssi_text, 128 - len(rssi_text) * 8, 40)

        if s["log_path"] in (None, "no SD"):
            sd_text = "No SD"
        else:
            sd_text = "Logging." if self._blink else "Logging"
        o.text(sd_text, 0, 52)
        self._blink = not self._blink

        o.show()
