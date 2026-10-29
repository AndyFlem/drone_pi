# Longrange Drone — Build Specification & Performance Estimate

8-inch long-range cinematic quadcopter. **All-up weight: 1750 g** (includes onboard AKASO EK7000 Pro 4K action-cam payload; logger additions since then — LoRa radio, LDO, IPS display — not yet re-weighed).

Component specs looked up from manufacturer/retailer listings (Aug 2026). Performance figures derived from T-Motor's official V2808 1300 KV bench data, superseded where noted by measured flight-log data. ArduPilot values in this document reflect the parameter dump `9inch.param` (28 Oct 2026); Pico logger details reflect the `drone_pi` repo as of 28 Oct 2026.

---

# 1. Configuration Summary (confirmed)
- **Firmware:** ArduPilot — **Copter** (running on the H743 FC)
- **Motors:** T-Motor Velox V2808 **1300 KV**
- **Navigation:** HGLRC M100-5883 GNSS + compass (u-blox M10 / **QMC5883P**) — enables GPS position hold, waypoint/auto missions, RTL. *Replaced the YEHEI M10Q after a crash (Oct 2026); compass now on I2C2 because the FC's SCL1 pad was damaged.*
- **FPV video:** **Analog** — RushFPV Tank Tiny VTX + RunCam Robin 3 V2. DJI O4 not fitted (stack supports it if changed later).
- **Telemetry logging / companion:** Raspberry Pi Pico 2 W on FC UART3 — microSD `.tlog` logging, 1.3" ST7789 IPS status display, WiFi MAVLink bridge, 433 MHz LoRa backup telemetry link, and RC-triggered action-cam control. See §5 and §6.
- **Payload:** AKASO EK7000 **Pro** 4K30FPS action cam (upgraded from the standard EK7000, Oct 2026), ~130 g with mount, included in AUW.

## UART assignments (H743 FC)
| UART | ArduPilot port | Connected to | Params |
|---|---|---|---|
| USB | SERIAL0 | GCS (USB) | `SERIAL0_PROTOCOL = 2`, 115200 |
| UART1 | SERIAL1 | — spare | `SERIAL1_PROTOCOL = -1` |
| UART2 | SERIAL2 | ExpressLRS receiver (RadioMaster RP4TD) | `SERIAL2_PROTOCOL = 23` (RCIN, CRSF) |
| UART3 | SERIAL3 | Pico 2 W logger | `SERIAL3_PROTOCOL = 2` (MAVLink2), `SERIAL3_BAUD = 921` |
| UART4 | SERIAL4 | GPS (HGLRC M100-5883) | `SERIAL4_PROTOCOL = 5` (GPS), `SERIAL4_BAUD = 230`; compass on **I2C2** |
| UART6 | SERIAL6 | ESC (GOKU G55M) | `SERIAL6_PROTOCOL = 16` (ESC telemetry), 115200 |
| UART7 | SERIAL7 | Reserved for rangefinder (not fitted) | `SERIAL7_PROTOCOL = 9` (Rangefinder), 115200 — `RNGFND1_TYPE = 0`, so inactive |
| UART8 | SERIAL8 | VTX (RushFPV Tank Tiny) | `SERIAL8_PROTOCOL = 37` (SmartAudio; the driver sets its own baud, `SERIAL8_BAUD = 57` is unused) |

SERIALn maps directly to UARTn on this target (confirmed: the Pico link is live on SERIAL3). Spare UART remaining: UART1 (UART7 earmarked for a rangefinder).

## I2C assignments (H743 FC)
ArduPilot hwdef `FlywooH743Pro`: `I2C_ORDER I2C1 I2C2` → **bus 0 = I2C1, bus 1 = I2C2**. All buses are probed for external compasses (`AP_COMPASS_PROBING_ENABLED`, `HAL_I2C_INTERNAL_MASK 0`).

| Bus | Pads | Devices | Notes |
|---|---|---|---|
| I2C1 (bus 0) | SDA1 / SCL1 | — | **Out of service — SCL1 pad damaged in crash.** Do not use. |
| I2C2 (bus 1) | SDA2 / SCL2 | Onboard SPL06 baro @ 0x76 (internal, `BARO1_DEVID = 816649`) + **external QMC5883P compass @ 0x2C** | Shared with the baro. No address clash. A short/fault on the compass leads can also take down the baro. |

## RC channels and flight modes
| Channel | Function | Params |
|---|---|---|
| 1–4 | Roll / Pitch (reversed) / Throttle / Yaw | `RCMAP_*` default, `RC2_REVERSED = 1` |
| 5 | Arm / emergency motor stop | `RC5_OPTION = 165` |
| 6 | Flight mode | `FLTMODE_CH = 6` |
| 7 | Action-cam record toggle (read by the Pico, not the FC) | `CAMERA_VIDEO_RC_CHAN = 7` |
| 8 | RTL | `RC8_OPTION = 4` |
| 9 | Action-cam photo (read by the Pico, not the FC) | `CAMERA_PHOTO_RC_CHAN = 9` |

Flight modes: `FLTMODE1 = 2` AltHold, `FLTMODE2/3/5 = 0` Stabilize, `FLTMODE4 = 5` **Loiter**, `FLTMODE6 = 3` **Auto**.

## Arming / GPS requirement
**`ARMING_NEED_LOC = 1` is now set**, so the vehicle refuses to arm in any mode until it has an absolute position. That guarantees home is set at takeoff, which the RTL failsafes (`FS_THR_ENABLE = 1`, `BATT_FS_LOW_ACT = 2`, RC8 RTL switch) depend on. `ARMING_SKIPCHK = 0` (no checks skipped). For indoor/bench testing without a fix, set `ARMING_NEED_LOC` back to 0 temporarily and restore it before flying.

