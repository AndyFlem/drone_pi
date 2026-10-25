# st7789.py -- minimal ST7789 driver for the 1.3" 240x240 IPS panel
# (ZJY-IPS130 V2.0). Text-row oriented: there is no full-screen framebuffer
# (240x240 RGB565 would be 115 KB of heap); each row of text is drawn into a
# small band with the built-in 8x8 font, pixel-doubled, and pushed straight
# to the panel's RAM window.
#
# The 7-pin board has no CS pin (CS is tied low on the module), so it needs
# SPI mode 3 (polarity=1, phase=1) and a bus of its own -- it would latch
# any other device's traffic as display data.

import time
from machine import Pin
from micropython import const
import framebuf
import micropython

_SWRESET = const(0x01)
_SLPOUT = const(0x11)
_NORON = const(0x13)
_INVON = const(0x21)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)

# (MADCTL, x offset, y offset) per rotation. The controller has 240x320 of
# RAM; a 240x240 panel sits at the top of it, so the 180/270 degree
# orientations have to skip the unused 80 rows.
_ROTATIONS = (
    (0x00, 0, 0),
    (0x60, 0, 0),
    (0xC0, 0, 80),
    (0xA0, 80, 0),
)


def color565(r, g, b):
    # framebuf stores RGB565 little-endian but the panel wants big-endian,
    # so colours are pre-swapped and buffers can be sent as-is.
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


BLACK = color565(0, 0, 0)
WHITE = color565(255, 255, 255)
RED = color565(255, 0, 0)
GREEN = color565(0, 255, 0)
YELLOW = color565(255, 255, 0)
CYAN = color565(0, 255, 255)
GREY = color565(128, 128, 128)


@micropython.viper
def _upscale(src: ptr16, dst: ptr16, w: int, h: int, s: int):
    dw = w * s
    di = 0
    for y in range(h):
        row = y * w
        start = di
        for x in range(w):
            c = src[row + x]
            for _ in range(s):
                dst[di] = c
                di += 1
        for _ in range(s - 1):
            for i in range(dw):
                dst[di] = dst[start + i]
                di += 1


class ST7789:
    def __init__(self, spi, dc, rst, cs=None, bl=None, width=240, height=240,
                 rotation=0, scale=2):
        self.spi = spi
        self.dc = dc
        self.rst = rst
        self.cs = cs
        self.bl = bl
        self.width = width
        self.height = height
        self.scale = scale
        self.cols = width // (8 * scale)  # characters per text row
        self.row_h = 8 * scale
        self._madctl, self._xoff, self._yoff = _ROTATIONS[rotation & 3]

        self.dc.init(Pin.OUT, value=0)
        self.rst.init(Pin.OUT, value=1)
        if self.cs is not None:
            self.cs.init(Pin.OUT, value=1)

        # Band: one text row at 1x, then pixel-doubled into _out for sending.
        bw = width // scale
        self._band_buf = bytearray(bw * 8 * 2)
        self._band = framebuf.FrameBuffer(self._band_buf, bw, 8, framebuf.RGB565)
        self._out = bytearray(width * self.row_h * 2)

        self._init_panel()
        self.fill(BLACK)
        if self.bl is not None:
            self.bl.init(Pin.OUT, value=1)

    def _cmd(self, cmd, data=None):
        if self.cs is not None:
            self.cs(0)
        self.dc(0)
        self.spi.write(bytes((cmd,)))
        if data is not None:
            self.dc(1)
            self.spi.write(data)
        if self.cs is not None:
            self.cs(1)

    def _init_panel(self):
        self.rst(1)
        time.sleep_ms(5)
        self.rst(0)
        time.sleep_ms(20)
        self.rst(1)
        time.sleep_ms(150)
        self._cmd(_SWRESET)
        time.sleep_ms(150)
        self._cmd(_SLPOUT)
        time.sleep_ms(120)
        self._cmd(_COLMOD, b"\x55")  # 16 bit/pixel RGB565
        self._cmd(_MADCTL, bytes((self._madctl,)))
        self._cmd(_INVON)  # IPS panels are wired inverted; without this colours come out negative
        self._cmd(_NORON)
        time.sleep_ms(10)
        self._cmd(_DISPON)
        time.sleep_ms(10)

    def _window(self, x, y, w, h):
        x0 = x + self._xoff
        y0 = y + self._yoff
        x1 = x0 + w - 1
        y1 = y0 + h - 1
        self._cmd(_CASET, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._cmd(_RASET, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))

    def blit(self, buf, x, y, w, h):
        self._window(x, y, w, h)
        self._cmd(_RAMWR, buf)

    def fill(self, color):
        # Reuses the row buffer as a solid-colour strip.
        out = self._out
        b0 = color & 0xFF
        b1 = color >> 8
        for i in range(0, len(out), 2):
            out[i] = b0
            out[i + 1] = b1
        for y in range(0, self.height, self.row_h):
            self.blit(out, 0, y, self.width, min(self.row_h, self.height - y))

    def text_row(self, y, parts, bg=BLACK):
        # Draws one full-width row of text at pixel row y. parts is a list of
        # (column, text, colour); the whole row is repainted with bg, so
        # stale characters from the previous render are cleared.
        b = self._band
        b.fill(bg)
        for col, text, fg in parts:
            b.text(text, col * 8, 0, fg)
        if self.scale == 1:
            self.blit(self._band_buf, 0, y, self.width, 8)
        else:
            _upscale(self._band_buf, self._out, self.width // self.scale, 8, self.scale)
            self.blit(self._out, 0, y, self.width, self.row_h)

    def backlight(self, on):
        if self.bl is not None:
            self.bl(1 if on else 0)
