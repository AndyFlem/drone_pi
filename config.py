# config.py -- pin/bus assignments, mirrors dronespec.md Sec.5 wiring tables.

# UART0 (FC UART3 <-> Pico): FC TX3 -> Pico GP1 (RX), FC RX3 -> Pico GP0 (TX)
UART_ID = 0
UART_TX_PIN = 0
UART_RX_PIN = 1
UART_BAUD = 921600

# SPI0 (Pico <-> microSD, 3.3V-only mini adapter -- never feed it 5V)
SPI_ID = 0
SPI_SCK_PIN = 2
SPI_MOSI_PIN = 3
SPI_MISO_PIN = 4
SD_CS_PIN = 5

# SPI1 (Pico <-> DX-LR30 SX126x LoRa radio, see radio-notes.md). Kept off
# SPI0 because the microSD driver holds SPI0 during writes. Power the radio
# from its own 3.3V LDO, never the Pico's 3V3(OUT).
RADIO_SPI_ID = 1
RADIO_SPI_BAUD = 8_000_000
RADIO_SCK_PIN = 10
RADIO_MOSI_PIN = 11
RADIO_MISO_PIN = 12
RADIO_NSS_PIN = 13
RADIO_BUSY_PIN = 14
RADIO_DIO1_PIN = 15
RADIO_NRST_PIN = 16
RADIO_TXEN_PIN = 17
RADIO_RXEN_PIN = 18

# I2C1 (Pico <-> SSD1306 OLED)
I2C_ID = 1
I2C_SDA_PIN = 6
I2C_SCL_PIN = 7
OLED_ADDR = 0x3C  # try 0x3D if the screen stays blank

SD_SYNC_INTERVAL_MS = 1500
OLED_UPDATE_INTERVAL_MS = 400
HEARTBEAT_INTERVAL_MS = 1000
STATION_CHECK_INTERVAL_MS = 2000  # how often to poll for AP client connect/disconnect
FLIGHT_SUMMARY_INTERVAL_MS = 5000  # how often to log a position/attitude summary line

# Messages requested explicitly via MAV_CMD_SET_MESSAGE_INTERVAL, since this
# port has no SRx_* stream-rate group of its own (see mavlink_min.
# build_set_message_interval). msgid=0/1/24/65/74 are decoded for the OLED
# (main._translate) and msgid=2 for wall-clock sync (main.main, util.
# WallClock) -- everything else here is requested purely so the raw bytes
# land in the .tlog for post-flight analysis; rate chosen per message's role
# (attitude/RC faster, slow-changing power/pressure data slower).
#
# STATUSTEXT (253) is also decoded for the OLED (RC failsafe detection) but
# is deliberately not listed here -- it's event-driven and ArduPilot sends
# it unprompted whenever there's something to report, not on a stream rate.
REQUESTED_MSG_INTERVALS_US = {
    2: 1_000_000,    # SYSTEM_TIME        1 Hz  GPS-derived UNIX time for log timestamps
    1: 500_000,      # SYS_STATUS         2 Hz  battery, sensor health flags
    24: 500_000,     # GPS_RAW_INT        2 Hz  raw GPS fix/sats/alt
    33: 200_000,     # GLOBAL_POSITION_INT 5 Hz  fused position/altitude
    30: 100_000,     # ATTITUDE          10 Hz  roll/pitch/yaw
    74: 200_000,     # VFR_HUD            5 Hz  airspeed/groundspeed/climb/throttle
    65: 100_000,     # RC_CHANNELS       10 Hz  receiver channel values + rssi
    36: 200_000,     # SERVO_OUTPUT_RAW   5 Hz  actual motor/servo PWM outputs
    27: 200_000,     # RAW_IMU            5 Hz  accel/gyro/mag
    29: 500_000,     # SCALED_PRESSURE    2 Hz  baro pressure/temp
    241: 500_000,    # VIBRATION          2 Hz  vibe_x/y/z + accel clipping counters
    125: 1_000_000,  # POWER_STATUS       1 Hz  Vcc/servo-rail voltage, brownout flags
    291: 200_000,    # ESC_STATUS         5 Hz  per-motor RPM/voltage/current (modern dialect)
    290: 1_000_000,  # ESC_INFO           1 Hz  per-motor temp/error count (modern dialect)
    11030: 200_000,  # ESC_TELEMETRY_1_TO_4  5 Hz  ArduPilot-dialect fallback for older firmware
    # Low-rate status for the LoRa GCS link (LORA_STREAM_RATES below).
    42: 1_000_000,   # MISSION_CURRENT    1 Hz  current waypoint
    147: 1_000_000,  # BATTERY_STATUS     1 Hz  per-battery voltage/current/consumed
    242: 5_000_000,  # HOME_POSITION    0.2 Hz  home lat/lon/alt
    245: 1_000_000,  # EXTENDED_SYS_STATE 1 Hz  landed state
}
STATUS_REQUEST_INTERVAL_MS = 5000  # resend periodically in case a request is dropped

