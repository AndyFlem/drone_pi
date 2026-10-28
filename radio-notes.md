# Radio Notes — 433 MHz LoRa backup telemetry link

Low-rate backup MAVLink telemetry link from the Pico 2 W logger to a ground station.
Replaces the earlier RFM69HCW plan.

## Module
- **DX-Smart DX-LR30-433M22S** on a **DX-PJ27-V1.2** breakout, SMA antenna.
- Chip: SX126x family. Most likely **SX1262**: a manual listing for the DX-LR30 names
  the SX1262, and DX's LLCC68 parts use different model numbers (LR20 / LR22 / LR32 / LR42).
  This is **not confirmed from a DX datasheet**. The only definitive check is the chip
  marking under the soldered can.
- Breakout pins: VCC, GND, NSS, NRST, MOSI, SCK, DIO1, MISO, DIO2, BUSY, RXEN, TXEN.
- Supply: **3.3 V only** (absolute max is about 3.7 V). TX at 22 dBm draws about 120 mA.
- Payload: up to 255 bytes, so nearly every MAVLink2 frame fits in one packet.
  The RFM69 fragmentation problem goes away.

## Wiring — Pico 2 W, SPI1
SPI1 is kept separate from SPI0 because the microSD driver holds SPI0 during writes.
Used elsewhere: GP0/1 (UART0 to FC), GP2–5 (SPI0, SD card), GP8, 9, 20, 26, 27, 28 (SoftSPI, ST7789 display),
GP21/22 (camera remote).

| Radio | Pico | Phys pin |
|---|---|---|
| SCK | GP10 (SPI1 SCK) | 14 |
| MOSI | GP11 (SPI1 TX) | 15 |
| MISO | GP12 (SPI1 RX) | 16 |
| NSS | GP13 (GPIO CS) | 17 |
| BUSY | GP14 | 19 |
| DIO1 | GP15 (IRQ) | 20 |
| NRST | GP16 | 21 |
| TXEN | GP17 | 22 |
| RXEN | GP18 | 24 |
| DIO2 | not connected | — |
| GND | GND | 18 |
| VCC | 3.3 V from a dedicated LDO (see below) | — |

These pins are the `RADIO_*` entries in `config.py`.

## Power
- Don't power the radio from the Pico's 3V3(OUT). That rail already carries the SD card
  write peaks, the display, the camera remote and the Pico's own WiFi, and has a budget of
  about 300 mA.
- Use an **AMS1117-3.3** fed from the FC's 5 V BEC.
  - It has about 1.7 V of headroom against a 1.1–1.3 V dropout.
  - It dissipates about 0.2 W during TX bursts.
  - The genuine part needs about 22 µF of tantalum or electrolytic on its output, and can
    oscillate with ceramic caps only. The common blue breakout boards already have suitable
    caps fitted.
  - Measure the output before connecting the radio, since clones vary.
  - An AP2112K-3.3 would be a smaller alternative that is happy with ceramic caps.
- Fit 100 µF plus 0.1 µF right at the radio's VCC/GND. Keep all grounds common.

## Driver behaviour
- **Poll BUSY low before every SPI command.** This is the main difference from the RFM69.
- **TXEN/RXEN** drive the module's local RF switch:
  - TX: TXEN high, RXEN low.
  - RX: RXEN high, TXEN low.
  - `sx126x.py` sets them in `start_tx()` and `start_rx()`.
  - Alternative: bridge DIO2 to TXEN and use `SetDIO2AsRfSwitchCtrl`. RXEN then needs the
    inverse signal.
- DIO1 carries TxDone / RxDone / CRC error / timeout. `lora_link.py` polls the pin rather than
  using a Pico interrupt, and restarts RX if TxDone hasn't arrived within twice the airtime
  plus 100 ms.
- LowDataRateOptimize is switched on automatically for SF11 or SF12 at 125 kHz.
- Oscillator (`RADIO_TCXO_VOLTAGE = "auto"`): the driver calibrates on the crystal first and,
  if the oscillator fails to start, resets and retries with a 1.8 V TCXO on DIO3. The startup
  log line says which one was used.
- Regulator: LDO (`RADIO_USE_DCDC = False`). DC-DC only works if the module has the inductor.
- Start-up also runs image calibration for 430–440 MHz, selects the SX1262 high-power PA,
  applies datasheet errata 15.1 and 15.2, and sets boosted RX gain. If the sync-word register
  doesn't read back as an SX126x default, start-up fails with "no SX126x found".
- SF7–9 is valid even if the chip turns out to be an LLCC68, whose limits are SF5–9 at
  125 kHz, SF5–10 at 250 kHz and SF5–11 at 500 kHz.

## Link protocol (half-duplex, single frequency)
- Both radios rest in RX. To send: switch to TX, transmit, wait for TxDone, switch back to RX.
- Collision avoidance, with the drone owning the timing (LoRaWAN Class A style):
  - **Drone:** sends a telemetry packet every `DRONE_TX_INTERVAL_MS` (1 s) and listens the
    rest of the time. If a ground packet is still arriving when a send is due, the drone waits
    for up to one ground-packet airtime + 10 ms before sending anyway.
  - **Ground:** stays in RX permanently. It only transmits (commands or parameter requests)
    `GROUND_REPLY_DELAY_MS` (100 ms) after receiving a drone packet, so its reply lands while
    the drone is listening.
