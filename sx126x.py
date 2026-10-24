# Minimal non-blocking SX1262 / LLCC68 LoRa driver for MicroPython.
# BUSY is polled before every SPI command; TXEN/RXEN drive the module's RF
# switch. DIO1 signals TxDone / RxDone / Timeout / CRC and header errors.
import time
from machine import Pin, SPI

# Opcodes
_SET_STANDBY = 0x80
_SET_TX = 0x83
_SET_RX = 0x82
_SET_REGULATOR_MODE = 0x96
_CALIBRATE = 0x89
_CALIBRATE_IMAGE = 0x98
_SET_PA_CONFIG = 0x95
_SET_RX_TX_FALLBACK = 0x93
_WRITE_REGISTER = 0x0D
_READ_REGISTER = 0x1D
_WRITE_BUFFER = 0x0E
_READ_BUFFER = 0x1E
_SET_DIO_IRQ_PARAMS = 0x08
_GET_IRQ_STATUS = 0x12
_CLEAR_IRQ_STATUS = 0x02
_SET_DIO3_AS_TCXO = 0x97
_SET_RF_FREQUENCY = 0x86
_SET_PACKET_TYPE = 0x8A
_SET_TX_PARAMS = 0x8E
_SET_MODULATION_PARAMS = 0x8B
_SET_PACKET_PARAMS = 0x8C
_SET_BUFFER_BASE = 0x8F
_GET_RX_BUFFER_STATUS = 0x13
_GET_PACKET_STATUS = 0x14
_GET_RSSI_INST = 0x15
_GET_DEVICE_ERRORS = 0x17
_CLEAR_DEVICE_ERRORS = 0x07

# Registers
_REG_SYNC_WORD = 0x0740
_REG_TX_MODULATION = 0x0889
_REG_RX_GAIN = 0x08AC
_REG_TX_CLAMP = 0x08D8

# IRQ bits
IRQ_TX_DONE = 0x0001
IRQ_RX_DONE = 0x0002
IRQ_PREAMBLE = 0x0004
IRQ_HEADER_VALID = 0x0010
IRQ_HEADER_ERR = 0x0020
IRQ_CRC_ERR = 0x0040
IRQ_TIMEOUT = 0x0200
_IRQ_DIO1 = IRQ_TX_DONE | IRQ_RX_DONE | IRQ_HEADER_ERR | IRQ_CRC_ERR | IRQ_TIMEOUT
_IRQ_ALL = _IRQ_DIO1 | IRQ_PREAMBLE | IRQ_HEADER_VALID

_ERR_XOSC_START = 0x0020

_BW_CODES = {125: 0x04, 250: 0x05, 500: 0x06}
_TCXO_CODES = {1.6: 0, 1.7: 1, 1.8: 2, 2.2: 3, 2.4: 4, 2.7: 5, 3.0: 6, 3.3: 7}


class RadioError(Exception):
    pass


