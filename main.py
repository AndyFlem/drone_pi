# main.py -- Pico 2 W telemetry logger entry point (auto-runs on boot).
#
# Reads MAVLink2 off UART0 (wired to FC UART3), writes each frame to a
# QGroundControl-compatible .tlog on the microSD card, and drives a live
# status screen on the SSD1306 OLED. Pin/bus assignments: config.py, which
# mirrors dronespec.md Sec.5.
#
# Third-party drivers required alongside this file -- deliberately NOT
# vendored here; pull the tested upstream versions rather than a hand-copied
# one, since SD/SPI block-device timing is easy to get subtly wrong:
#   import mip; mip.install("sdcard")
#   import mip; mip.install("ssd1306")
# (run those once from a REPL with the board on Wi-Fi, or copy sdcard.py /
# ssd1306.py from the official micropython/micropython drivers/ tree onto
# the board next to this file.)

import time
from machine import UART, Pin

import config
from mavlink_min import FrameReader, build_heartbeat, build_set_message_interval, decode
from util import WallClock
from sdlog import TlogWriter, TextLogWriter
from oled_status import StatusDisplay
from wifi_telem import TelemetryLink
from pico_log import log, attach as attach_text_log, attach_clock


def _translate(msgid, fields):
    # HEARTBEAT / SYS_STATUS / GPS_RAW_INT / VFR_HUD / RC_CHANNELS / STATUSTEXT -> StatusDisplay kwargs
    if msgid == 0:
        return {"mode": fields["mode"]}
    if msgid == 1:
        return {"voltage_v": fields["voltage_v"], "battery_pct": fields["battery_pct"],
                "armable": fields["armable"]}
    if msgid == 24:
        return {"fix_type": fields["fix_type"], "satellites": fields["satellites"]}
    if msgid == 74:
        return {"heading_deg": fields["heading_deg"]}
    if msgid == 65:
        rssi = fields["rssi"]
        return {"rssi_pct": None if rssi == 255 else rssi * 100 // 254}
    if msgid == 253:
        text = fields["text"].lower()
        if "radio failsafe" in text:
            return {"rc_ok": "clear" in text}
    return {}


def _battery_text(battery):
    if battery is None:
        return None
    pct = "%d%%" % battery["battery_pct"] if battery["battery_pct"] >= 0 else "?%"
    return "batt=%.1fV %s" % (battery["voltage_v"], pct)


def _init_stage(label, fn):
    log("[init] %s ..." % label)
    try:
        result = fn()
    except Exception as e:
        log("[init] %s FAILED: %r" % (label, e))
        raise
    log("[init] %s OK" % label)
    return result


def main():
    boot_ms = time.ticks_ms()
    log("=== telemetry logger booting ===")

    uart = _init_stage(
        "uart0 (mavlink)",
        lambda: UART(config.UART_ID, baudrate=config.UART_BAUD,
                      tx=Pin(config.UART_TX_PIN), rx=Pin(config.UART_RX_PIN),
                      rxbuf=1024),
    )
    reader = FrameReader(uart)
    clock = WallClock()
    attach_clock(clock)

    link = _init_stage(
        "wifi ap + udp bridge",
        lambda: TelemetryLink(config.AP_SSID, config.AP_PASSWORD, config.GCS_UDP_PORT),
    )

    log("[init] sd card + tlog ...")
    try:
        tlog = TlogWriter(config.SPI_ID, config.SPI_SCK_PIN, config.SPI_MOSI_PIN,
                           config.SPI_MISO_PIN, config.SD_CS_PIN,
                           sync_interval_ms=config.SD_SYNC_INTERVAL_MS)
        log_path = tlog.path
        log("[init] sd card + tlog OK -- logging to %s" % log_path)
        try:
            text_log = TextLogWriter(tlog.mount_point, tlog.session_id,
                                      sync_interval_ms=config.SD_SYNC_INTERVAL_MS)
            attach_text_log(text_log)
            log("[init] text log OK -- logging to %s" % text_log.path)
        except Exception as e:
            # Debug/flight-event log is a nice-to-have alongside the .tlog --
            # its absence shouldn't take down telemetry logging either.
            log("[init] text log FAILED: %r -- REPL-only debug output" % e)
    except Exception as e:
        # SD card/adapter not wired in yet (or faulty) -- keep flying blind on
        # logging rather than bricking the OLED status readout over it.
        log("[init] sd card + tlog FAILED: %r -- continuing without SD logging" % e)
        tlog = None
        log_path = "no SD"

    display = _init_stage(
        "oled",
        lambda: StatusDisplay(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN,
                               addr=config.OLED_ADDR),
    )
    display.update(log_path=log_path)

    log("=== entering main loop ===")

    frame_count = 0
    heartbeat_seq = 0
    request_seq = 0
    fc_sysid = None
    fc_compid = None
    last_mode = None
    last_armed = None
    last_armable = None
    last_position = None
    last_attitude = None
    last_battery = None
    last_heartbeat = time.ticks_ms()
    last_oled = time.ticks_ms()
    last_stations = time.ticks_ms()
    last_summary = time.ticks_ms()
    last_request = 0  # force an immediate request as soon as we know the FC's ids

    while True:
        for frame in reader.poll():
            if tlog is not None:
                tlog.write_frame(frame, clock.now())
            frame_count += 1

            msgid, fields = decode(frame)
            if msgid not in config.WIFI_EXCLUDE_MSGIDS:
                link.send(frame)
            if msgid == 0:
                fc_sysid, fc_compid = frame[5], frame[6]
            if msgid == 2 and fields and fields["time_unix_usec"]:
                was_synced = clock.synced
                clock.sync(fields["time_unix_usec"])
                if not was_synced:
                    log("[time] GPS-derived UNIX time now available -- log timestamps synced")
            if fields:
                display.update(**_translate(msgid, fields))

                if msgid == 0:
                    mode = fields["mode"]
                    if mode != last_mode:
                        log("[flight] mode: %s -> %s" % (last_mode, mode))
                        last_mode = mode
                    armed = fields["armed"]
                    if armed != last_armed:
                        batt = _battery_text(last_battery)
                        log("[flight] %s%s" % ("ARMED" if armed else "DISARMED",
                                                " (%s)" % batt if batt else ""))
                        last_armed = armed
                elif msgid == 1:
                    last_battery = fields
                    armable = fields["armable"]
                    if armable is not None and armable != last_armable:
                        log("[flight] %s" % ("READY TO ARM" if armable else "NOT READY TO ARM"))
                        last_armable = armable
                elif msgid == 253 and "prearm" in fields["text"].lower():
                    log("[flight] %s" % fields["text"])
                elif msgid == 33:
                    last_position = fields
                elif msgid == 30:
                    last_attitude = fields

        for cmd in link.poll_commands():
            uart.write(cmd)

        now = time.ticks_ms()

        if time.ticks_diff(now, last_heartbeat) >= config.HEARTBEAT_INTERVAL_MS:
            uart.write(build_heartbeat(heartbeat_seq))
            heartbeat_seq = (heartbeat_seq + 1) & 0xFF
            last_heartbeat = now

        if fc_sysid is not None and time.ticks_diff(now, last_request) >= config.STATUS_REQUEST_INTERVAL_MS:
            for wanted_id, interval_us in config.REQUESTED_MSG_INTERVALS_US.items():
                uart.write(build_set_message_interval(
                    request_seq, fc_sysid, fc_compid, wanted_id, interval_us))
                request_seq = (request_seq + 1) & 0xFF
            last_request = now

        if time.ticks_diff(now, last_oled) >= config.OLED_UPDATE_INTERVAL_MS:
            display.update(frames=frame_count, uptime_s=time.ticks_diff(now, boot_ms) // 1000)
            display.render()
            last_oled = now

        if time.ticks_diff(now, last_stations) >= config.STATION_CHECK_INTERVAL_MS:
            link.check_stations()
            last_stations = now

        if time.ticks_diff(now, last_summary) >= config.FLIGHT_SUMMARY_INTERVAL_MS:
            if last_position is not None and last_attitude is not None:
                hdg = last_position["hdg_deg"]
                batt = _battery_text(last_battery)
                log("[flight] %spos lat=%.6f lon=%.6f alt=%.1fm hdg=%s | att roll=%.1f pitch=%.1f yaw=%.1f" % (
                    (batt + " | ") if batt else "",
                    last_position["lat_deg"], last_position["lon_deg"], last_position["rel_alt_m"],
                    "%.0f" % hdg if hdg is not None else "?",
                    last_attitude["roll_deg"], last_attitude["pitch_deg"], last_attitude["yaw_deg"]))
            last_summary = now


if __name__ == "__main__":
    main()
