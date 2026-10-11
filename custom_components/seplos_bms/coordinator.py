"""DataUpdateCoordinator for the Seplos BMS integration."""

from __future__ import annotations

from collections import deque
from datetime import timedelta
from itertools import islice
import logging
from time import monotonic
from typing import Any

from aiobmsble import BMSSample
from aiobmsble.basebms import BaseBMS
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_last_service_info,
)
from homeassistant.components.bluetooth.const import DOMAIN as BLUETOOTH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SeplosBMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Seplos BMS data safely without overloading BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        bms_device: BaseBMS,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data.get(CONF_ADDRESS, ble_device.address)
        self.device_name = entry.data.get(CONF_NAME, entry.title or DEFAULT_NAME)
        self._device: BaseBMS = bms_device
        self._mac = ble_device.address
        self._stale: bool = False
        self._link_q: deque[bool] = deque([False], maxlen=100)

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.address})",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
            config_entry=entry,
        )

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac), (BLUETOOTH_DOMAIN, self._mac)},
            connections={(CONNECTION_BLUETOOTH, self._mac)},
            name=self.device_name,
            manufacturer=self._device.INFO.get("default_manufacturer", "Seplos"),
            model=self._device.INFO.get("default_model", "Smart BMS"),
        )

        if service_info := async_last_service_info(
            self.hass, address=self._mac, connectable=True
        ):
            _LOGGER.debug("%s: Initial advertisement: %s", self.name, service_info.as_dict())

    @property
    def rssi(self) -> int | None:
        """Return RSSI value for target BMS."""
        service_info: BluetoothServiceInfoBleak | None = async_last_service_info(
            self.hass, address=self._mac, connectable=True
        )
        return service_info.rssi if service_info else None

    @property
    def link_quality(self) -> int:
        """Return percentage of successful BMS reads out of the last 100 attempts."""
        return self._link_q.count(True) * 100 // len(self._link_q)

    def _device_stale(self) -> bool:
        """Check if the connection has become stale and needs a clean reset."""
        if self._link_q[-1]:
            self._stale = False
        elif (
            not self._stale
            and self.link_quality <= 10
            and list(islice(reversed(self._link_q), 10)) == [False] * 10
        ):
            rssi = self.rssi
            _LOGGER.error(
                "%s: Seplos BMS is stale, triggering reconnect%s!",
                self.name,
                f", check signal strength ({rssi} dBm)" if rssi is not None else "",
            )
            self._stale = True

        return self._stale

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect safely."""
        _LOGGER.debug("Shutting down Seplos BMS coordinator (%s)", self.name)
        await super().async_shutdown()
        try:
            await self._device.disconnect()
        except Exception as err:
            _LOGGER.debug("Error disconnecting during shutdown of %s: %s", self.address, err)

    async def _async_setup(self) -> None:
        """Fetch static device information during initial setup."""
        try:
            bms_info = await self._device.device_info()
            if bms_info:
                self.device_info.update(
                    DeviceInfo(
                        name=bms_info.get("name") or self.device_name,
                        manufacturer=bms_info.get("manufacturer")
                        or self._device.INFO.get("default_manufacturer", "Seplos"),
                        model=bms_info.get("model")
                        or self._device.INFO.get("default_model", "Smart BMS"),
                        sw_version=bms_info.get("sw_version") or bms_info.get("fw_version"),
                        hw_version=bms_info.get("hw_version"),
                        model_id=bms_info.get("model_id"),
                        serial_number=bms_info.get("serial_number"),
                    )
                )
        except Exception as err:
            _LOGGER.debug("Could not read device info for %s: %s", self.address, err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Seplos BMS via aiobmsble."""
        _LOGGER.debug("%s: BMS data update started", self.name)

        if self._device_stale():
            await self._device.disconnect(reset=True)

        start = monotonic()
        update_interval_sec = self.update_interval.total_seconds() if self.update_interval else DEFAULT_SCAN_INTERVAL

        try:
            # Note: We intentionally do NOT wrap this in asyncio.timeout.
            # aiobmsble manages its own internal timeouts. Wrapping in asyncio.timeout
            # cancels Bleak mid-flight and crashes the Linux/BlueZ BLE stack.
            raw_sample: BMSSample | None = await self._device.async_update()
            if not raw_sample:
                raise UpdateFailed(f"Aucune donnée valide reçue du BMS {self.address}")

        except TimeoutError as err:
            _LOGGER.warning(
                "%s: Timeout Bluetooth. Vérifiez qu'aucune application mobile "
                "(ex: EN BMS / bms_flutter) n'est activement connectée en même temps à la batterie.",
                self.name,
            )
            raise UpdateFailed(f"Timeout Bluetooth avec {self.address}") from err

        except (BleakError, EOFError) as err:
            rssi = self.rssi
            _LOGGER.warning(
                "%s: Erreur communication BLE: %s (RSSI: %s dBm)",
                self.name,
                err,
                rssi if rssi is not None else "--",
            )
            raise UpdateFailed(f"Erreur Bluetooth avec {self.address}: {err}") from err

        except Exception as err:
            _LOGGER.error("%s: Erreur inattendue: %s", self.name, err)
            raise UpdateFailed(f"Erreur inattendue avec {self.address}: {err}") from err

        finally:
            elapsed = monotonic() - start
            slots = 1 + int(elapsed / max(update_interval_sec, 1))
            self._link_q.extend([False] * slots)

        self._link_q[-1] = True  # Mark this attempt as successful

        processed = self._process_sample(raw_sample)
        _LOGGER.debug("%s: BMS data update successful: %s", self.name, processed)
        return processed

    def _process_sample(self, sample: BMSSample) -> dict[str, Any]:
        """Normalize sample data into structured dictionary."""
        data: dict[str, Any] = dict(sample)

        # Si le BMS est V3, les données de pack peuvent être dans packs[0]
        packs = data.get("packs")
        if packs and isinstance(packs, list) and len(packs) > 0:
            first_pack = packs[0]
            if isinstance(first_pack, dict):
                for k, v in first_pack.items():
                    if k not in data or data[k] is None:
                        data[k] = v

        # Puissance (W)
        voltage = data.get("voltage")
        current = data.get("current")
        if voltage is not None and current is not None:
            data["power"] = round(float(voltage) * float(current), 1)
        else:
            data["power"] = None

        # Statistiques des cellules
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

        # Températures
        temp_values = data.get("temp_values")
        if isinstance(temp_values, list) and temp_values:
            temps: list[float] = []
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

        # États binaires
        data["charging_allowed"] = data.get("chrg_mosfet", False)
        data["discharging_allowed"] = data.get("dischrg_mosfet", False)
        data["balancer_active"] = bool(data.get("balancer", 0))
        data["heater_active"] = bool(data.get("heater", False))

        # Alarme / Problème
        problem_code = data.get("problem_code", 0)
        data["has_problem"] = bool(problem_code)

        return data