## Failsafes and safety settings
| Item | Setting |
|---|---|
| RC (throttle) failsafe | `FS_THR_ENABLE = 1` (RTL), `FS_THR_VALUE = 975`, `RC_FS_TIMEOUT = 1` s |
| Battery low | `BATT_LOW_VOLT = 19.0 V`, `BATT_LOW_TIMER = 15` s → `BATT_FS_LOW_ACT = 2` (RTL) |
| Battery critical | `BATT_CRT_VOLT = 18.0 V` → `BATT_FS_CRT_ACT = 1` (Land) |
| Arming voltage | `BATT_ARM_VOLT = 18.1 V` |
| GCS failsafe | `FS_GCS_ENABLE = 0` (off — the WiFi/LoRa links are not relied on for control) |
| EKF failsafe | `FS_EKF_ACTION = 1` (Land), `FS_EKF_THRESH = 0.8` |
| Dead reckoning | `FS_DR_ENABLE = 2`, `FS_DR_TIMEOUT = 30` s |
| Vibration / crash | `FS_VIBE_ENABLE = 1`, `FS_CRASH_CHECK = 1` |
| RTL | `RTL_ALT_M = 17 m`, `RTL_LOIT_TIME = 5 s`, `RTL_CONE_SLOPE = 3` |
| Geofence | `FENCE_ENABLE = 0` (configured but off): `FENCE_TYPE = 7`, `FENCE_RADIUS = 150 m`, `FENCE_ALT_MAX = 120 m`, `FENCE_ACTION = 3` (RTL) |
| Terrain | `TERRAIN_ENABLE = 1` (100 m grid) |

---

# 2. Components

