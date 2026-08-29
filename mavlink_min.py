# mavlink_min.py -- minimal MAVLink2 framing for the telemetry logger.
#
# Scope is deliberately narrow: reassemble raw frames off the UART for .tlog
# logging, decode the handful of fields the OLED needs, and build an outgoing
# HEARTBEAT so the FC starts/keeps streaming (dronespec.md Sec.5 notes this
# helps ArduPilot begin sending). We do not validate incoming checksums --
# QGroundControl/MAVExplorer will do that when the .tlog is replayed.

import ustruct as struct

MAVLINK2_STX = 0xFD
_HEADER_LEN = 10  # STX, len, incompat, compat, seq, sysid, compid, msgid(3)
_CRC_LEN = 2
_SIGNATURE_LEN = 13
_INCOMPAT_SIGNED = 0x01

# Highest real message ID across common.xml + ardupilotmega.xml, with
# generous headroom. We don't have a CRC_EXTRA table for every message type
# we might receive, so we can't fully checksum-validate incoming frames --
# but a stray 0xFD found inside another message's payload (a false sync)
# produces effectively random header bytes, which is astronomically unlikely
# to land under this bound by chance. Anything above it gets treated as a
# false sync rather than a real frame.
_MAX_PLAUSIBLE_MSGID = 16383

# CRC_EXTRA is only needed for messages we *build* (HEARTBEAT, COMMAND_LONG).
# Verify these against your dialect's C headers (mavlink_msg_*.h ->
# MAVLINK_MSG_ID_*_CRC) if the FC ever seems to ignore them -- worst case a
# wrong value just gets the frame silently dropped, nothing unsafe.
_HEARTBEAT_CRC_EXTRA = 50
_COMMAND_LONG_CRC_EXTRA = 152

# MAV_SYS_STATUS_SENSOR.MAV_SYS_STATUS_PREARM_CHECK -- ArduPilot reports its
# prearm-check result as a bit in SYS_STATUS's health field (set = armable),
# but only sets the matching bit in the present field on versions that
# actually support this, so present must be checked too.
_MAV_SYS_STATUS_PREARM_CHECK = 0x10000000

MAV_CMD_SET_MESSAGE_INTERVAL = 511

ARDUCOPTER_MODES = {
    0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED",
    5: "LOITER", 6: "RTL", 7: "CIRCLE", 9: "LAND", 11: "DRIFT",
    13: "SPORT", 16: "POSHOLD", 17: "BRAKE", 20: "GUIDED_NOGPS",
}


def x25crc(data, crc=0xFFFF):
    for byte in data:
        tmp = byte ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def build_heartbeat(seq, sysid=255, compid=190):
    """GCS-type heartbeat (type=MAV_TYPE_GCS, autopilot=MAV_AUTOPILOT_INVALID)."""
    payload = struct.pack("<IBBBBB", 0, 6, 8, 0, 4, 3)
    msgid = 0
    header = bytes([
        MAVLINK2_STX, len(payload), 0, 0, seq & 0xFF, sysid, compid,
        msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF,
    ])
    crc = x25crc(header[1:] + payload)
    crc = x25crc(bytes([_HEARTBEAT_CRC_EXTRA]), crc)
    return header + payload + struct.pack("<H", crc)


