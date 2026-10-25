# main.py -- Pico 2 W telemetry logger entry point (auto-runs on boot).
#
# Reads MAVLink2 off UART0 (wired to FC UART3), writes each frame to a
# QGroundControl-compatible .tlog on the microSD card, and drives a live
# status screen (SSD1306 OLED or ST7789 IPS, per config.DISPLAY_TYPE). The FC stream is relayed to a GCS over
# the Pico's WiFi AP (wifi_telem.py) and, as a light message set, over a
# 433 MHz LoRa backup link (lora_link.py + sx126x.py, see radio-notes.md).
# Pin/bus assignments: config.py, which mirrors dronespec.md Sec.5.
#
# Third-party drivers required alongside this file -- deliberately NOT
# vendored here; pull the tested upstream versions rather than a hand-copied
# one, since SD/SPI block-device timing is easy to get subtly wrong:
#   import mip; mip.install("sdcard")
#   import mip; mip.install("ssd1306")   # only for DISPLAY_TYPE = "ssd1306"
# (run those once from a REPL with the board on Wi-Fi, or copy sdcard.py /
# ssd1306.py from the official micropython/micropython drivers/ tree onto
# the board next to this file.)

import time
from machine import UART, Pin

import config
from mavlink_min import FrameReader, build_heartbeat, build_set_message_interval, decode
from util import WallClock
from sdlog import TlogWriter, TextLogWriter
from wifi_telem import TelemetryLink
from lora_link import LoraLink
from camera import CameraRemote, RcSwitch, PHOTO, VIDEO
from pico_log import log, attach as attach_text_log, attach_clock
import sx126x

# MAV_CMD_SET_MESSAGE_INTERVAL, and the sysid/compid build_heartbeat()/
# build_set_message_interval() send as.
_CMD_SET_MESSAGE_INTERVAL = 511
_OWN_SYSID = 255
_OWN_COMPID = 190


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


def _is_own_ack(msgid, fields):
    # The FC's COMMAND_ACKs to our periodic SET_MESSAGE_INTERVAL burst --
    # one per requested message every STATUS_REQUEST_INTERVAL_MS, which as
    # LoRa priority traffic would eat a large share of the downlink. (A GCS
    # on 255/190 sending the same command would lose its ACK over LoRa too;
    # it will still see it over WiFi.)
    return (msgid == 77 and fields is not None
            and fields["command"] == _CMD_SET_MESSAGE_INTERVAL
            and fields["target_system"] == _OWN_SYSID
            and fields["target_component"] == _OWN_COMPID)


def _start_lora(uart):
    radio = sx126x.SX126x(config.RADIO_SPI_ID, config.RADIO_SCK_PIN, config.RADIO_MOSI_PIN,
                          config.RADIO_MISO_PIN, config.RADIO_NSS_PIN, config.RADIO_BUSY_PIN,
                          config.RADIO_DIO1_PIN, config.RADIO_NRST_PIN, config.RADIO_TXEN_PIN,
                          config.RADIO_RXEN_PIN, config.RADIO_SPI_BAUD)
    radio.begin(config.RADIO_FREQ_HZ, config.RADIO_SF, config.RADIO_BW_KHZ, config.RADIO_CR,
                config.RADIO_PREAMBLE, config.RADIO_TX_POWER_DBM, config.RADIO_SYNC_WORD,
                config.RADIO_TCXO_VOLTAGE, config.RADIO_USE_DCDC)
    log("[lora] radio up: %.3f MHz SF%d BW%d %d dBm, %s" % (
        config.RADIO_FREQ_HZ / 1e6, config.RADIO_SF, config.RADIO_BW_KHZ,
        config.RADIO_TX_POWER_DBM, "TCXO %.1f V" % radio.tcxo if radio.tcxo else "crystal"))
    lora = LoraLink(config, radio, uart, led=Pin("LED", Pin.OUT, value=0))
    log("[lora] " + lora.describe())
    return lora


