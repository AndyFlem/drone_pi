# lora_link.py -- 433 MHz LoRa backup MAVLink telemetry link, drone side.
#
# Half-duplex on a single frequency. The drone owns the timing: it transmits
# every DRONE_TX_INTERVAL_MS and otherwise listens. The ground station stays
# in RX and only replies straight after a drone packet, so its reply lands in
# the drone's listen window (LoRaWAN Class A style). Hardware and protocol
# notes: radio-notes.md.
#
# The over-air format must stay identical to the ground station's:
# Packet: [net_id][flags][seq][peer_rssi][peer_snr] + whole MAVLink frames
#   flags bit 7: sent by the drone
#   peer_rssi:   -dBm of the last packet heard from the other side (0 = none)
#   peer_snr:    its SNR in dB, signed
#
# Downlink: main.py offers every FC frame; DroneQueue keeps a light message
# set (config.LORA_*) that fits the airtime budget. Uplink: ground packets
# carry whole MAVLink frames from the GCS, written straight to the FC UART.

import struct
import time

import sx126x
from mavlink_min import build_radio_status, sik_rssi
from pico_log import log

HDR_LEN = 5
_FLAG_DRONE = 0x80
_PEER_TIMEOUT_MS = 3000


def _max_len_for(radio, budget_ms):
    n = 255
    while n >= HDR_LEN and radio.airtime_ms(n) > budget_ms:
        n -= 1
    if n < HDR_LEN:
        raise ValueError("airtime budget %.1f ms too small for a packet" % budget_ms)
    return n


class DroneQueue:
    """FC -> radio. Priority frames are FIFO; stream frames keep only the latest
    per (msgid, sysid, compid) and are sent at most at their configured rate."""

    def __init__(self, priority_msgs, stream_rates, share, queue_len):
        self._prio_ids = priority_msgs
        self._period = {k: int(1000 / v) for k, v in stream_rates.items()}
        self._share = share
        self._max = queue_len
        self._prio = []
        self._stream = {}
        self._last = {}
        self.dropped = 0

    def add(self, frame, msgid):
        if msgid in self._prio_ids:
            if len(self._prio) >= self._max:
                self.dropped += 1
            else:
                self._prio.append(frame)
        elif msgid in self._period:
            self._stream[(msgid, frame[5], frame[6])] = frame
        # anything else is not part of the radio message set

    def pending(self):
        return len(self._prio) + len(self._stream)

    def _take_prio(self, out, limit):
        prio = self._prio
        while prio:
            n = len(prio[0])
            if HDR_LEN + n > 255:
                prio.pop(0)  # can never fit
                self.dropped += 1
            elif len(out) + n <= limit:
                out += prio.pop(0)
            else:
                break

    def build(self, room, now):
        due = []
        for k in self._stream:
            last = self._last.get(k)
            if last is None:
                due.append((-1 << 30, k))
            else:
                # Most overdue relative to its own rate goes first.
                age = time.ticks_diff(now, last)
                period = self._period[k[0]]
                if age >= period:
                    due.append((-age / period, k))
        due.sort()
        out = bytearray()
        self._take_prio(out, int(room * self._share) if due else room)
        for _, k in due:
            raw = self._stream[k]
            if len(out) + len(raw) <= room:
                out += raw
                del self._stream[k]
                self._last[k] = now
        self._take_prio(out, room)
        return out


