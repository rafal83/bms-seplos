"""DataUpdateCoordinator for the Seplos BMS integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from aiobmsble import BMSSample
from aiobmsble.bms.seplos_bms import BMS as SeplosV3BMS
from aiobmsble.bms.seplos_v2_bms import BMS as SeplosV2BMS
from bleak.backends.device import BLEDevice
from bleak_retry_connector import close_stale_connections_by_address

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PROTOCOL_AUTO,
    PROTOCOL_V2,
    PROTOCOL_V3,
)

_LOGGER = logging.getLogger(__name__)


class SeplosBMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Seplos BMS data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data[CONF_ADDRESS]
        self.device_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        self.protocol_type = entry.data.get(CONF_PROTOCOL, PROTOCOL_AUTO)

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.address})",
            update_interval=timedelta(seconds=scan_interval),
        )

        self._bms: SeplosV2BMS | SeplosV3BMS | None = None
        self._ble_device: BLEDevice | None = None
        self._device_info_cache: dict[str, str] = {
            "manufacturer": "Seplos",
            "model": "Smart BMS",
            "sw_version": "Unknown",
        }

    @property
    def bms_device_info(self) -> dict[str, str]:
        """Return cached device info."""
        return self._device_info_cache

    def _get_ble_device(self) -> BLEDevice:
        """Get the BLEDevice from Home Assistant bluetooth integration."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise UpdateFailed(f"Device {self.address} not found in Bluetooth scan")
        return ble_device

    def _instantiate_bms(self, ble_device: BLEDevice) -> SeplosV2BMS | SeplosV3BMS:
        """Instantiate the correct BMS driver class based on protocol setting."""
        if self.protocol_type == PROTOCOL_V2:
            return SeplosV2BMS(ble_device)
        if self.protocol_type == PROTOCOL_V3:
            return SeplosV3BMS(ble_device)

        # Automatic detection based on device advertised name
        dev_name = (ble_device.name or "").strip()
        if dev_name.startswith(("BP0", "BP1", "BP2")):
            return SeplosV2BMS(ble_device)

        # Default for SP, XZHX, CSY, ST, etc. is V3 (or fallback to V2)
        return SeplosV3BMS(ble_device)

    async def _async_setup(self) -> None:
        """Initial check to ensure device is reachable."""
        try:
            ble_device = self._get_ble_device()
            self._ble_device = ble_device
            self._bms = self._instantiate_bms(ble_device)
        except Exception as err:
            raise ConfigEntryNotReady(
                f"Unable to connect to Seplos BMS at {self.address}: {err}"
            ) from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Seplos BMS via BLE."""
        ble_device = self._get_ble_device()
        self._ble_device = ble_device

        # If driver not instantiated or ble_device changed, re-create
        if self._bms is None or self._bms._ble_device != ble_device:
            self._bms = self._instantiate_bms(ble_device)

        await close_stale_connections_by_address(self.address)

        raw_sample: BMSSample | None = None
        last_error: Exception | None = None

        # Try query with current driver, fallback between V3 and V2 if auto
        drivers_to_try = [self._bms]
        if self.protocol_type == PROTOCOL_AUTO:
            if isinstance(self._bms, SeplosV3BMS):
                drivers_to_try.append(SeplosV2BMS(ble_device))
            else:
                drivers_to_try.append(SeplosV3BMS(ble_device))

        for driver in drivers_to_try:
            try:
                _LOGGER.debug(
                    "Connecting and querying Seplos BMS (%s) with %s",
                    self.address,
                    driver.__class__.__name__,
                )
                # Apply timeout to BLE query to avoid blocking coordinator
                async with asyncio.timeout(25):
                    raw_sample = await driver.async_update()
                    self._bms = driver
                    break
            except Exception as err:
                last_error = err
                _LOGGER.debug(
                    "Driver %s failed for %s: %s",
                    driver.__class__.__name__,
                    self.address,
                    err,
                )
                try:
                    await driver.disconnect()
                except Exception:
                    pass

        if raw_sample is None:
            raise UpdateFailed(
                f"Failed to fetch data from Seplos BMS {self.address}: {last_error}"
            )

        # Update cached device info if available
        try:
            info = getattr(self._bms, "device_info", {})
            if info:
                self._device_info_cache["manufacturer"] = info.get(
                    "manufacturer", info.get("default_manufacturer", "Seplos")
                )
                self._device_info_cache["model"] = info.get(
                    "model", info.get("default_model", "Smart BMS")
                )
                self._device_info_cache["sw_version"] = info.get(
                    "sw_version", "1.0"
                )
        except Exception:
            pass

        return self._process_sample(raw_sample)

    def _process_sample(self, sample: BMSSample) -> dict[str, Any]:
        """Normalize sample data into structured dictionary."""
        data: dict[str, Any] = dict(sample)

        # Calculated fields: Power (W)
        voltage = data.get("voltage")
        current = data.get("current")
        if voltage is not None and current is not None:
            data["power"] = round(float(voltage) * float(current), 1)
        else:
            data["power"] = None

        # Cell voltages statistics
        cell_voltages: list[float] = data.get("cell_voltages", [])
        if cell_voltages:
            valid_cells = [float(v) for v in cell_voltages if v > 0]
            if valid_cells:
                min_v = min(valid_cells)
                max_v = max(valid_cells)
                data["min_cell_voltage"] = round(min_v, 3)
                data["max_cell_voltage"] = round(max_v, 3)
                data["cell_voltage_delta"] = round((max_v - min_v) * 1000, 1)  # mV
                data["min_cell_number"] = valid_cells.index(min_v) + 1
                data["max_cell_number"] = valid_cells.index(max_v) + 1
            data["cell_count"] = len(cell_voltages)

        # Temperatures
        # temp_values can be a list of floats or TempSensor objects
        temp_values = data.get("temp_values")
        if isinstance(temp_values, list) and temp_values:
            temps = []
            for t in temp_values:
                if isinstance(t, (int, float)):
                    temps.append(float(t))
                elif hasattr(t, "value"):
                    temps.append(float(t.value))
                elif isinstance(t, dict) and "value" in t:
                    temps.append(float(t["value"]))
            if temps:
                data["temp_cell_min"] = min(temps)
                data["temp_cell_max"] = max(temps)
                data["temp_cell_avg"] = round(sum(temps) / len(temps), 1)

        # Binary states
        data["charging_allowed"] = data.get("chrg_mosfet", False)
        data["discharging_allowed"] = data.get("dischrg_mosfet", False)
        data["balancer_active"] = bool(data.get("balancer", 0))
        data["heater_active"] = bool(data.get("heater", False))

        # Problem / Alarm code
        problem_code = data.get("problem_code", 0)
        data["has_problem"] = bool(problem_code)

        return data

    async def async_disconnect(self) -> None:
        """Disconnect underlying BLE client."""
        if self._bms is not None:
            try:
                await self._bms.disconnect()
            except Exception as err:
                _LOGGER.debug("Error disconnecting %s: %s", self.address, err)

