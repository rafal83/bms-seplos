"""Constants for the Seplos BMS integration."""

from typing import Final

DOMAIN: Final = "seplos_bms"

CONF_ADDRESS: Final = "address"
CONF_NAME: Final = "name"
CONF_PROTOCOL: Final = "protocol"
CONF_TYPE: Final = "type"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_KEEP_ALIVE: Final = "keep_alive"

DEFAULT_NAME: Final = "Seplos BMS"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
DEFAULT_KEEP_ALIVE: Final = True
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

PROTOCOL_AUTO: Final = "auto"
PROTOCOL_V2: Final = "seplos_v2"
PROTOCOL_V3: Final = "seplos_v3"

PROTOCOLS: Final = [
    PROTOCOL_AUTO,
    PROTOCOL_V2,
    PROTOCOL_V3,
]

# Service UUIDs used by Seplos BMS (V2: ff00, V3: fff0)
UUID_SERVICE_V2: Final = "0000ff00-0000-1000-8000-00805f9b34fb"
UUID_SERVICE_V3: Final = "0000fff0-0000-1000-8000-00805f9b34fb"

# Alarm / warning problem code bitmask descriptions
ALARM_BITS: Final = {
    0x0001: "voltage_low",
    0x0002: "voltage_high",
    0x0004: "temp_low",
    0x0008: "temp_high",
    0x0010: "current_over_charge",
    0x0020: "current_over_discharge",
    0x0040: "cell_imbalance",
    0x0080: "short_circuit",
}
