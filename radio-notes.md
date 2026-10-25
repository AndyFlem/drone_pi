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
Used elsewhere: GP0/1 (UART0 to FC), GP2–5 (SPI0, SD card), GP8, 9, 20, 21, 26, 27 (SoftSPI, ST7789 display).

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
  write peaks, the OLED and the Pico's own WiFi, and has a budget of about 300 mA.
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
  - Toggle them inside `send()` and `receive()`.
  - Alternative: bridge DIO2 to TXEN and use `SetDIO2AsRfSwitchCtrl`. RXEN then needs the
    inverse signal.
- Use DIO1 for the TxDone / RxDone / timeout interrupts.
- For SF11 or SF12 at 125 kHz, turn on **LowDataRateOptimize** in `SetModulationParams`.
- Planned settings: SF7–9 at 125–250 kHz. This is valid even if the chip turns out to be an
  LLCC68, whose limits are SF5–9 at 125 kHz, SF5–10 at 250 kHz and SF5–11 at 500 kHz.

## Link protocol (half-duplex, single frequency)
- Both radios rest in RX. To send: switch to TX, transmit, wait for TxDone, switch back to RX.
- Collision avoidance, with the drone owning the timing (LoRaWAN Class A style):
  - **Drone:** sends a telemetry packet every N ms, then listens for about 50–100 ms.
  - **Ground:** stays in RX permanently. It only transmits (commands or parameter requests)
    immediately after receiving a drone packet, so its reply lands in the drone's listen window.
- Use a lighter MAVLink message set over the radio than the full SD `.tlog` stream.
- Fallback options if more is needed later: TDMA (as SiK and mLRS radios do) or
  listen-before-talk using Channel Activity Detection (CAD).

## Rules and safety
- **UK licence-exempt 433 MHz (433.05–434.79 MHz) is limited to 10 mW ERP.** The module can
  output about 160 mW, so set TX power to roughly 10 dBm unless operating under an amateur licence.
- Never transmit without an antenna connected. A 433 MHz quarter-wave antenna is about 17 cm.

## Firmware (drone side)
- `sx126x.py`: non-blocking SX1262/LLCC68 driver (BUSY polling, TXEN/RXEN, DIO1).
- `lora_link.py`: the drone half of the link protocol above. `main.py` offers it every FC
  frame and polls it several times per loop. Uplink frames from the GCS go straight to
  the FC UART.
- Packet: `[net_id][flags][seq][peer_rssi][peer_snr]` followed by whole MAVLink frames.
  The modem settings and link protocol values in `config.py` must match the ground station.
- Defaults: SF7 / 250 kHz / CR 4/5, a 1 s drone slot and a 10 % duty cycle. That allows
  drone packets of up to about 117 B (about 99 ms of airtime), which is about 110 B/s
  of downlink.
- Message set (`LORA_PRIORITY_MSGS` / `LORA_STREAM_RATES`):
  - Stream messages keep only the latest copy and are sent by how overdue they are.
  - Priority messages (params, mission, ACKs, STATUSTEXT) are FIFO. They are capped at
    75 % of a packet while stream messages are waiting.
  - The FC's ACKs to the Pico's own `SET_MESSAGE_INTERVAL` requests are not sent.
- RADIO_STATUS (SiK scale) goes to the FC once a second, so ArduPilot logs LoRa RSSI.
  txbuf is always reported as 100 %. A lower value would make ArduPilot throttle this
  port, which is also the full-rate .tlog feed.
- The OLED shows the last ground-packet RSSI at the bottom right (`L:-85`, or `L:--`).
- A radio that fails to initialise is logged and skipped. Logging and WiFi carry on.

## Open items
- Confirm the exact chip (seller datasheet, or the marking under the can on a spare module).
- The ground-station side (second module plus a host) is maintained separately and must
  use the same packet format and modem/link settings.
- Measure how often a ground reply is missed while the main loop is blocked by an SD
  sync or an OLED push. If it happens often, raise `GROUND_REPLY_DELAY_MS` on both ends.