## Frame — UMT LX8 V2 8-Inch Long Range FPV Carbon Frame
- Type: X-type, 3K carbon fiber (`FRAME_CLASS = 1` Quad, `FRAME_TYPE = 1` X)
- Wheelbase: 367 mm
- Footprint: ~230.4 × 278.5 mm
- Arm thickness: 6.0 mm
- Plate thickness: bottom 3.0 mm / middle 3.0 mm / top 2.0 mm / connecting 2.0 mm
- Prop compatibility: 8-inch
- Supports analog and digital VTX systems
- Stack mount: 30×30 (per this build's stack); frame weight not listed by retailer

## Battery — GNB (Gaoneng) 8000 mAh 6S 10C Li-ion
- Capacity: 8000 mAh, 22.2 V nominal (6S) — `BATT_CAPACITY = 8000`
- Configuration: 6S2P, Samsung 21700 40T Li-ion cells
- Discharge: 10C → ~80 A max continuous
- Charge rate: 1C
- Weight: 904 g (±25 g)
- Dimensions: 44 × 81 × 130 mm (H×W×L)
- Connector: XT60
- Model: GNB80006S10R
- Note: battery alone is ~52% of the 1750 g AUW
- Monitoring: `BATT_MONITOR = 4` (analog V + I), `BATT_VOLT_MULT = 11.0`, `BATT_AMP_PERVLT = 9`, `BATT_AMP_OFFSET = 0.9` (calibrated). Motor voltage compensation `MOT_BAT_VOLT_MAX = 25.2`, `MOT_BAT_VOLT_MIN = 19.8`.

## Motors — T-Motor Velox V2808 Cinematic ×4 — **1300 KV** (confirmed)
- Stator: 2808 (28 mm), 12N14P (`SERVO_BLH_POLES = 14`)
- KV: **1300 KV** (this build)
- Weight: ~60.5–61.1 g each (~242 g for 4)
- Shaft: 4 mm
- Voltage: 16.8–25.2 V (up to 6S)
- Max power (per motor): ~1512 W @ 1300 KV
- Idle current: ~1.19 A
- Burst current: ~62.4 A @ 1300 KV
- Rated for 4–8" props
- ArduPilot: `MOT_PWM_TYPE = 6` (DShot600), `MOT_SPIN_ARM = 0.10`, `MOT_SPIN_MIN = 0.15`, `MOT_SPIN_MAX = 0.95`, `MOT_THST_EXPO = 0.6`, learned `MOT_THST_HOVER = 0.137`

## Stack — Flywoo GOKU H743 PRO 55A 32-Bit 128K 30×30 (O4 Plug&Play)
**Flight controller:**
- MCU: STM32H743VIH6, 480 MHz Cortex-M7
- IMU: dual ICM42688P gyros (both in use, `INS_USE = INS_USE2 = 1`)
- Baro: DPS310 / SPL06 (on I2C2, 0x76), OSD: AT7456E (`OSD_TYPE = 1`)
- Blackbox: 512 MB
- 7× UART, 2× I2C, 12 PWM outputs, dual-camera switching
- Input: 2–6S (7.4–26 V); BEC: 10 V/3 A + 5 V/3 A
- Mount: 30×30 mm (M3); FC 36.5 × 36.5 × 8.45 mm, 9.9 g
- **Firmware: ArduPilot Copter** (FC also supports Betaflight / INAV)
- Configured for DJI O4 / O4 Pro air unit (plug & play) — O4 not fitted; running analog
- UART usage: see §1
- Board relays: `RELAY2_PIN = 81`, `RELAY3_PIN = 82` (`RELAY3_DEFAULT = 1`) — the board's switchable outputs (BEC / camera switching)
- NeoPixel LED output on `SERVO13_FUNCTION = 120`
- Harmonic notch: `INS_HNTCH_ENABLE = 1`, throttle-based (`INS_HNTCH_MODE = 1`), 80 Hz centre, 40 Hz bandwidth, 3 harmonics
- **Damage note (Oct 2026 crash):** SCL1 pad damaged — I2C1 unusable; external compass moved to I2C2.

**ESC (GOKU G55M AM32):**
- 55 A continuous 4-in-1, 3–6S
- Firmware: AM32 (AT32F421), DShot300/600
- PWM 24k–128k, weight 15 g
- Serial ESC telemetry on UART6

## GNSS / Compass — HGLRC M100-5883 (replaced YEHEI M10Q, Oct 2026)
Compact u-blox M10 GPS with integrated compass. Provides GPS + magnetometer for ArduPilot Copter navigation.
- GNSS: u-blox M10 (10th gen); GPS/QZSS, SBAS, GLONASS, BeiDou, Galileo; 72 channels
- Compass/mag: **QMC5883P (I2C addr 0x2C)** — this unit is from a newer batch that ships the "P" chip, not the QMC5883L (0x0D) in HGLRC's listing
- Protocol: UBX; up to 10 Hz output. ArduPilot runs it at 230400 baud, `GPS1_RATE_MS = 200` (5 Hz), `GPS_AUTO_CONFIG = 1`
- Interface: UART (GNSS) on **UART4** + I2C (compass) on **I2C2 (SDA2/SCL2)**
- Input: 3.3–5 V (powered from FC 5 V)
- Antenna: ceramic patch
- Size: 21 × 21 × 8.02 mm; 7.73 g
- Wiring: GPS TX → FC R4, GPS RX → FC T4, SDA → **SDA2**, SCL → **SCL2**, 5V → 5V, GND → GND
- **ArduPilot compass device ID (confirmed): 1453065** (0x162C09: QMC5883P, addr 0x2C, I2C bus 1). `COMPASS_DEV_ID = COMPASS_PRIO1_ID = 1453065`, `COMPASS_USE = 1`, `COMPASS_EXTERNAL = 1`, auto-detected `COMPASS_ORIENT = 2` (Yaw 90), calibrated. The old YEHEI compass's offsets/orientation still sit in the slot-2 params with `COMPASS_USE2 = 0`; no compass-motor compensation yet (`COMPASS_MOTCT = 0`).

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
- Output: CRSF (on **UART2**; `RC_PROTOCOLS = 1` all)
- RSSI: `RSSI_TYPE = 3` (from the receiver protocol)
- Telemetry power: max 2× 100 mW; up to 500 Hz / F1000 Hz; Gemini mode supported
- Input: 4.5–12 V; weight 1.4 g (excl. antennas); 23.7 × 16.3 × 4.0 mm
- Built-in WiFi for firmware/WebUI

## FPV Video System — Analog (current final config)

### VTX — RushFPV Tank Tiny (Analog 5.8 GHz)
- 5.8 GHz, 48 CH (37 CH US version)
- Power: PIT / 25 / 100 / 200 / 350 mW (max)
- Input: 5 V
- Control: TBS SmartAudio (on **UART8**; `VTX_ENABLE = 1`)
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

## Payload — AKASO EK7000 Pro 4K30FPS Action Camera (upgraded from EK7000, Oct 2026)
- Onboard HD recording camera (separate from the analog FPV feed); self-powered, no electrical connection to the FC
- Remote-triggered from RC switches via the Pico and a gutted AKASO 2.4 GHz remote (see §5)
- Video: 4K @ 30 fps, 1080p @ 60 fps
- Photo: 20 MP
- Stabilisation: in-camera electronic (EIS) — new vs the standard EK7000; useful for cinematic footage, though soft-mounting is still worthwhile against prop vibration
- Control: 2" rear touchscreen (standard EK7000 was button-only) + WiFi app control
- Ports: micro-HDMI, USB; microSD (U3 card recommended, format in-camera)
- Battery: 1050 mAh, ~90 min recording — comfortably outlasts a ~30–35 min flight
- Camera body weight: ~60–61 g (bare, with battery)
- Weight with mount: ~130 g (same as previous EK7000 setup — body weights are near-identical; **re-weigh to confirm**)
- Included in the 1750 g all-up weight

---

# 3. Weight Tally
| Component | Weight |
|---|---|
| Battery (GNB 8000 6S) | 904 g |
| Motors ×4 | ~242 g |
| Stack (FC+ESC) | ~25 g |
| Props ×4 | ~48 g |
| GNSS/compass (HGLRC M100-5883) | ~8 g |
| RX + VTX + FPV cam | ~8 g |
| Telemetry logger (Pico 2 W + SD + display + wiring) | ~18 g |
| AKASO EK7000 Pro 4K (payload, w/ mount) | ~130 g |
| **Subtotal of above** | **~1383 g** |
| Frame + hardware + wiring + antennas (balance) | **~367 g** |
| **All-up weight** | **1750 g** |

Not yet included: the LoRa radio + DX-PJ27 breakout, its LDO and caps, the 433 MHz antenna and the gutted camera remote. Re-weigh the aircraft and update AUW.

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
- Hover thrust needed: 437 g/motor → **~27% throttle** (bench-based)
- Hover power: ~460–475 W (motors) + ~12 W avionics
- **Hover current ≈ 19 A** (fresh, 25 V) to **~21–23 A** (nominal/low, 22–21 V)
- Well within the battery's 80 A (10C) limit — huge margin in hover.

## Flight time (8000 mAh Li-ion)
- **Hover endurance: ~18–20 min** (usable 80–90% of pack, ~21 A hover)
- **Efficient forward cruise: ~25–32 min** (cruise draws ~0.6–0.75× hover current thanks to translational lift)
- Li-ion tolerates deeper discharge than LiPo, so the upper end is realistic if flown gently to ~3.3 V/cell.

> **Superseded by measured data** — the two subsections below (from flight log `log0010`) show real draw is roughly half the bench-based hover estimate, so real endurance and range are *better* than the figures immediately above. Use the measured/mission numbers for planning.

## Measured performance — flight log `log0010` (this-type-of-flying basis)

A ~6-minute low-altitude sortie (AUTO mission + Loiter/AltHold, calm air, ≤ 31 m AGL) flown at the then-configured 6 m/s mission cruise speed. This is the **empirical basis for the mission figures below** and supersedes the bench-derived hover estimate above, which proves conservative.

Measured from pack telemetry (`BATTERY_STATUS`, current sensor calibrated via `BATT_AMP_PERVLT` / `BATT_AMP_OFFSET`):

- **Average draw: ~12.6 A** (~210 mAh/min, ~4.9 Wh/min)
- Throttle: median ~10%, peak 16% — learned hover throttle at the time 12.6%. It has since settled at **`MOT_THST_HOVER = 0.137`** (~13.7%) with the post-crash GPS and logger additions, i.e. ~9% more hover power than in `log0010`.
- Pack: 25.16 → 24.19 V; **~13% of the 8000 mAh used in ~5 min**
- Cross-check: 13% in 5 min → ~38 min to full depletion; the 4.19 → 4.03 V/cell sag over that 13% matches a healthy 21700 Li-ion curve, so the current reading is trustworthy (±10–15%)

The measured ~12.6 A sits **well below the earlier bench estimate of ~19–23 A hover** — the 8×3.7 prop on this light airframe is markedly more efficient than the 7.5" bench prop. Real-world endurance is therefore *better* than the original §4 estimate.

## Expected maximum mission (log-derived + current flight params)

Auto-mission cruise is now **`WP_SPD = 10 m/s`** (raised from 6 m/s); `LOIT_SPEED_MS = 12.5 m/s` in Loiter. Waypoint radius `WP_RADIUS_M = 2`, climb/descent `WP_SPD_UP = 2` / `WP_SPD_DN = 1.5 m/s`. Reserve is enforced by **`BATT_LOW_VOLT = 19.0 V` → RTL** (15 s timer) and **`BATT_CRT_VOLT = 18.0 V` → LAND**, with `RTL_ALT_M = 17 m`.

Endurance is scaled from `log0010` by the ~9% higher hover throttle. At 10 m/s the quad gets more translational lift than at 6 m/s, so cruise power should be similar to or a little below hover; distance figures assume that and have not yet been confirmed by a 10 m/s log.

| Figure | Expected max | Basis |
|---|---|---|
| Airborne endurance | **~32–35 min** | to ~3.3 V/cell, gentle flying, calm air |
| Practical mission endurance (w/ reserve) | **~27–30 min** | plan ~80–85% of pack; RTL trips at 19 V |
| Ground-track distance @ 10 m/s cruise | **~16–18 km** (≤ ~20 km absolute) | endurance × cruise speed — *estimate, verify with a 10 m/s log* |
| Out-and-back radius (return to home) | **~8 km theoretical** | half of usable track, before link limits and wind |

**Planning recommendation:** keep budgeting **~25–30 min / ~10 km of track / ~4–5 km radius** until both the 10 m/s energy figures and the control/video links have been verified at range. The airframe's energy budget is no longer the limiting factor at that radius — the links are.

**Caveats / to confirm before true long-range:**
- **Geofence** is configured at `FENCE_RADIUS = 150 m` / `FENCE_ALT_MAX = 120 m` (`FENCE_ACTION = 3` RTL) but **disabled** (`FENCE_ENABLE = 0`). Raise the radius before flying beyond 150 m with the fence on.
- RTL relies on home being set at takeoff — now guaranteed by `ARMING_NEED_LOC = 1` (§1).
- Fly a log at the new 10 m/s cruise to replace the scaled endurance/range estimates with measured ones. Any headwind cuts effective range and radius.
- Verify the **ELRS 2.4 GHz control link**, analog video and the **433 MHz LoRa backup link** at multi-km range before relying on the full radius. At licence-exempt power (10 mW ERP) the LoRa link's range will be well below the airframe's.
- Airframe lifetime to date (`STAT_*` params): **42 flights, ~91 min total flight time, 6.9 km flown** (`STAT_BOOTCNT = 197`).

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
- ArduPilot Copter + the M10 GNSS/compass suit this mission well — GPS position hold, waypoint/auto missions, RTL, and smooth autonomous cruise all play to the airframe's long-range strengths.

---

# 5. Telemetry Logging Subsystem (Pico 2 W)

Independent, removable telemetry logger tapping the FC's MAVLink stream. Complements (does not replace) the FC's onboard 512 MB `.bin` dataflash logging. The FC streams MAVLink2 out **UART3 (TX3/RX3)** at 921600 baud. The Pico:
- logs every frame to microSD as a QGC-compatible `.tlog`, plus a plaintext `.txt` event log;
- drives a 1.3" ST7789 IPS display for live status;
- bridges the stream over its onboard WiFi (AP mode, UDP :14550) to a phone/tablet GCS;
- sends a light message set over a 433 MHz LoRa backup link to a separate ground station (§6);
- triggers the AKASO EK7000 Pro's photo/record buttons from RC switches.

Code lives in the `AndyFlem/drone_pi` repo (MicroPython). Pin assignments are in `config.py`.

## Parts
- **Raspberry Pi Pico 2 W** (RP2350, 3.3 V logic, WiFi) — ~7 g
- **microSD adapter — mini 6-pin SPI type, 3.3 V ONLY** (no onboard regulator or level shifter; silkscreen pins: 3V3 / CS / MOSI / CLK / MISO / GND). Power from Pico 3V3 — **do NOT feed 5 V.** — ~1 g
- **1.3" IPS, ST7789, 240×240, SPI** (ZJY-IPS130 V2.0; pins GND/VCC/SCL/SDA/RES/DC/BLK, no CS) — ~5 g. Selected by `DISPLAY_TYPE = "st7789"`. The earlier 0.96" SSD1306 I2C OLED is still supported as an alternative (`DISPLAY_TYPE = "ssd1306"`, Pico I2C1 with SDA on GP26 and SCL on GP27, address 0x3C).
- **AKASO 2.4 GHz camera remote**, gutted, with its CR2032 removed
- **DX-LR30-433M22S LoRa module** on a DX-PJ27 breakout with SMA antenna, plus a 3.3 V LDO (see §6)

## Complete wiring

**Pico GPIO usage at a glance:** GP0/1 UART0 (FC) · GP2–5 SPI0 (SD) · GP8, 9, 20, 26, 27 PIO SPI (display) · GP10–18 SPI1 + control (LoRa) · GP21/22 camera remote.

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

**Pico ↔ IPS display (PIO SPI, mode 3)** — the 7-pin board has no CS, so it can't share SPI0/SPI1:
| Display | Pico | Pico phys pin |
|---|---|---|
| SCL | GP27 | 32 |
| SDA | GP26 | 31 |
| RES | GP8 | 11 |
| DC | GP9 | 12 |
| BLK | GP20 | 26 |
| VCC | 3V3(OUT) | 36 |
| GND | GND | 8 |

The bus is a write-only SPI driven by a PIO state machine (PIO0 SM0, `DISPLAY_PIO_SM`) at 20 MHz (`DISPLAY_SPI_BAUD`). It needs no MISO pin, so GP28 is free. Only rows whose text has changed are redrawn. The display used to run on bit-banged SoftSPI, which took about 125 ms per row and held up the main loop for 250–650 ms on every redraw. That overflowed the 1 KB UART RX buffer in about half of the 5 s intervals in log0103.

> Pin note: `config.py` defines `DISPLAY_SCK_PIN = 27` (board "SCL") and `DISPLAY_MOSI_PIN = 26` (board "SDA"). The repo's previous spec table had these two the other way round; the table above follows `config.py`. Check against the actual wiring.

**Pico ↔ AKASO camera remote (gutted, coin cell removed)**. Each GPIO goes to the non-ground leg of a remote tactile switch and is driven open-drain: pulled low for 300 ms (`CAMERA_PRESS_MS`) is a press, floating is released. Presses are queued one at a time with a 250 ms gap (`CAMERA_GAP_MS`), so the remote never sees both buttons at once (`camera.py`):
| Remote | Pico | Pico phys pin |
|---|---|---|
| Photo button | GP21 | 27 |
| Video button | GP22 | 29 |
| BAT+ | 3V3(OUT) | 36 |
| BAT− | GND | 28 |

Triggers (`config.py`), read from RC_CHANNELS with high ≥ 1700 µs and low ≤ 1300 µs:
- **RC channel 7** (`CAMERA_VIDEO_RC_CHAN`): every flip, in either direction, presses record. The camera toggles start/stop on each press.
- **RC channel 9** (`CAMERA_PHOTO_RC_CHAN`): each move to high takes a photo.
- A switch position only counts once 3 RC_CHANNELS readings in a row agree (`CAMERA_RC_CONFIRM_READS`, about 300 ms at 10 Hz). Readings outside 800–2200 µs are treated as invalid, so a single bad packet can't fire the camera.
- The switch position at boot only sets the baseline and does not count as a flip.
- `CAMERA_RECORD_ON_ARM` (currently **off**) also presses record on arm and on disarm. The Pico can't see whether the camera is recording, so with this on, leave the video switch alone while armed.

**Pico ↔ LoRa radio (SPI1, DX-LR30-433M22S on DX-PJ27 breakout)**. SPI1 is kept separate from SPI0 because the microSD driver holds SPI0 during writes. These are the `RADIO_*` entries in `config.py`:
| Radio | Pico | Pico phys pin |
|---|---|---|
| SCK | GP10 (SPI1 SCK) | 14 |
| MOSI | GP11 (SPI1 TX) | 15 |
| MISO | GP12 (SPI1 RX) | 16 |
| NSS | GP13 (GPIO CS) | 17 |
| BUSY | GP14 | 19 |
| DIO1 | GP15 (IRQ, polled) | 20 |
| NRST | GP16 | 21 |
| TXEN | GP17 | 22 |
| RXEN | GP18 | 24 |
| DIO2 | not connected | — |
| VCC | 3.3 V from a dedicated LDO (not 3V3(OUT)) | — |
| GND | GND | 18 |

**Power tree:**
- FC **5 V BEC → Pico VSYS (pin 39)**; FC **GND → Pico GND** (common ground)
- Pico **3V3(OUT) (pin 36) → SD 3V3, display VCC and camera-remote BAT+** (all 3.3 V devices)
- FC **5 V BEC → AMS1117-3.3 (or AP2112K-3.3) → LoRa radio VCC**. The radio draws about 120 mA in TX bursts, so it is kept off the Pico's 3V3(OUT) (see §6 Power). Fit 100 µF + 0.1 µF at the radio.
- All logic 3.3 V end-to-end — no level shifters required. **Never feed the SD adapter 5 V** (this mini type has no regulator).

## ArduPilot config (FC side)
- `SERIAL3_PROTOCOL = 2` (MAVLink2), `SERIAL3_BAUD = 921` (921600, matching `UART_BAUD` in `config.py`) — confirmed: UART3 is SERIAL3 on this target.
- The port's stream-rate group (`MAV2_*` — SERIAL3 is the second MAVLink instance after USB) is left at **0** for all streams. Rates are set from the Pico instead: it sends a HEARTBEAT every second (sysid 255, compid 190) and, once it has seen the FC's HEARTBEAT, requests each message in `REQUESTED_MSG_INTERVALS_US` with `MAV_CMD_SET_MESSAGE_INTERVAL`. The requests are re-sent every 5 s (`STATUS_REQUEST_INTERVAL_MS`) in case one is dropped.
- The USB port's group (`MAV1_*`) keeps normal rates for a wired GCS.

## Requested message rates
| Message | Rate | Used for |
|---|---|---|
| ATTITUDE, RC_CHANNELS | 10 Hz | log, camera triggers, display RSSI |
| GLOBAL_POSITION_INT, VFR_HUD | 5 Hz | log, display heading, flight summary |
| SERVO_OUTPUT_RAW, RAW_IMU, ESC_STATUS, ESC_TELEMETRY_1_TO_4 | 5 Hz | `.tlog` only |
| SYS_STATUS, GPS_RAW_INT | 2 Hz | display (battery, armable, GPS fix) |
| SCALED_PRESSURE, VIBRATION | 2 Hz | `.tlog` only |
| SYSTEM_TIME | 1 Hz | GPS-derived wall clock for log timestamps |
| POWER_STATUS, ESC_INFO | 1 Hz | `.tlog` only |
| MISSION_CURRENT, BATTERY_STATUS, EXTENDED_SYS_STATE | 1 Hz | LoRa link |
| HOME_POSITION | 0.2 Hz | LoRa link |

STATUSTEXT is not requested, since ArduPilot sends it whenever it has something to report. The Pico uses it to detect RC failsafe and PreArm messages.

## Pico firmware (MicroPython)
Boot order in `main.py`: UART → WiFi AP → LoRa radio → SD card and logs → display → camera remote. A LoRa, SD or text-log failure is logged and skipped so the rest keeps running. A UART, WiFi, display or camera failure stops start-up. Third-party drivers needed on the board: `sdcard` (via `mip`), and `ssd1306` only if that display is selected.

- **MAVLink reader** (`mavlink_min.py`): reads MAVLink2 frames off UART0 (1 KB RX buffer) and decodes the few messages the display and logs need. Frames of those decoded types are checksum-checked and dropped if they fail (a UART overrun can splice two frames together). Other types go to the `.tlog` and radio links unchecked. Decoded messages are only acted on if they come from the FC, whose sysid/compid are taken from the first autopilot (non-GCS) HEARTBEAT and then kept fixed.
- **`.tlog`** (`sdlog.TlogWriter`): each record is an 8-byte big-endian µs timestamp followed by the raw frame bytes, so the file opens directly in MAVExplorer, QGroundControl or pymavlink. Timestamps come from `util.WallClock`, which syncs to the FC's SYSTEM_TIME once GPS time is available. Files are named `logNNNN.tlog`, using the next free number, and are flushed with `os.sync()` every 1.5 s (`SD_SYNC_INTERVAL_MS`). The SD SPI bus runs at 1 MHz.
- **Event log** (`pico_log.py` + `sdlog.TextLogWriter`): every REPL debug line is also appended to `logNNNN.txt` next to the matching `.tlog`. This covers init progress, WiFi station connects and disconnects, LoRa link stats every 5 s, main-loop timing every 5 s (`[loop]`: the worst-case ms for each loop section including SD flush/sync, the peak bytes waiting in the UART RX buffer against its size, the bytes/s received, and how many frames were dropped for a bad checksum or false sync), camera triggers, and flight events:
  - mode changes, PreArm failures, ready / not ready to arm;
  - armed / disarmed, with battery voltage;
  - a battery + position + attitude summary line every 5 s.
- **Display** (`lcd_status.py`, or `oled_status.py` for the SSD1306), refreshed every 400 ms:
  | Row | Left | Right |
  |---|---|---|
  | 1 | Flight mode | Armable: `RDY` / `BAD` / `?` |
  | 2 | GPS: `No-fix` or `Fix (sats)` | Heading |
  | 3 | Battery voltage and % | — |
  | 4 | Pico uptime (mm:ss) | RC RSSI %, or `RSSI:LOST` on RC failsafe |
  | 5 | SD status: `Logging` (blinking) or `No SD` | LoRa RSSI of last ground packet (`L:-85` or `L:--`) |
- **WiFi AP + UDP MAVLink bridge** (`wifi_telem.py`): the Pico hosts its own access point (`AP_SSID` / `AP_PASSWORD` in `config.py`, fixed on channel 6 to avoid a cyw43 AP wedge seen after client disconnects, default IP 192.168.4.1). FC frames are broadcast to the AP subnet on UDP :14550 as they're read, so QGroundControl's UDP auto-connect picks the stream up with no handshake. The `.tlog`-only messages in `WIFI_EXCLUDE_MSGIDS` (RAW_IMU, SERVO_OUTPUT_RAW, VIBRATION, SCALED_PRESSURE, POWER_STATUS, ESC_*) are not relayed, because they were slowing Mission Planner's parameter download to about 60 s. MAVLink datagrams from the GCS are written byte for byte to the FC, so the bridge works both ways (telemetry out, commands and params in).
- **433 MHz LoRa backup link** (`lora_link.py` + `sx126x.py`): see §6. The Pico's onboard LED blinks on each ground packet received.
- **Camera remote** (`camera.py`): see the wiring section above.

## Bench tools in the repo
- `tf_luna_test.py` / `tfluna_i2c_test.py`: bench tests for a Benewake TF-Luna lidar on the Pico (UART mode and I2C mode). They use GP12/GP13, which are now LoRa MISO/NSS, so run them only with the radio disconnected and `main.py` stopped. Related: FC `SERIAL7_PROTOCOL = 9` is set for a rangefinder but `RNGFND1_TYPE = 0` (none configured).

---

# 6. 433 MHz LoRa Backup Telemetry Link

Low-rate backup MAVLink telemetry link from the Pico 2 W to a separate ground station. Replaces the earlier RFM69HCW plan.

## Module
- **DX-Smart DX-LR30-433M22S** on a **DX-PJ27-V1.2** breakout, SMA antenna.
- Chip: SX126x family. Most likely **SX1262**: a manual listing for the DX-LR30 names the SX1262, and DX's LLCC68 parts use different model numbers (LR20 / LR22 / LR32 / LR42). This is **not confirmed from a DX datasheet** — the only definitive check is the chip marking under the soldered can.
- Breakout pins: VCC, GND, NSS, NRST, MOSI, SCK, DIO1, MISO, DIO2, BUSY, RXEN, TXEN. Wiring in §5.
- Supply: **3.3 V only** (absolute max about 3.7 V). TX at 22 dBm draws about 120 mA.
- Payload: up to 255 bytes, so nearly every MAVLink2 frame fits in one packet (the RFM69 fragmentation problem goes away).

## Power
- Don't power the radio from the Pico's 3V3(OUT). That rail already carries the SD card write peaks, the display, the camera remote and the Pico's own WiFi, and has a budget of about 300 mA.
- Use an **AMS1117-3.3** fed from the FC's 5 V BEC:
  - about 1.7 V of headroom against a 1.1–1.3 V dropout; dissipates about 0.2 W during TX bursts;
  - the genuine part needs about 22 µF of tantalum or electrolytic on its output and can oscillate with ceramic caps only — the common blue breakout boards already have suitable caps;
  - measure the output before connecting the radio, since clones vary.
  - An **AP2112K-3.3** is a smaller alternative that is happy with ceramic caps.
- Fit 100 µF plus 0.1 µF right at the radio's VCC/GND. Keep all grounds common.

## Driver behaviour (`sx126x.py`)
- Non-blocking SX1262/LLCC68 driver on SPI1 at 8 MHz.
- **Polls BUSY low before every SPI command** (the main difference from the RFM69).
- **TXEN/RXEN** drive the module's local RF switch — TX: TXEN high, RXEN low; RX: RXEN high, TXEN low — set in `start_tx()` / `start_rx()`. Alternative: bridge DIO2 to TXEN and use `SetDIO2AsRfSwitchCtrl` (RXEN then needs the inverse signal).
- DIO1 carries TxDone / RxDone / CRC error / timeout. `lora_link.py` polls the pin rather than using a Pico interrupt, and restarts RX if TxDone hasn't arrived within twice the airtime plus 100 ms.
- LowDataRateOptimize is switched on automatically for SF11/SF12 at 125 kHz.
- Oscillator (`RADIO_TCXO_VOLTAGE = "auto"`): calibrates on the crystal first and, if the oscillator fails to start, resets and retries with a 1.8 V TCXO on DIO3. The startup log line says which was used.
- Regulator: LDO (`RADIO_USE_DCDC = False`). DC-DC only works if the module has the inductor.
- Start-up also runs image calibration for 430–440 MHz, selects the SX1262 high-power PA, applies datasheet errata 15.1 and 15.2, and sets boosted RX gain. If the sync-word register doesn't read back as an SX126x default, start-up fails with "no SX126x found".
- SF7–9 is valid even if the chip turns out to be an LLCC68 (limits SF5–9 at 125 kHz, SF5–10 at 250 kHz, SF5–11 at 500 kHz).

## Link protocol (half-duplex, single frequency)
- Both radios rest in RX. To send: switch to TX, transmit, wait for TxDone, switch back to RX.
- Collision avoidance, with the drone owning the timing (LoRaWAN Class A style):
  - **Drone:** sends a telemetry packet every `DRONE_TX_INTERVAL_MS` (1 s) and listens the rest of the time. If a ground packet is still arriving when a send is due, it waits up to one ground-packet airtime + 10 ms before sending anyway.
  - **Ground:** stays in RX permanently and only transmits (commands or parameter requests) `GROUND_REPLY_DELAY_MS` (100 ms) after receiving a drone packet, so its reply lands while the drone is listening.
- `main.py` offers `lora_link.py` every FC frame and polls it several times per loop, including after each display push, so it gets back to RX in time for the ground reply. Uplink frames from the GCS go straight to the FC UART.
- Fallback options if more is needed later: TDMA (as SiK and mLRS radios do) or listen-before-talk using Channel Activity Detection (CAD).

## Packet format
`[net_id][flags][seq][peer_rssi][peer_snr]` followed by whole MAVLink frames.
- `net_id` is `LORA_NET_ID` (0x5A). Packets with another id, or with the drone flag (bit 7 of `flags`) set, are counted as foreign and dropped.
- `peer_rssi` is the −dBm of the last packet heard from the other side (0 = none); `peer_snr` is its SNR in dB, signed.
- Gaps in the ground's `seq` are counted as lost packets.
- Modem settings and link-protocol values in `config.py` must match the ground station; both ends work out the maximum packet sizes from them.

## Current settings (`config.py`)
| Setting | Value |
|---|---|
| Frequency | 433.920 MHz |
| Modem | SF7, 250 kHz, CR 4/5, 12-symbol preamble, CRC on |
| Sync word | 0x1424 (private network) |
| TX power | 22 dBm |
| Duty cycle | 1.0 (no limit) |
| Drone slot | 1000 ms, with a 30 ms guard |
| Ground reply delay | 100 ms |

Packet size limits:
- Drone packet: the largest that fits in the smaller of `slot × duty` and half the slot.
- Ground reply: the largest that fits in the smaller of `slot × duty` and what's left of the slot after the drone packet, the guard time and the reply delay.

With the current settings both are the full 255 B (~202 ms airtime), so the link carries about 250 B/s each way. With `RADIO_DUTY_CYCLE = 0.1`, both drop to 117 B (~99 ms), about 110 B/s. The startup log prints the sizes actually in use.

## Message set (`LORA_PRIORITY_MSGS` / `LORA_STREAM_RATES`)
- **Stream messages** keep only the latest copy per message and sender and are sent at most at their configured rate; the most overdue relative to its rate goes first.
  | Message | Rate |
  |---|---|
  | HEARTBEAT, ATTITUDE, GLOBAL_POSITION_INT | 1 Hz |
  | SYS_STATUS, GPS_RAW_INT, VFR_HUD | 0.5 Hz |
  | MISSION_CURRENT, BATTERY_STATUS, EXTENDED_SYS_STATE | 0.2 Hz |
  | HOME_POSITION | 0.1 Hz |
- **Priority messages** are queued first in, first out: PARAM_VALUE, the mission protocol messages (39, 40, 44, 46, 47, 51, 73), COMMAND_ACK and STATUSTEXT.
  - While stream messages are due, priority messages may fill at most 75 % of a packet (`LORA_PRIORITY_SHARE`), so HEARTBEAT keeps flowing during a parameter download.
  - The queue holds 40 frames (`LORA_PRIORITY_QUEUE_LEN`); frames beyond that are dropped and counted.
  - The FC's ACKs to the Pico's own `SET_MESSAGE_INTERVAL` requests are not sent.
- Everything else goes to the `.tlog` and WiFi only.

## Status and diagnostics
- RADIO_STATUS (SiK scale) goes to the FC once a second, so ArduPilot logs LoRa RSSI, remote RSSI, noise and lost packets. txbuf is always reported as 100 % — a lower value would make ArduPilot throttle this port, which is also the full-rate `.tlog` feed.
- The display shows the last ground-packet RSSI bottom right (`L:-85`, or `L:--`). RSSI and SNR are cleared if no ground packet arrives for 3 s.
- The Pico's onboard LED flashes for 30 ms on each ground packet.
- Every 5 s a `[lora]` stats line goes to the REPL and the SD event log: TX/RX counts, lost and CRC-error packets, RSSI/SNR at both ends, queue depth and drops, bytes each way, and measured duty cycle.
- A radio that fails to initialise is logged and skipped; logging and WiFi carry on.

## Rules and safety
- **UK licence-exempt 433 MHz (433.05–434.79 MHz) is limited to 10 mW ERP and a 10 % duty cycle.** For licence-exempt use set `RADIO_TX_POWER_DBM` to about 10 and `RADIO_DUTY_CYCLE = 0.1` on **both ends**.
- **The current `config.py` is set to 22 dBm (about 160 mW) with `RADIO_DUTY_CYCLE = 1`.** These settings are only legal under an amateur licence.
- Never transmit without an antenna connected. A 433 MHz quarter-wave antenna is about 17 cm.

## Ground station
The ground-station side (second DX-LR30 module plus a host) is maintained separately. It must use the same packet format and modem/link settings as the drone.

---

# 7. Open Items / To Confirm

**Logger and LoRa link**
- Confirm the exact LoRa chip (seller datasheet, or the marking under the can on a spare module).
- Bring LoRa TX power and duty cycle back to licence-exempt limits on both ends unless flying under an amateur licence (§6 Rules and safety).
- Measure how often a ground reply is missed while the main loop is blocked by an SD sync or a display push. If it happens often, raise `GROUND_REPLY_DELAY_MS` on both ends.
- Verify the display SCL/SDA wiring against `config.py` (GP27 = SCL, GP26 = SDA) and set `DISPLAY_ROTATION` as needed.
- Change `AP_SSID` / `AP_PASSWORD` from the placeholders before flying.
- SD adapter: **3.3 V only** — powered from Pico 3V3(OUT), never 5 V. Use a good-quality card; format FAT32/exFAT.

**Airframe**
- Re-weigh with the LoRa radio, LDO, antenna, IPS display and camera remote fitted; update AUW and §4.
- Fly a log at `WP_SPD = 10 m/s` to replace the scaled endurance/range estimates.
- CompassMot is not done (`COMPASS_MOTCT = 0`) — worthwhile if the GPS mast sits near power wiring.
- Decide on the rangefinder: `SERIAL7_PROTOCOL = 9` is set but no `RNGFND1_TYPE`. (TF-Luna bench scripts exist on the Pico side.)
- Raise `FENCE_RADIUS` before enabling the fence for flights beyond 150 m.

---

# 8. GPS/Compass Replacement Checklist (Oct 2026, post-crash)

1. ✅ Wire M100-5883: TX→R4, RX→T4, SDA→**SDA2**, SCL→**SCL2**, 5V, GND. Mount on a mast/clear of power leads, arrow forward if possible.
2. Power up, confirm baro still reads normally (it shares I2C2 — a bad compass lead will show up as baro errors too).
3. ✅ Check `COMPASS_DEV_ID` → **1453065** (QMC5883P @ 0x2C on I2C2). This unit has the "P" chip, not the 5883L (855305) originally expected. Old ID 855297 now shows as missing.
4. ✅ Compass priority: missing 855297 entry removed, `COMPASS_PRIO1_ID = 1453065`, `COMPASS_USE = 1`.
5. ✅ Onboard compass calibration done; `COMPASS_AUTO_ROT = 2` set `COMPASS_ORIENT = 2` (Yaw 90).
6. Optional but worthwhile: CompassMot if the new mounting is closer to power wiring.
7. ✅ GPS: no changes needed — `SERIAL4_PROTOCOL = 5`, `GPS1_TYPE = 1`, `GPS_AUTO_CONFIG = 1` reconfigured the M10 to `GPS1_RATE_MS = 200` (5 Hz) automatically.
8. ✅ `ARMING_NEED_LOC = 1` set (confirmed in the 28 Oct param dump). Confirm in the field that it refuses to arm until it has a fix.
9. Post-crash: re-check level/accel, frame and prop/motor condition; first flight in AltHold → Loiter in open space, watch for toilet-bowling (bad compass orientation/cal). Flight count has risen from 34 to 42 since the replacement, so this has likely been done — tick off once confirmed.