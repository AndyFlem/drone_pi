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

# I2C1 (Pico <-> SSD1306 OLED)
I2C_ID = 1
I2C_SDA_PIN = 6
I2C_SCL_PIN = 7
OLED_ADDR = 0x3C  # try 0x3D if the screen stays blank

SD_SYNC_INTERVAL_MS = 1500
OLED_UPDATE_INTERVAL_MS = 400
HEARTBEAT_INTERVAL_MS = 1000
STATS_PRINT_INTERVAL_MS = 2000

# Messages requested explicitly via MAV_CMD_SET_MESSAGE_INTERVAL, since this
# port has no SRx_* stream-rate group of its own (see mavlink_min.
# build_set_message_interval). Only msgid=0/1/24/33 are decoded for the OLED
# (main._translate) -- everything else here is requested purely so the raw
# bytes land in the .tlog for post-flight analysis; rate chosen per message's
# role (attitude/RC faster, slow-changing power/pressure data slower).
REQUESTED_MSG_INTERVALS_US = {
    1: 500_000,      # SYS_STATUS         2 Hz  battery, sensor health flags
    24: 500_000,     # GPS_RAW_INT        2 Hz  raw GPS fix/sats/alt
    33: 200_000,     # GLOBAL_POSITION_INT 5 Hz  fused position/altitude
    30: 100_000,     # ATTITUDE          10 Hz  roll/pitch/yaw
    74: 200_000,     # VFR_HUD            5 Hz  airspeed/groundspeed/climb/throttle
    65: 100_000,     # RC_CHANNELS       10 Hz  receiver channel values + rssi
    36: 200_000,     # SERVO_OUTPUT_RAW   5 Hz  actual motor/servo PWM outputs
    27: 200_000,     # RAW_IMU            5 Hz  accel/gyro/mag
    29: 500_000,     # SCALED_PRESSURE    2 Hz  baro pressure/temp
    125: 1_000_000,  # POWER_STATUS       1 Hz  Vcc/servo-rail voltage, brownout flags
    291: 200_000,    # ESC_STATUS         5 Hz  per-motor RPM/voltage/current (modern dialect)
    290: 1_000_000,  # ESC_INFO           1 Hz  per-motor temp/error count (modern dialect)
    11030: 200_000,  # ESC_TELEMETRY_1_TO_4  5 Hz  ArduPilot-dialect fallback for older firmware
}
STATUS_REQUEST_INTERVAL_MS = 5000  # resend periodically in case a request is dropped
