# Longrange Drone — Build Specification & Performance Estimate

8-inch long-range cinematic quadcopter. **All-up weight: 1750 g** (includes onboard AKASO EK7000 4K action-cam payload).

Component specs looked up from manufacturer/retailer listings (Aug 2026). Performance figures derived from T-Motor's official V2808 1300 KV bench data.

---

# 1. Configuration Summary (confirmed)
- **Firmware:** ArduPilot — **Copter** (running on the H743 FC)
- **Motors:** T-Motor Velox V2808 **1300 KV**
- **Navigation:** YEHEI M10Q GNSS + compass (u-blox M10 / QMC5883L) — enables GPS position hold, waypoint/auto missions, RTL
- **FPV video:** **Analog** — RushFPV Tank Tiny VTX + RunCam Robin 3 V2. DJI O4 not fitted (stack supports it if changed later).
- **Telemetry logging:** Raspberry Pi Pico 2 W + microSD, capturing MAVLink telemetry via FC UART3; 0.96" OLED for live readout. See §5.
- **Payload:** AKASO EK7000 4K30FPS action cam, 130 g with mount, included in AUW.

## UART assignments (H743 FC)
| UART | Connected to | Notes |
|---|---|---|
| UART2 | ExpressLRS receiver (RadioMaster RP4TD) | RC in via CRSF |
| UART3 | Telemetry logger (Pico 2 W) | MAVLink2 out to Pico (TX3/RX3) |
| UART4 | GPS (YEHEI M10Q) | GNSS serial; compass on I2C |
| UART6 | ESC (GOKU G55M) | ESC telemetry serial |
| UART8 | VTX (RushFPV Tank Tiny) | SmartAudio control |

(Spare UARTs remaining: UART1, UART7.)

---

# 2. Components

