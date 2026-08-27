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
from util import MonotonicUs
from sdlog import TlogWriter
from oled_status import StatusDisplay


def _translate(msgid, fields):
    # HEARTBEAT / SYS_STATUS / GPS_RAW_INT / GLOBAL_POSITION_INT / VFR_HUD -> StatusDisplay kwargs
    if msgid == 0:
        return {"mode": fields["mode"], "armed": fields["armed"]}
    if msgid == 1:
        return {"voltage_v": fields["voltage_v"]}
    if msgid == 24:
        return {"fix_type": fields["fix_type"], "satellites": fields["satellites"]}
    if msgid == 33:
        return {"alt_m": fields["rel_alt_m"]}
    if msgid == 74:
        return {"heading_deg": fields["heading_deg"]}
    return {}


def _init_stage(label, fn):
    print("[init] %s ..." % label)
    try:
        result = fn()
    except Exception as e:
        print("[init] %s FAILED: %r" % (label, e))
        raise
    print("[init] %s OK" % label)
    return result


def main():
    print("=== telemetry logger booting ===")

    uart = _init_stage(
        "uart0 (mavlink)",
        lambda: UART(config.UART_ID, baudrate=config.UART_BAUD,
                      tx=Pin(config.UART_TX_PIN), rx=Pin(config.UART_RX_PIN)),
    )
    reader = FrameReader(uart)
    clock = MonotonicUs()

    print("[init] sd card + tlog ...")
    try:
        tlog = TlogWriter(config.SPI_ID, config.SPI_SCK_PIN, config.SPI_MOSI_PIN,
                           config.SPI_MISO_PIN, config.SD_CS_PIN,
                           sync_interval_ms=config.SD_SYNC_INTERVAL_MS)
        log_path = tlog.path
        print("[init] sd card + tlog OK -- logging to %s" % log_path)
    except Exception as e:
        # SD card/adapter not wired in yet (or faulty) -- keep flying blind on
        # logging rather than bricking the OLED status readout over it.
        print("[init] sd card + tlog FAILED: %r -- continuing without SD logging" % e)
        tlog = None
        log_path = "no SD"

    display = _init_stage(
        "oled",
        lambda: StatusDisplay(config.I2C_ID, config.I2C_SDA_PIN, config.I2C_SCL_PIN,
                               addr=config.OLED_ADDR),
    )
    display.update(log_path=log_path)

    print("=== entering main loop ===")

    frame_count = 0
    msgid_counts = {}
    heartbeat_seq = 0
    request_seq = 0
    fc_sysid = None
    fc_compid = None
    last_heartbeat = time.ticks_ms()
    last_oled = time.ticks_ms()
    last_stats = time.ticks_ms()
    last_request = 0  # force an immediate request as soon as we know the FC's ids

    while True:
        for frame in reader.poll():
            if tlog is not None:
                tlog.write_frame(frame, clock.now())
            frame_count += 1

            msgid, fields = decode(frame)
            msgid_counts[msgid] = msgid_counts.get(msgid, 0) + 1
            if msgid == 0:
                fc_sysid, fc_compid = frame[5], frame[6]
            if fields:
                print("[mavlink] msgid=%d %s" % (msgid, fields))
                display.update(**_translate(msgid, fields))

        now = time.ticks_ms()

        if time.ticks_diff(now, last_heartbeat) >= config.HEARTBEAT_INTERVAL_MS:
            uart.write(build_heartbeat(heartbeat_seq))
            print("[heartbeat] sent seq=%d" % heartbeat_seq)
            heartbeat_seq = (heartbeat_seq + 1) & 0xFF
            last_heartbeat = now

        if fc_sysid is not None and time.ticks_diff(now, last_request) >= config.STATUS_REQUEST_INTERVAL_MS:
            for wanted_id, interval_us in config.REQUESTED_MSG_INTERVALS_US.items():
                uart.write(build_set_message_interval(
                    request_seq, fc_sysid, fc_compid, wanted_id, interval_us))
                request_seq = (request_seq + 1) & 0xFF
            print("[request] asked sys=%d comp=%d for %d msgids" % (
                fc_sysid, fc_compid, len(config.REQUESTED_MSG_INTERVALS_US)))
            last_request = now

        if time.ticks_diff(now, last_oled) >= config.OLED_UPDATE_INTERVAL_MS:
            display.update(frames=frame_count)
            display.render()
            last_oled = now

        if time.ticks_diff(now, last_stats) >= config.STATS_PRINT_INTERVAL_MS:
            print("[stats] frames=%d resyncs=%d by_msgid=%s" % (
                frame_count, reader.resync_count, msgid_counts))
            last_stats = now


if __name__ == "__main__":
    main()