def airtime_ms(payload_len, sf, bw_khz, cr=1, preamble=12, crc=True, ldro=None):
    """LoRa time on air for an explicit-header packet (SX126x datasheet 6.1.4)."""
    if ldro is None:
        ldro = sf >= 11 and bw_khz <= 125
    tsym = (1 << sf) / bw_khz  # ms
    if sf < 7:
        num = 8 * payload_len + 16 * crc - 4 * sf + 20
        n_pre = preamble + 6.25
    else:
        num = 8 * payload_len + 16 * crc - 4 * sf + 28
        n_pre = preamble + 4.25
    den = 4 * (sf - 2 * ldro)
    n_payload = 8 + max(-(-num // den), 0) * (cr + 4)
    return (n_pre + n_payload) * tsym


class SX126x:
    def __init__(self, spi_id, sck, mosi, miso, nss, busy, dio1, nrst, txen, rxen,
                 baudrate=8_000_000):
        self._spi = SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                        sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self._nss = Pin(nss, Pin.OUT, value=1)
        self._busy = Pin(busy, Pin.IN)
        self.dio1 = Pin(dio1, Pin.IN)
        self._nrst = Pin(nrst, Pin.OUT, value=1)
        self._txen = Pin(txen, Pin.OUT, value=0)
        self._rxen = Pin(rxen, Pin.OUT, value=0)
        self._buf4 = bytearray(4)
        self.tcxo = None
        self._sf = 7
        self._bw = 250
        self._cr = 1
        self._preamble = 12
        self._ldro = False

    # ---- low level ----
    def _wait_busy(self, timeout_ms=100):
        t0 = time.ticks_ms()
        while self._busy.value():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                raise RadioError("BUSY stuck high")

    def _cmd(self, data, read_len=0):
        """Send a command; returns read_len bytes that follow the status byte."""
        self._wait_busy()
        buf = bytearray(data) + bytes(read_len + (1 if read_len else 0))
        self._nss(0)
        self._spi.write_readinto(buf, buf)
        self._nss(1)
        if read_len:
            return buf[len(data) + 1:]
        return None

    def _write_reg(self, addr, data):
        self._cmd(bytes((_WRITE_REGISTER, addr >> 8, addr & 0xFF)) + bytes(data))

    def _read_reg(self, addr, n=1):
        return self._cmd((_READ_REGISTER, addr >> 8, addr & 0xFF), n)

    def reset(self):
        self._nrst(0)
        time.sleep_ms(2)
        self._nrst(1)
        time.sleep_ms(10)
        self._wait_busy(500)

    def device_errors(self):
        b = self._cmd((_GET_DEVICE_ERRORS,), 2)
        return (b[0] << 8) | b[1]

    def _clear_device_errors(self):
        self._cmd((_CLEAR_DEVICE_ERRORS, 0, 0))

    def _calibrate(self, tcxo):
        self._cmd((_SET_STANDBY, 0x00))  # STDBY_RC
        self._clear_device_errors()
        if tcxo:
            # Delay in 15.625 us steps: 5 ms for the TCXO to settle.
            d = 5 * 64
            self._cmd((_SET_DIO3_AS_TCXO, _TCXO_CODES[tcxo], d >> 16, (d >> 8) & 0xFF, d & 0xFF))
        self._cmd((_CALIBRATE, 0x7F))
        time.sleep_ms(5)
        self._wait_busy(500)
        return self.device_errors()

    # ---- configuration ----
    def begin(self, freq_hz, sf=7, bw_khz=250, cr=1, preamble=12, power_dbm=10,
              sync_word=0x1424, tcxo="auto", dcdc=False):
        self.reset()
        sw = self._read_reg(_REG_SYNC_WORD, 2)
        if sw[0] not in (0x14, 0x34) or sw[1] not in (0x24, 0x44):
            raise RadioError("no SX126x found (sync word reads %02x%02x)" % (sw[0], sw[1]))

        if tcxo == "auto":
            err = self._calibrate(None)
            if err & _ERR_XOSC_START:
                self.reset()
                tcxo = 1.8
                err = self._calibrate(tcxo)
            else:
                tcxo = None
        else:
            err = self._calibrate(tcxo)
        self.tcxo = tcxo
        if err & ~0x0100:  # ignore PA ramp flag
            raise RadioError("calibration failed, device errors 0x%04x" % err)

        self._cmd((_SET_PACKET_TYPE, 0x01))  # LoRa
        self._cmd((_SET_REGULATOR_MODE, 0x01 if dcdc else 0x00))
        self._cmd((_SET_RX_TX_FALLBACK, 0x20))  # back to STDBY_RC
        self._cmd((_SET_BUFFER_BASE, 0x00, 0x00))

        # Image calibration for the 430-440 MHz band, then frequency.
        self._cmd((_CALIBRATE_IMAGE, 0x6B, 0x6F))
        self._wait_busy(500)
        frf = (freq_hz << 25) // 32_000_000
        self._cmd((_SET_RF_FREQUENCY, (frf >> 24) & 0xFF, (frf >> 16) & 0xFF,
                   (frf >> 8) & 0xFF, frf & 0xFF))

        # SX1262 high-power PA; SetTxParams then takes the power in dBm.
        self._cmd((_SET_PA_CONFIG, 0x04, 0x07, 0x00, 0x01))
        self.set_power(power_dbm)
        # Errata 15.2: better resistance to antenna mismatch.
        clamp = self._read_reg(_REG_TX_CLAMP)[0]
        self._write_reg(_REG_TX_CLAMP, (clamp | 0x1E,))

        self._sf, self._bw, self._cr, self._preamble = sf, bw_khz, cr, preamble
        self._ldro = sf >= 11 and bw_khz <= 125
        self._cmd((_SET_MODULATION_PARAMS, sf, _BW_CODES[bw_khz], cr, 1 if self._ldro else 0))
        # Errata 15.1: TX modulation quality at 500 kHz.
        mod = self._read_reg(_REG_TX_MODULATION)[0]
        self._write_reg(_REG_TX_MODULATION, (mod & 0xFB if bw_khz == 500 else mod | 0x04,))
        self._set_packet_params(255)
        self._write_reg(_REG_SYNC_WORD, (sync_word >> 8, sync_word & 0xFF))
        self._write_reg(_REG_RX_GAIN, (0x96,))  # boosted RX gain

        self._cmd((_SET_DIO_IRQ_PARAMS, _IRQ_ALL >> 8, _IRQ_ALL & 0xFF,
                   _IRQ_DIO1 >> 8, _IRQ_DIO1 & 0xFF, 0, 0, 0, 0))
        self.clear_irq()

    def set_power(self, dbm):
        dbm = max(-9, min(22, int(dbm)))
        self._cmd((_SET_TX_PARAMS, dbm & 0xFF, 0x04))  # 200 us ramp

    def _set_packet_params(self, length):
        p = self._preamble
        self._cmd((_SET_PACKET_PARAMS, p >> 8, p & 0xFF, 0x00, length, 0x01, 0x00))

    def airtime_ms(self, length):
        return airtime_ms(length, self._sf, self._bw, self._cr, self._preamble, True, self._ldro)

    # ---- operation ----
    def irq_status(self):
        b = self._cmd((_GET_IRQ_STATUS,), 2)
        return (b[0] << 8) | b[1]

    def clear_irq(self, mask=0xFFFF):
        self._cmd((_CLEAR_IRQ_STATUS, mask >> 8, mask & 0xFF))

    def start_rx(self):
        """Continuous receive."""
        self._cmd((_SET_STANDBY, 0x00))
        self._set_packet_params(255)
        self.clear_irq()
        self._txen(0)
        self._rxen(1)
        self._cmd((_SET_RX, 0xFF, 0xFF, 0xFF))

    def start_tx(self, data):
        """Begin transmitting; completion is signalled by IRQ_TX_DONE on DIO1."""
        n = len(data)
        if n > 255:
            raise ValueError("packet too long")
        self._cmd((_SET_STANDBY, 0x00))
        self._cmd(bytes((_WRITE_BUFFER, 0x00)) + bytes(data))
        self._set_packet_params(n)
        self.clear_irq()
        self._rxen(0)
        self._txen(1)
        # Hardware timeout at twice the expected airtime (15.625 us steps).
        t = min(int(self.airtime_ms(n) * 2 * 64) + 640, 0xFFFFFF)
        self._cmd((_SET_TX, t >> 16, (t >> 8) & 0xFF, t & 0xFF))

    def standby(self):
        self._cmd((_SET_STANDBY, 0x00))
        self._txen(0)
        self._rxen(0)

    def rx_in_progress(self):
        """True while a packet header has been seen but RxDone has not fired."""
        irq = self.irq_status()
        return bool(irq & IRQ_HEADER_VALID) and not (irq & _IRQ_DIO1)

    def read_packet(self):
        """Returns (payload, rssi_dbm, snr_db) for the packet just received."""
        b = self._cmd((_GET_RX_BUFFER_STATUS,), 2)
        n, start = b[0], b[1]
        data = self._cmd((_READ_BUFFER, start), n) if n else b""
        s = self._cmd((_GET_PACKET_STATUS,), 3)
        rssi = -s[0] / 2
        snr = (s[1] - 256 if s[1] > 127 else s[1]) / 4
        return bytes(data), rssi, snr

    def rssi_inst(self):
        return -self._cmd((_GET_RSSI_INST,), 1)[0] / 2