## Frame — UMT LX8 V2 8-Inch Long Range FPV Carbon Frame
- Type: X-type, 3K carbon fiber
- Wheelbase: 367 mm
- Footprint: ~230.4 × 278.5 mm
- Arm thickness: 6.0 mm
- Plate thickness: bottom 3.0 mm / middle 3.0 mm / top 2.0 mm / connecting 2.0 mm
- Prop compatibility: 8-inch
- Supports analog and digital VTX systems
- Stack mount: 30×30 (per this build's stack); frame weight not listed by retailer

## Battery — GNB (Gaoneng) 8000 mAh 6S 10C Li-ion
- Capacity: 8000 mAh, 22.2 V nominal (6S)
- Configuration: 6S2P, Samsung 21700 40T Li-ion cells
- Discharge: 10C → ~80 A max continuous
- Charge rate: 1C
- Weight: 904 g (±25 g)
- Dimensions: 44 × 81 × 130 mm (H×W×L)
- Connector: XT60
- Model: GNB80006S10R
- Note: battery alone is ~52% of the 1750 g AUW

## Motors — T-Motor Velox V2808 Cinematic ×4 — **1300 KV** (confirmed)
- Stator: 2808 (28 mm), 12N14P
- KV: **1300 KV** (this build)
- Weight: ~60.5–61.1 g each (~242 g for 4)
- Shaft: 4 mm
- Voltage: 16.8–25.2 V (up to 6S)
- Max power (per motor): ~1512 W @ 1300 KV
- Idle current: ~1.19 A
- Burst current: ~62.4 A @ 1300 KV
- Rated for 4–8" props

## Stack — Flywoo GOKU H743 PRO 55A 32-Bit 128K 30×30 (O4 Plug&Play)
**Flight controller:**
- MCU: STM32H743VIH6, 480 MHz Cortex-M7
- IMU: dual ICM42688P gyros
- Baro: DPS310 / SPL06, OSD: AT7456E
- Blackbox: 512 MB
- 7× UART, 2× I2C, 12 PWM outputs, dual-camera switching
- Input: 2–6S (7.4–26 V); BEC: 10 V/3 A + 5 V/3 A
- Mount: 30×30 mm (M3); FC 36.5 × 36.5 × 8.45 mm, 9.9 g
- **Firmware: ArduPilot Copter** (FC also supports Betaflight / INAV)
- Configured for DJI O4 / O4 Pro air unit (plug & play) — O4 not fitted; running analog
- UART usage: UART2 → ELRS RX, UART3 → Pico logger, UART4 → GPS, UART6 → ESC telem, UART8 → VTX SmartAudio (see §1)

**ESC (GOKU G55M AM32):**
- 55 A continuous 4-in-1, 3–6S
- Firmware: AM32 (AT32F421), DShot300/600
- PWM 24k–128k, weight 15 g

## GNSS / Compass — YEHEI M10Q GPS Module
YEHEI-branded M10Q-5883-class module (u-blox M10 reference design). Provides GPS + magnetometer for ArduPilot Copter navigation.
- GNSS: u-blox M10 series; concurrent GPS + GLONASS + Galileo + BeiDou
- Compass/mag: QMC5883L
- Update rate: up to 5 Hz (UBX); 1 Hz NMEA
- Interface: UART (GNSS) on **UART4** + I2C (compass), 9600 baud default
- Input: 4–9 V; ~13 mA draw
- Antenna: 15×15 mm ceramic patch
- PPS status LED
- Size: ~20 × 20 × 12.4 mm; ~8 g
- Note: specs are for the standard M10Q-5883 reference design; verify wiring/pinout against the actual YEHEI unit before install

## Props — HQProp 8×3.7×3 (Grey)
- 8" diameter, 3.7" pitch, 3 blades (tri-blade)
- Material: polycarbonate
- Weight: ~12 g each
- Hub: 15.5 mm dia, 8.5 mm thick; 5 mm shaft bore
- Supplied as CW/CCW sets

## Receiver — RadioMaster RP4TD ExpressLRS 2.4GHz True Diversity
- 2.4 GHz, ExpressLRS (ships v3.3.0), mLRS compatible
- True diversity, dual SX1281 RF chips, ESP32 MCU
- Antennas: 2× 65 mm T-antenna
- Output: CRSF (on **UART2**; UART pads available)
- Telemetry power: max 2× 100 mW; up to 500 Hz / F1000 Hz; Gemini mode supported
- Input: 4.5–12 V; weight 1.4 g (excl. antennas); 23.7 × 16.3 × 4.0 mm
- Built-in WiFi for firmware/WebUI

## FPV Video System — Analog (current final config)

### VTX — RushFPV Tank Tiny (Analog 5.8 GHz)
- 5.8 GHz, 48 CH (37 CH US version)
- Power: PIT / 25 / 100 / 200 / 350 mW (max)
- Input: 5 V
- Control: TBS SmartAudio (on **UART8**)
- Antenna: U.FL
- Weight: 1.4 g

### FPV Camera — RunCam Robin 3 V2 1200TVL Analog
- Sensor: 1/3" CMOS, 1200TVL
- Aspect: 4:3; FOV D150° / H120° / V87°
- Format: NTSC/PAL selectable; rolling shutter; WDR; color/BW
- Input: 5–23 V (120 mA @5V)
- Size: 19 × 19 × 19 mm (micro/19mm mount), ABS housing
- Weight: 5.3 g
- Menu via cable control; mirror/flip available

## Payload — AKASO EK7000 4K30FPS Action Camera
- Onboard HD recording camera (separate from the analog FPV feed)
- Records 4K @ 30 fps
- Weight with mount: 130 g
- Already included in the 1750 g all-up weight

---

# 3. Weight Tally
| Component | Weight |
|---|---|
| Battery (GNB 8000 6S) | 904 g |
| Motors ×4 | ~242 g |
| Stack (FC+ESC) | ~25 g |
| Props ×4 | ~48 g |
| GNSS/compass (YEHEI M10Q) | ~8 g |
| RX + VTX + FPV cam | ~8 g |
| Telemetry logger (Pico 2 W + SD + OLED + wiring) | ~18 g |
| AKASO EK7000 4K (payload, w/ mount) | 130 g |
| **Subtotal of above** | **~1383 g** |
| Frame + hardware + wiring + antennas (balance) | **~367 g** |
| **All-up weight** | **1750 g** |

Battery is the dominant single mass (~52% of AUW). The balance is the frame, screws, wiring, connectors, and antennas — consistent with an 8" 6 mm-arm carbon frame build.

---

# 4. Performance Estimate

**Basis:** T-Motor's official V2808 1300 KV bench data at 6S (25.2→24.2 V) with the T-HOBBY T7546-3 (7.5×4.6 tri) prop. Our prop is the HQProp 8×3.7×3 — slightly larger diameter, lower pitch. In hover the larger disc makes the 8×3.7 comparable-to-slightly-more-efficient; peak top-end thrust may be a touch lower than the 7.5" figures. Treat numbers as ±10–15%.

## Manufacturer bench data (per motor, 6S)
| Throttle | Thrust | Current | Power | Eff |
|---|---|---|---|---|
| 20% | 245 g | 2.2 A | 55 W | 4.44 g/W |
| 40% | 778 g | 8.9 A | 223 W | 3.49 g/W |
| 60% | 1510 g | 20.7 A | 514 W | 2.93 g/W |
| 80% | 2298 g | 40.0 A | 982 W | 2.34 g/W |
| 100% | 2910 g | 62.4 A | 1512 W | 1.92 g/W |

## Thrust-to-weight
- Max static thrust (4 motors): **~11.6 kg**
- **TWR ≈ 6.6 : 1** at 1750 g
- Very high authority — not thrust-limited at current weight.

## Hover
- Hover thrust needed: 437 g/motor → **~27% throttle**
- Hover power: ~460–475 W (motors) + ~12 W avionics
- **Hover current ≈ 19 A** (fresh, 25 V) to **~21–23 A** (nominal/low, 22–21 V)
- Well within the battery's 80 A (10C) limit — huge margin in hover.

## Flight time (8000 mAh Li-ion)
- **Hover endurance: ~18–20 min** (usable 80–90% of pack, ~21 A hover)
- **Efficient forward cruise: ~25–32 min** (cruise draws ~0.6–0.75× hover current thanks to translational lift)
- Li-ion tolerates deeper discharge than LiPo, so the upper end is realistic if flown gently to ~3.3 V/cell.

## Payload / load-carry capacity (additional, on top of 1750 g)
| Criterion | Max AUW | Extra payload | Notes |
|---|---|---|---|
| Comfortable (hover ≤ 50% throttle) | ~4.6 kg | **~2.8 kg** | Keeps agility + control headroom |
| Battery-limited (80 A cont. @ hover) | ~5.3 kg | ~3.5 kg | Hover alone near C-rating; no maneuver margin |
| Absolute (TWR 2:1) | ~5.8 kg | ~4.1 kg | Sluggish, hot, minimal safety margin — not advised |

**Recommended working payload: up to ~1.5–2 kg extra** for safe, efficient, maneuverable flight with battery/thermal margin.

## Takeaways
- Motors are heavily over-specced for 1750 g → smooth, cool, efficient cruising and excellent wind penetration.
- The **battery is the limiting factor**, both for endurance (52% of AUW) and for heavy-lift (10C ceiling), not the motors.
- Sweet spot: long-range/cinematic cruise at low throttle, ~25–30 min real-world mixed flights.
- ArduPilot Copter + the M10Q GNSS/compass suit this mission well — GPS position hold, waypoint/auto missions, RTL, and smooth autonomous cruise all play to the airframe's long-range strengths.

---

# 5. Telemetry Logging Subsystem

Independent, removable telemetry logger tapping the FC's MAVLink stream. Complements (does not replace) the FC's onboard 512 MB `.bin` dataflash logging. The FC streams MAVLink2 out **UART3 (TX3/RX3)**; the Pico logs it to microSD (recommended: QGC-compatible `.tlog` format), drives a 0.96" OLED for live status, and rebroadcasts the stream over its onboard WiFi (AP mode, UDP :14550) to a phone/tablet GCS.

## Parts
- **Raspberry Pi Pico 2 W** (RP2350, 3.3 V logic, WiFi) — ~7 g
- **microSD adapter — mini 6-pin SPI type, 3.3 V ONLY** (no onboard regulator or level shifter; silkscreen pins: 3V3 / CS / MOSI / CLK / MISO / GND). Power from Pico 3V3 — **do NOT feed 5 V.** — ~1 g
- **0.96" OLED, SSD1306, 128×64, I2C** (JMD0.96D-1; pins GND/VCC/SCL/SDA; addr 0x3C default) — ~5 g

## Complete wiring

**FC ↔ Pico (UART, MAVLink2)** — FC pads TX3 / RX3 (UART3). Note the TX→RX cross:
| FC (H743 UART3) | Pico | Pico phys pin |
|---|---|---|
| TX3 | GP1 (UART0 RX) | 2 |
| RX3 | GP0 (UART0 TX) | 1 |
| GND | GND | 3/8/… |

**Pico ↔ microSD adapter (SPI0)** — labels as printed on the SD board:
| SD board label | Pico | Pico phys pin |
|---|---|---|
| CLK | GP2 (SPI0 SCK) | 4 |
| MOSI | GP3 (SPI0 TX) | 5 |
| MISO | GP4 (SPI0 RX) | 6 |
| CS | GP5 | 7 |
| 3V3 | 3V3(OUT) | 36 |
| GND | GND | 8 |

**Pico ↔ OLED (I2C1):**
| OLED | Pico | Pico phys pin |
|---|---|---|
| SDA | GP6 | 9 |
| SCL | GP7 | 10 |
| VCC | 3V3(OUT) | 36 |
| GND | GND | 8 |

**Pico ↔ LoRa radio (SPI1, DX-LR30-433M22S on DX-PJ27 breakout)**. Details in [radio-notes.md](radio-notes.md):
| Radio | Pico | Pico phys pin |
|---|---|---|
| SCK | GP10 (SPI1 SCK) | 14 |
| MOSI | GP11 (SPI1 TX) | 15 |
| MISO | GP12 (SPI1 RX) | 16 |
| NSS | GP13 | 17 |
| BUSY | GP14 | 19 |
| DIO1 | GP15 | 20 |
| NRST | GP16 | 21 |
| TXEN | GP17 | 22 |
| RXEN | GP18 | 24 |
| DIO2 | not connected | — |
| VCC | 3.3 V from a dedicated LDO (not 3V3(OUT)) | — |
| GND | GND | 18 |

**Power tree:**
- FC **5 V BEC → Pico VSYS (pin 39)**; FC **GND → Pico GND** (common ground)
- Pico **3V3(OUT) (pin 36) → SD 3V3 and OLED VCC** (both 3.3 V devices)
- FC **5 V BEC → AMS1117-3.3 (or AP2112K-3.3) → LoRa radio VCC**. The radio draws about 120 mA in TX bursts, so it is kept off the Pico's 3V3(OUT). Fit 100 µF + 0.1 µF at the radio.
- All logic 3.3 V end-to-end — no level shifters required. **Never feed the SD adapter 5 V** (this mini type has no regulator).

## ArduPilot config (FC side, on UART3's serial)
- `SERIALx_PROTOCOL = 2` (MAVLink2) — SERIALx = whichever SERIAL number ArduPilot maps to UART3 on this target
- `SERIALx_BAUD = 921` (921600; 115 also fine)
- Set the port's `SRx_*` stream rates (ATTITUDE, POSITION, EXTRA1/2/3, RAW_SENS, RC_CHAN, EXT_STAT) to desired Hz. Pico sending a heartbeat helps ArduPilot start streaming.

## Pico firmware approach
- Read MAVLink2 frames off UART0 (frames start 0xFD, self-describe length).
- Write **`.tlog`**: per packet = 8-byte big-endian µs timestamp (`time_us_64()`) + raw bytes → opens directly in MAVExplorer / QGroundControl / pymavlink (no custom decoder).
- Buffer in RAM, `f_sync` every 1–2 s (power-loss safety; optional supercap).
- OLED: show live GPS fix/sats, battery V, alt, mode, log status.
- WiFi AP + UDP MAVLink bridge (`wifi_telem.py`): Pico hosts its own access
  point (SSID/password in `config.py`, default IP 192.168.4.1) and relays
  every FC frame to the AP subnet broadcast address on UDP :14550 as it's
  read, so QGroundControl's UDP auto-connect (which listens passively and
  adopts whichever sender it first hears from) picks it up with no
  handshake. GCS-originated UDP datagrams on the same port are forwarded
  byte-for-byte back to the FC over UART, so it's a bidirectional bridge
  (telemetry out, commands/params in) — not just one-way re-broadcast.