# Message IDs NOT relayed over the WiFi/UDP GCS link -- the high-rate
# messages above that are requested purely for .tlog post-flight analysis
# (RAW_IMU, SERVO_OUTPUT_RAW, VIBRATION, SCALED_PRESSURE, POWER_STATUS,
# ESC_STATUS, ESC_INFO, ESC_TELEMETRY_1_TO_4). A GCS doesn't need these
# live, and forwarding all of them was saturating the wifi link badly
# enough to make Mission Planner's initial parameter download take ~60s.
# The .tlog still gets every frame unfiltered; this only trims the wifi
# relay. Messages outside REQUESTED_MSG_INTERVALS_US entirely (PARAM_VALUE,
# COMMAND_ACK, MISSION_*, etc.) are FC-response traffic, not part of this
# stream-rate set, and are always relayed.
WIFI_EXCLUDE_MSGIDS = {27, 36, 241, 29, 125, 291, 290, 11030}

# WiFi AP + UDP MAVLink bridge to GCS (Pico 2 W onboard radio). Customize
# SSID/password before flying -- these are placeholders.
AP_SSID = "DronePico"
AP_PASSWORD = "dronetelem"  # WPA2-PSK; MicroPython requires >= 8 chars
GCS_UDP_PORT = 14550
# Fixed 2.4GHz channel (1/6/11 are the non-overlapping ones) instead of
# leaving it to auto-select -- the cyw43 AP occasionally wedges after a
# client disconnects, and pinning the channel avoids the mid-flight channel
# switches that seem to trigger it.
AP_CHANNEL = 6

# --- LoRa backup telemetry link (lora_link.py, radio-notes.md) ---
# TCXO on DIO3: None (crystal), a voltage (1.6-3.3), or "auto" to try the
# crystal first and fall back to a 1.8 V TCXO if the oscillator fails to start.
RADIO_TCXO_VOLTAGE = "auto"
RADIO_USE_DCDC = False  # LDO is always safe; DC-DC needs the module's inductor

# Modem -- must match the ground station exactly.
RADIO_FREQ_HZ = 433_920_000
RADIO_SF = 7  # 7-9 keeps LLCC68 compatibility
RADIO_BW_KHZ = 250  # 125, 250 or 500
RADIO_CR = 1  # 1..4 = 4/5..4/8
RADIO_PREAMBLE = 12
RADIO_SYNC_WORD = 0x1424  # private LoRa network
# UK licence-exempt 433 MHz: 10 mW ERP. Raise only under an amateur licence.
RADIO_TX_POWER_DBM = 10
# ERC 70-03 Annex 1 band c1 (433.05-434.79 MHz, 10 mW) limits duty cycle to
# 10 %. Set to 1.0 if operating under an amateur licence.
RADIO_DUTY_CYCLE = 0.10

# Link protocol -- must match the ground station (both ends derive the
# per-packet size limits from these).
LORA_NET_ID = 0x5A  # packets with a different id are ignored
DRONE_TX_INTERVAL_MS = 1000  # drone owns the timing
GROUND_REPLY_DELAY_MS = 5  # ground waits this long after a drone packet before replying
GUARD_MS = 30  # margin left at the end of each slot

# Light message set sent over LoRa (FC -> ground); everything else is
# .tlog/WiFi only. Priority messages are queued FIFO and always sent.
LORA_PRIORITY_MSGS = {
    22,  # PARAM_VALUE
    39, 40, 44, 46, 47, 51, 73,  # mission protocol
    77,  # COMMAND_ACK (except replies to our own SET_MESSAGE_INTERVAL, see main.py)
    253,  # STATUSTEXT
}
# Streamed messages: only the latest is kept, sent at up to this rate (Hz).
LORA_STREAM_RATES = {
    0: 1.0,  # HEARTBEAT
    1: 0.5,  # SYS_STATUS
    24: 0.5,  # GPS_RAW_INT
    30: 1.0,  # ATTITUDE
    33: 1.0,  # GLOBAL_POSITION_INT
    42: 0.2,  # MISSION_CURRENT
    74: 0.5,  # VFR_HUD
    147: 0.2,  # BATTERY_STATUS
    242: 0.1,  # HOME_POSITION
    245: 0.2,  # EXTENDED_SYS_STATE
}
# Share of a packet priority traffic may take while stream messages are due,
# so HEARTBEAT keeps flowing during a parameter download.
LORA_PRIORITY_SHARE = 0.75
LORA_PRIORITY_QUEUE_LEN = 40
LORA_INJECT_RADIO_STATUS = True  # RADIO_STATUS to the FC so it logs LoRa RSSI
LORA_RADIO_STATUS_INTERVAL_MS = 1000
LORA_STATS_INTERVAL_MS = 5000  # how often to log a [lora] link stats line
