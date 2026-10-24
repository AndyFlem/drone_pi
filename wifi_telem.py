# wifi_telem.py -- WiFi AP + UDP MAVLink bridge to a GCS (Pico 2 W onboard radio).
#
# Brings the Pico up as its own access point (no router/credentials needed in
# the field) and bridges raw MAVLink2 frames over UDP :14550. Telemetry is
# broadcast to the AP subnet rather than sent to a learned client address --
# this is the same pattern used by ESP8266/ESP32 ArduPilot wifi-telemetry
# bridges, and it's what QGroundControl's UDP auto-connect expects: it
# listens passively on 14550 and adopts whatever source address it first
# hears a frame from, so the vehicle side has to speak first, unprompted.

import network
import socket
import time

from pico_log import log

MAVLINK1_STX = 0xFE
MAVLINK2_STX = 0xFD


class TelemetryLink:
    """AP + non-blocking UDP socket for relaying MAVLink to/from a GCS."""

    def __init__(self, ssid, password, port, channel=None):
        self.port = port

        wlan = network.WLAN(network.AP_IF)
        if channel is not None:
            wlan.config(essid=ssid, password=password, channel=channel)
        else:
            wlan.config(essid=ssid, password=password)
        wlan.active(True)
        while not wlan.active():
            time.sleep_ms(100)
        self.wlan = wlan
        self.ip = wlan.ifconfig()[0]
        self.broadcast_addr = self.ip.rsplit(".", 1)[0] + ".255"
        log("[wifi] ap up ssid=%s ip=%s" % (ssid, self.ip))

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        sock.setblocking(False)
        self.sock = sock
        log("[wifi] udp bridge listening port=%d broadcasting to %s" % (port, self.broadcast_addr))

        self._stations = set()

    def send(self, frame):
        """Broadcast a raw MAVLink frame to the AP subnet. Best-effort --
        UDP telemetry is already not delivery-guaranteed, so a full send
        buffer or momentary radio hiccup is just dropped, same as any other
        lost telemetry packet."""
        try:
            self.sock.sendto(frame, (self.broadcast_addr, self.port))
        except OSError:
            pass

    def poll_commands(self):
        """Return a list of raw MAVLink frames received from the GCS since
        the last call. Non-blocking; returns [] when nothing is waiting."""
        frames = []
        while True:
            try:
                data, _addr = self.sock.recvfrom(300)
            except OSError:
                break
            if data and data[0] in (MAVLINK1_STX, MAVLINK2_STX):
                frames.append(data)
        return frames

    def check_stations(self):
        """Poll devices currently associated with the AP and print
        connect/disconnect debug lines. Call periodically, not every loop
        iteration -- station association doesn't change often, and
        status('stations') isn't a free call."""
        try:
            stations = self.wlan.status("stations")
        except (OSError, ValueError):
            return  # not supported by this firmware -- nothing to report

        macs = set(mac for mac, *_ in stations)
        for mac in macs - self._stations:
            log("[wifi] station connected mac=%s" % _format_mac(mac))
        for mac in self._stations - macs:
            log("[wifi] station disconnected mac=%s" % _format_mac(mac))
        self._stations = macs


def _format_mac(mac):
    return ":".join("%02x" % b for b in mac)