def build_set_message_interval(seq, target_sysid, target_compid, message_id, interval_us,
                                sysid=255, compid=190):
    """COMMAND_LONG / MAV_CMD_SET_MESSAGE_INTERVAL -- ask the FC to stream a
    specific message at a chosen rate, independent of any SRx_* param group
    existing for the port (some ports, e.g. a repurposed GPS UART, may not
    expose one)."""
    payload = struct.pack(
        "<fffffffHBBB",
        float(message_id), float(interval_us), 0.0, 0.0, 0.0, 0.0, 0.0,
        MAV_CMD_SET_MESSAGE_INTERVAL, target_sysid, target_compid, 0,
    )
    msgid = 76  # COMMAND_LONG
    header = bytes([
        MAVLINK2_STX, len(payload), 0, 0, seq & 0xFF, sysid, compid,
        msgid & 0xFF, (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF,
    ])
    crc = x25crc(header[1:] + payload)
    crc = x25crc(bytes([_COMMAND_LONG_CRC_EXTRA]), crc)
    return header + payload + struct.pack("<H", crc)


class FrameReader:
    """Byte-stream MAVLink2 frame assembler fed from a UART."""

    def __init__(self, uart):
        self.uart = uart
        self._buf = bytearray()
        self.resync_count = 0

    def poll(self):
        """Call regularly; returns a list of complete raw frames (bytes)."""
        n = self.uart.any()
        if n:
            self._buf.extend(self.uart.read(n))
        frames = []
        while True:
            frame = self._try_extract()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def _try_extract(self):
        buf = self._buf
        start = buf.find(bytes([MAVLINK2_STX]))
        if start == -1:
            buf[:] = b""
            return None
        if start > 0:
            buf[:start] = b""
        if len(buf) < _HEADER_LEN:
            return None

        payload_len = buf[1]
        incompat_flags = buf[2]
        signed = bool(incompat_flags & _INCOMPAT_SIGNED)
        total = _HEADER_LEN + payload_len + _CRC_LEN + (_SIGNATURE_LEN if signed else 0)

        if len(buf) < total:
            return None

        msgid = buf[7] | (buf[8] << 8) | (buf[9] << 16)
        if msgid > _MAX_PLAUSIBLE_MSGID:
            # False sync -- this "total" length is untrustworthy too (it was
            # read from bogus header bytes), so only drop the offending STX
            # and resync on the next 0xFD rather than skipping a whole
            # miscomputed frame length, which could eat a real frame.
            self.resync_count += 1
            buf[:1] = b""
            return None

        frame = bytes(buf[:total])
        buf[:total] = b""
        return frame


def _pad(payload, length):
    """MAVLink2 senders trim trailing zero *bytes* (not whole trailing
    fields) to save bandwidth -- e.g. a multi-byte field can arrive with its
    low byte present and its zero high byte(s) cut off. Zero-padding back out
    to the message's full non-extension length before unpacking reconstructs
    the true value either way, and needs no per-field length guards."""
    if len(payload) < length:
        return payload + bytes(length - len(payload))
    return payload


def decode(frame):
    """Best-effort decode of a few message types used for the OLED.

    Returns (msgid, dict) or (msgid, None) for messages we don't decode.
    Field layouts/offsets are the MAVLink2 wire order (fields sorted largest-
    first) for the *non-extension* portion of each message.
    """
    msgid = frame[7] | (frame[8] << 8) | (frame[9] << 16)
    payload = frame[10:10 + frame[1]]

    if msgid == 0:  # HEARTBEAT
        p = _pad(payload, 9)
        custom_mode, mtype, autopilot, base_mode, status = struct.unpack("<IBBBB", p[:8])
        return msgid, {
            "mode": ARDUCOPTER_MODES.get(custom_mode, str(custom_mode)),
        }

    if msgid == 2:  # SYSTEM_TIME -- time_unix_usec is 0 until the FC has a
        # real time source (derived from the GPS fix); nonzero from then on.
        p = _pad(payload, 12)
        time_unix_usec, = struct.unpack_from("<Q", p, 0)
        return msgid, {"time_unix_usec": time_unix_usec}

    if msgid == 1:  # SYS_STATUS
        p = _pad(payload, 31)
        present, _enabled, health = struct.unpack_from("<III", p, 0)
        voltage_mv = struct.unpack_from("<H", p, 14)[0]
        battery_remaining = struct.unpack_from("<b", p, 30)[0]
        if present & _MAV_SYS_STATUS_PREARM_CHECK:
            armable = bool(health & _MAV_SYS_STATUS_PREARM_CHECK)
        else:
            armable = None  # FC doesn't report prearm status this way
        return msgid, {
            "voltage_v": voltage_mv / 1000.0,
            "battery_pct": battery_remaining,
            "armable": armable,
        }

    if msgid == 24:  # GPS_RAW_INT
        p = _pad(payload, 30)
        fix_type, sats = struct.unpack_from("<BB", p, 28)
        return msgid, {
            "fix_type": fix_type,
            "satellites": sats,
        }

    if msgid == 74:  # VFR_HUD -- EKF-fused mag heading
        p = _pad(payload, 20)
        heading, = struct.unpack_from("<h", p, 16)
        return msgid, {"heading_deg": heading}

    if msgid == 65:  # RC_CHANNELS -- rssi is the RC link's own quality
        # reading (ELRS reports it via CRSF telemetry into this field),
        # scaled 0-254; 255 means "unknown/invalid". Some receiver/RSSI_TYPE
        # combinations never actually update this byte, so it can't be
        # trusted alone to notice a lost transmitter -- see STATUSTEXT (253).
        p = _pad(payload, 42)
        rssi, = struct.unpack_from("<B", p, 41)
        return msgid, {"rssi": rssi}

    if msgid == 253:  # STATUSTEXT -- ArduPilot emits "PreArm: Radio
        # failsafe on" / "...cleared" the instant the RC link state
        # changes, which is a reliable way to notice a lost transmitter
        # when RC_CHANNELS.rssi itself won't move.
        p = _pad(payload, 51)
        text = bytes(p[1:51]).split(b"\x00", 1)[0].decode()
        return msgid, {"text": text}

    if msgid == 27:  # RAW_IMU -- xmag/ymag/zmag is the external compass
        # (QMC5883L on the GPS module) in milligauss, raw/uncalibrated.
        # Decoded here just to confirm real data is flowing; the full
        # RAW_IMU frame (accel/gyro too) is already logged raw regardless.
        p = _pad(payload, 26)
        xmag, ymag, zmag = struct.unpack_from("<hhh", p, 20)
        return msgid, {"mag_mgauss": (xmag, ymag, zmag)}

    return msgid, None