def _start_display():
    # Imported here so only the selected screen's driver has to be on the board.
    if config.DISPLAY_TYPE == "st7789":
        from lcd_status import StatusDisplay
        return StatusDisplay(config.DISPLAY_SCK_PIN, config.DISPLAY_MOSI_PIN,
                             config.DISPLAY_MISO_PIN, config.DISPLAY_DC_PIN,
                             config.DISPLAY_RST_PIN, bl=config.DISPLAY_BL_PIN,
                             rotation=config.DISPLAY_ROTATION)
    from oled_status import StatusDisplay
    return StatusDisplay(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN,
                         addr=config.OLED_ADDR)


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
        lambda: TelemetryLink(config.AP_SSID, config.AP_PASSWORD, config.GCS_UDP_PORT,
                               channel=config.AP_CHANNEL),
    )

    log("[init] lora radio ...")
    try:
        lora = _start_lora(uart)
        log("[init] lora radio OK")
    except Exception as e:
        # Backup link only -- a missing/faulty radio module mustn't take down
        # logging or the WiFi link.
        log("[init] lora radio FAILED: %r -- continuing without LoRa" % e)
        lora = None

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
        # logging rather than bricking the status display over it.
        log("[init] sd card + tlog FAILED: %r -- continuing without SD logging" % e)
        tlog = None
        log_path = "no SD"

    display = _init_stage(
        "display (%s)" % config.DISPLAY_TYPE,
        _start_display,
    )
    display.update(log_path=log_path)

    camera = _init_stage(
        "camera remote",
        lambda: CameraRemote(config.CAMERA_PHOTO_PIN, config.CAMERA_VIDEO_PIN,
                             press_ms=config.CAMERA_PRESS_MS, gap_ms=config.CAMERA_GAP_MS),
    )
    video_switch = RcSwitch(config.CAMERA_VIDEO_RC_CHAN) if config.CAMERA_VIDEO_RC_CHAN else None
    photo_switch = RcSwitch(config.CAMERA_PHOTO_RC_CHAN) if config.CAMERA_PHOTO_RC_CHAN else None

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
    last_display = time.ticks_ms()
    last_stations = time.ticks_ms()
    last_summary = time.ticks_ms()
    last_lora_stats = time.ticks_ms()
    last_request = 0  # force an immediate request as soon as we know the FC's ids

    while True:
        # The LoRa link is polled at several points per iteration, not just
        # once: after a transmit it has to be back in RX within a few ms to
        # catch the ground reply, and an SD sync or display push can block for
        # longer than that.
        if lora is not None:
            lora.poll()

        for frame in reader.poll():
            if tlog is not None:
                tlog.write_frame(frame, clock.now())
            frame_count += 1

            msgid, fields = decode(frame)
            if msgid not in config.WIFI_EXCLUDE_MSGIDS:
                link.send(frame)
            if lora is not None and not _is_own_ack(msgid, fields):
                lora.offer(frame, msgid)
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
                        # last_armed is None on the first HEARTBEAT -- booting
                        # into an already-armed FC isn't an arm event.
                        if config.CAMERA_RECORD_ON_ARM and last_armed is not None:
                            log("[camera] video toggle (%s)" % ("armed" if armed else "disarmed"))
                            camera.press(VIDEO)
                        last_armed = armed
                elif msgid == 1:
                    last_battery = fields
                    armable = fields["armable"]
                    if armable is not None and armable != last_armable:
                        log("[flight] %s" % ("READY TO ARM" if armable else "NOT READY TO ARM"))
                        last_armable = armable
                elif msgid == 253 and "prearm" in fields["text"].lower():
                    log("[flight] %s" % fields["text"])
                elif msgid == 65:
                    channels = fields["channels"]
                    if video_switch is not None and video_switch.update(channels) is not None:
                        log("[camera] video toggle (ch%d)" % config.CAMERA_VIDEO_RC_CHAN)
                        camera.press(VIDEO)
                    if photo_switch is not None and photo_switch.update(channels):
                        log("[camera] photo (ch%d)" % config.CAMERA_PHOTO_RC_CHAN)
                        camera.press(PHOTO)
                elif msgid == 33:
                    last_position = fields
                elif msgid == 30:
                    last_attitude = fields

        if lora is not None:
            lora.poll()
        camera.poll()

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

        if time.ticks_diff(now, last_display) >= config.DISPLAY_UPDATE_INTERVAL_MS:
            display.update(frames=frame_count, uptime_s=time.ticks_diff(now, boot_ms) // 1000,
                           lora_rssi=lora.rssi if lora is not None else None)
            display.render()
            last_display = now
            if lora is not None:
                lora.poll()

        if lora is not None and time.ticks_diff(now, last_lora_stats) >= config.LORA_STATS_INTERVAL_MS:
            log("[lora] " + lora.stats())
            last_lora_stats = now

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