class LoraLink:
    def __init__(self, cfg, radio, uart, led=None):
        self.cfg = cfg
        self.radio = radio
        self.uart = uart
        self.led = led

        # Airtime per slot, split between the drone packet and the ground
        # reply -- must match the ground station's calculation.
        slot = cfg.DRONE_TX_INTERVAL_MS
        duty = cfg.RADIO_DUTY_CYCLE
        self.drone_len = _max_len_for(radio, min(slot * duty, slot * 0.5))
        drone_air = radio.airtime_ms(self.drone_len)
        self.ground_len = _max_len_for(
            radio, min(slot * duty, slot - drone_air - cfg.GUARD_MS - cfg.GROUND_REPLY_DELAY_MS))
        self.defer_ms = int(radio.airtime_ms(self.ground_len)) + 10

        self.queue = DroneQueue(cfg.LORA_PRIORITY_MSGS, cfg.LORA_STREAM_RATES,
                                cfg.LORA_PRIORITY_SHARE, cfg.LORA_PRIORITY_QUEUE_LEN)

        now = time.ticks_ms()
        self.t_start = now
        self.seq = 0
        self.status_seq = 0
        self.tx_busy = False
        self.tx_started = now
        self.tx_air = 0
        self.next_tx = now
        self.defer_start = None
        self.next_status = now
        self.led_off = None

        self.rssi = self.snr = None  # what we hear from the ground
        self.peer_rssi = self.peer_snr = None  # what the ground hears from us
        self.last_rx = None
        self.last_seq = None
        self.n_tx = self.n_rx = self.n_lost = self.n_crc = self.n_foreign = 0
        self.airtime_total = 0.0
        self.bytes_up = self.bytes_down = 0

        radio.start_rx()

    def describe(self):
        r = self.radio
        return ("drone packet <= %d B (%.0f ms), ground reply <= %d B (%.0f ms), "
                "slot %d ms" % (self.drone_len, r.airtime_ms(self.drone_len),
                                self.ground_len, r.airtime_ms(self.ground_len),
                                self.cfg.DRONE_TX_INTERVAL_MS))

    def offer(self, frame, msgid):
        """Hand over a raw MAVLink2 frame from the FC for the downlink."""
        self.queue.add(frame, msgid)

    # ---- main loop step ----
    def poll(self):
        """Call as often as possible: the radio has to go back to RX within
        GROUND_REPLY_DELAY_MS of TxDone to catch the ground reply."""
        now = time.ticks_ms()

        if self.radio.dio1.value():
            self._service_irq(now)
        elif self.tx_busy and time.ticks_diff(now, self.tx_started) > self.tx_air * 2 + 100:
            log("[lora] TX timeout, restarting RX")
            self.tx_busy = False
            self.radio.start_rx()

        self._schedule(now)

        if self.last_rx is not None and time.ticks_diff(now, self.last_rx) > _PEER_TIMEOUT_MS:
            self.rssi = self.snr = self.peer_rssi = self.peer_snr = None
            self.last_rx = None

        if self.cfg.LORA_INJECT_RADIO_STATUS and time.ticks_diff(now, self.next_status) >= 0:
            self.next_status = time.ticks_add(now, self.cfg.LORA_RADIO_STATUS_INTERVAL_MS)
            self._send_radio_status()

        if self.led_off is not None and time.ticks_diff(now, self.led_off) >= 0:
            self.led(0)
            self.led_off = None

    def _service_irq(self, now):
        irq = self.radio.irq_status()
        self.radio.clear_irq()
        if self.tx_busy and irq & (sx126x.IRQ_TX_DONE | sx126x.IRQ_TIMEOUT):
            self.tx_busy = False
            self.radio.start_rx()
            return
        if irq & (sx126x.IRQ_CRC_ERR | sx126x.IRQ_HEADER_ERR):
            self.n_crc += 1
            return
        if irq & sx126x.IRQ_RX_DONE:
            data, rssi, snr = self.radio.read_packet()
            self._on_packet(data, rssi, snr, now)

    def _on_packet(self, data, rssi, snr, now):
        if len(data) < HDR_LEN or data[0] != self.cfg.LORA_NET_ID or data[1] & _FLAG_DRONE:
            self.n_foreign += 1
            return
        seq = data[2]
        if self.last_seq is not None:
            gap = (seq - self.last_seq - 1) & 0xFF
            if gap < 128:
                self.n_lost += gap
        self.last_seq = seq
        self.n_rx += 1
        self.rssi, self.snr = rssi, snr
        self.peer_rssi = -data[3] if data[3] else None
        self.peer_snr = struct.unpack("b", data[4:5])[0] if data[3] else None
        self.last_rx = now
        payload = data[HDR_LEN:]
        if payload:
            self.uart.write(payload)
            self.bytes_down += len(payload)
        if self.led:
            self.led(1)
            self.led_off = time.ticks_add(now, 30)

    def _schedule(self, now):
        if self.tx_busy or time.ticks_diff(now, self.next_tx) < 0:
            return
        # Don't step on a ground reply that is still arriving.
        if self.radio.rx_in_progress():
            if self.defer_start is None:
                self.defer_start = now
            if time.ticks_diff(now, self.defer_start) < self.defer_ms:
                return
        self.defer_start = None
        interval = self.cfg.DRONE_TX_INTERVAL_MS
        self.next_tx = time.ticks_add(self.next_tx, interval)
        if time.ticks_diff(self.next_tx, now) <= 0:
            self.next_tx = time.ticks_add(now, interval)
        self._send(self.queue.build(self.drone_len - HDR_LEN, now), now)

    def _send(self, payload, now):
        rssi = 0
        snr = 0
        if self.rssi is not None:
            rssi = max(1, min(255, int(-self.rssi)))
            snr = max(-128, min(127, int(self.snr)))
        pkt = bytes((self.cfg.LORA_NET_ID, _FLAG_DRONE, self.seq, rssi, snr & 0xFF)) + payload
        self.seq = (self.seq + 1) & 0xFF
        self.radio.start_tx(pkt)
        self.tx_busy = True
        self.tx_started = now
        self.tx_air = self.radio.airtime_ms(len(pkt))
        self.airtime_total += self.tx_air
        self.n_tx += 1
        self.bytes_up += len(payload)

    def _send_radio_status(self):
        # Sent to the FC so ArduPilot logs LoRa link quality (RAD). txbuf is
        # always reported as 100% free: ArduPilot slows every stream on the
        # port a low txbuf arrives on, and this port is the full-rate .tlog
        # feed -- the LoRa queue filling up must not throttle that.
        noise = None if self.rssi is None else self.rssi - self.snr
        remnoise = None if self.peer_rssi is None else self.peer_rssi - self.peer_snr
        self.uart.write(build_radio_status(
            self.status_seq, min(self.n_lost, 0xFFFF), sik_rssi(self.rssi),
            sik_rssi(self.peer_rssi), 100, sik_rssi(noise), sik_rssi(remnoise)))
        self.status_seq = (self.status_seq + 1) & 0xFF

    def stats(self):
        up = max(1, time.ticks_diff(time.ticks_ms(), self.t_start))
        fmt = lambda v: "-" if v is None else "%.0f" % v
        return ("tx %d rx %d lost %d crc %d | rssi %s snr %s | peer rssi %s snr %s | "
                "q %d drop %d | sent %dB recvd %dB | duty %.1f%%" % (
                    self.n_tx, self.n_rx, self.n_lost, self.n_crc,
                    fmt(self.rssi), fmt(self.snr), fmt(self.peer_rssi), fmt(self.peer_snr),
                    self.queue.pending(), self.queue.dropped, self.bytes_up,
                    self.bytes_down, self.airtime_total * 100 / up))