- 433 MHz LoRa backup link (`lora_link.py` + `sx126x.py`, see
  [radio-notes.md](radio-notes.md)): a light message set (heartbeat, attitude,
  position, GPS, battery, plus params/mission/ACK/STATUSTEXT) goes to a
  separate ground station within a 10 % duty cycle at 10 mW. GCS frames from
  the ground station are forwarded to the FC over UART.
- Debug/flight-event log (`pico_log.py` + `sdlog.TextLogWriter`): every REPL
  debug line (init progress, wifi/AP status) plus flight-summary events
  (mode changes, PreArm failures, ready-to-arm, armed/disarmed, a
  position+attitude line every 5 s) also get appended to a plaintext
  `logNNNN.txt` alongside the matching `logNNNN.tlog` on the SD card, when
  the card is available.
- MicroPython is sufficient at telemetry rates; C/Pico-SDK + FatFs only if pushing very high rates.
- SD init note: the mini adapter has no card-detect; SPI clock init low (~400 kHz) then raise to ~12–25 MHz after mount. Keep SPI wires short — bare adapters aren't great at high clock over long leads.

## To confirm on build
- UART3 (TX3/RX3) broken out on the GOKU H743 PRO — confirmed as the chosen port (spares: UART1, UART7).
- Which ArduPilot SERIALx index maps to UART3 on this board target (set PROTOCOL/BAUD/stream rates there).
- OLED address 0x3C (try 0x3D if blank).
- SD adapter: confirmed **3.3 V only** — powered from Pico 3V3(OUT), never 5 V. Use a good-quality card; format FAT32/exFAT.