- The radio carries a lighter MAVLink message set than the full SD `.tlog` stream.
- Fallback options if more is needed later: TDMA (as SiK and mLRS radios do) or
  listen-before-talk using Channel Activity Detection (CAD).

## Rules and safety
- **UK licence-exempt 433 MHz (433.05–434.79 MHz) is limited to 10 mW ERP and a 10 % duty
  cycle.** For licence-exempt use, set `RADIO_TX_POWER_DBM` to about 10 and
  `RADIO_DUTY_CYCLE = 0.1` on both ends.
- **The current `config.py` is set to 22 dBm (about 160 mW) with `RADIO_DUTY_CYCLE = 1`.**
  These settings are only legal under an amateur licence.
- Never transmit without an antenna connected. A 433 MHz quarter-wave antenna is about 17 cm.

## Firmware (drone side)
- `sx126x.py`: non-blocking SX1262/LLCC68 driver (BUSY polling, TXEN/RXEN, DIO1), SPI1 at
  8 MHz.
- `lora_link.py`: the drone half of the link protocol above. `main.py` offers it every FC
  frame and polls it several times per loop, including after each display push, so it gets
  back to RX in time for the ground reply. Uplink frames from the GCS go straight to the
  FC UART.
- Packet: `[net_id][flags][seq][peer_rssi][peer_snr]` followed by whole MAVLink frames.
  - `net_id` is `LORA_NET_ID` (0x5A). Packets with another id, or with the drone flag
    (bit 7 of `flags`) set, are counted as foreign and dropped.
  - `peer_rssi` is the −dBm of the last packet heard from the other side (0 = none), and
    `peer_snr` is its SNR in dB, signed.
  - Gaps in the ground's `seq` are counted as lost packets.
- The modem settings and link protocol values in `config.py` must match the ground station.
  Both ends work out the maximum packet sizes from them.

### Current settings (`config.py`)
| Setting | Value |
|---|---|
| Frequency | 433.920 MHz |
| Modem | SF7, 250 kHz, CR 4/5, 12-symbol preamble, CRC on |
| Sync word | 0x1424 (private network) |
| TX power | 22 dBm |
| Duty cycle | 1.0 (no limit) |
| Drone slot | 1000 ms, with a 30 ms guard |
| Ground reply delay | 100 ms |

How the packet size limits are worked out:
- Drone packet: the largest that fits in the smaller of `slot × duty` and half the slot.
- Ground reply: the largest that fits in the smaller of `slot × duty` and what's left of the
  slot after the drone packet, the guard time and the reply delay.

With the current settings, both are the full 255 B (about 202 ms of airtime), so the link
carries about 250 B/s each way. With `RADIO_DUTY_CYCLE = 0.1`, both drop to 117 B (about
99 ms), which is about 110 B/s. The startup log prints the sizes actually in use.

### Message set (`LORA_PRIORITY_MSGS` / `LORA_STREAM_RATES`)
- Stream messages keep only the latest copy per message and sender, and are sent at most
  at their configured rate. The most overdue relative to its rate goes first.
  | Message | Rate |
  |---|---|
  | HEARTBEAT, ATTITUDE, GLOBAL_POSITION_INT | 1 Hz |
  | SYS_STATUS, GPS_RAW_INT, VFR_HUD | 0.5 Hz |
  | MISSION_CURRENT, BATTERY_STATUS, EXTENDED_SYS_STATE | 0.2 Hz |
  | HOME_POSITION | 0.1 Hz |
- Priority messages are queued first in, first out: PARAM_VALUE, the mission protocol
  messages (39, 40, 44, 46, 47, 51, 73), COMMAND_ACK and STATUSTEXT.
  - While stream messages are due, priority messages may fill at most 75 % of a packet
    (`LORA_PRIORITY_SHARE`), so HEARTBEAT keeps flowing during a parameter download.
  - The queue holds 40 frames (`LORA_PRIORITY_QUEUE_LEN`). Frames beyond that are dropped
    and counted.
  - The FC's ACKs to the Pico's own `SET_MESSAGE_INTERVAL` requests are not sent.
- Everything else goes to the `.tlog` and WiFi only.

### Status and diagnostics
- RADIO_STATUS (SiK scale) goes to the FC once a second, so ArduPilot logs LoRa RSSI,
  remote RSSI, noise and lost packets. txbuf is always reported as 100 %. A lower value
  would make ArduPilot throttle this port, which is also the full-rate .tlog feed.
- The display shows the last ground-packet RSSI at the bottom right (`L:-85`, or `L:--`).
  RSSI and SNR are cleared if no ground packet arrives for 3 s.
- The Pico's onboard LED flashes for 30 ms on each ground packet.
- Every 5 s a `[lora]` stats line is logged to the REPL and the SD event log. It shows TX/RX
  counts, lost and CRC-error packets, RSSI/SNR at both ends, queue depth and drops, bytes
  each way, and measured duty cycle.
- A radio that fails to initialise is logged and skipped. Logging and WiFi carry on.

## Open items
- Confirm the exact chip (seller datasheet, or the marking under the can on a spare module).
- The ground-station side (second module plus a host) is maintained separately and must
  use the same packet format and modem/link settings.
- Measure how often a ground reply is missed while the main loop is blocked by an SD
  sync or a display push. If it happens often, raise `GROUND_REPLY_DELAY_MS` on both ends.
- Bring TX power and duty cycle back to licence-exempt limits on both ends unless flying
  under an amateur licence (see Rules and safety).