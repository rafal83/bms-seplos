"""DataUpdateCoordinator for the Seplos BMS integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from aiobmsble import BMSConfig, BMSSample
from aiobmsble.bms.seplos_bms import BMS as SeplosV3BMS
from aiobmsble.bms.seplos_v2_bms import BMS as SeplosV2BMS
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDRESS,
    CONF_KEEP_ALIVE,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PROTOCOL_AUTO,
    PROTOCOL_V2,
    PROTOCOL_V3,
    UUID_SERVICE_V2,
    UUID_SERVICE_V3,
)

_LOGGER = logging.getLogger(__name__)


class SeplosBMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Seplos BMS data safely without overloading BLE."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data[CONF_ADDRESS]
        self.device_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        self.protocol_type = entry.data.get(CONF_PROTOCOL, PROTOCOL_AUTO)
        self.keep_alive = entry.options.get(
            CONF_KEEP_ALIVE,
            entry.data.get(CONF_KEEP_ALIVE, DEFAULT_KEEP_ALIVE),
        )

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
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._device_info_cache: dict[str, str] = {
            "manufacturer": "Seplos",
            "model": "Smart BMS",
            "sw_version": "Unknown",
        }

    @property
    def bms_device_info(self) -> dict[str, str]:
        """Return cached device info."""
        return self._device_info_cache

    def _determine_driver_class(
        self, ble_device: BLEDevice
    ) -> type[SeplosV2BMS | SeplosV3BMS]:
        """Determine driver class once based on user config or advertising data."""
        if self.protocol_type == PROTOCOL_V2:
            return SeplosV2BMS
        if self.protocol_type == PROTOCOL_V3:
            return SeplosV3BMS

        dev_name = (ble_device.name or "").strip()
        if dev_name.startswith(("BP0", "BP1", "BP2")):
            _LOGGER.debug("%s: Detected Seplos V2 protocol from name %s", self.address, dev_name)
            return SeplosV2BMS

        service_info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=True
        )
        if service_info:
            uuids = [u.lower() for u in (service_info.service_uuids or [])]
            if UUID_SERVICE_V2.lower() in uuids or "0000ff00-0000-1000-8000-00805f9b34fb" in uuids:
                _LOGGER.debug("%s: Detected Seplos V2 protocol from service UUID FF00", self.address)
                return SeplosV2BMS
            if UUID_SERVICE_V3.lower() in uuids or "0000fff0-0000-1000-8000-00805f9b34fb" in uuids:
                _LOGGER.debug("%s: Detected Seplos V3 protocol from service UUID FFF0", self.address)
                return SeplosV3BMS

        # Default to V3 (or V2 if BP name)
        return SeplosV3BMS

    async def async_setup(self) -> None:
        """Initialize the driver and verify BLE device availability."""
        if not bluetooth.async_address_present(self.hass, self.address, connectable=True):
            _LOGGER.warning(
                "Seplos BMS %s n'émet pas actuellement d'annonces Bluetooth ou est hors de portée",
                self.address,
            )

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise ConfigEntryNotReady(
                f"Périphérique Bluetooth {self.address} introuvable lors de l'initialisation"
            )

        driver_cls = self._determine_driver_class(ble_device)
        bms_config = BMSConfig(keep_alive=self.keep_alive)
        self._bms = driver_cls(ble_device, config=bms_config)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data safely from Seplos BMS via BLE."""
        async with self._lock:
            # 1. Vérifier si l'appareil est présent et émet
            if not bluetooth.async_address_present(self.hass, self.address, connectable=True):
                self._consecutive_failures += 1
                raise UpdateFailed(
                    f"Seplos BMS {self.address} n'est pas détecté en Bluetooth (hors de portée ou éteint)"
                )

            # 2. Récupérer l'objet BLEDevice actuel de Home Assistant
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                self._consecutive_failures += 1
                raise UpdateFailed(
                    f"Périphérique BLE {self.address} non disponible auprès de Home Assistant"
                )

            # 3. Initialiser le driver si besoin ou rafraîchir l'instance BLEDevice existante
            if self._bms is None:
                driver_cls = self._determine_driver_class(ble_device)
                bms_config = BMSConfig(keep_alive=self.keep_alive)
                self._bms = driver_cls(ble_device, config=bms_config)
            else:
                self._bms._ble_device = ble_device

            # 4. Interroger le BMS avec un timeout strict
            try:
                _LOGGER.debug(
                    "Interrogation du Seplos BMS (%s) avec %s",
                    self.address,
                    self._bms.__class__.__name__,
                )
                async with asyncio.timeout(20):
                    raw_sample = await self._bms.async_update()

                self._consecutive_failures = 0

            except TimeoutError as err:
                self._consecutive_failures += 1
                _LOGGER.warning(
                    "Délai d'attente dépassé avec le Seplos BMS %s. "
                    "IMPORTANT : Vérifiez qu'aucun smartphone ou application mobile "
                    "(ex: EN BMS / bms_flutter) n'est connecté en même temps à la batterie.",
                    self.address,
                )
                # En cas d'échecs répétés, déconnecter pour réinitialiser
                if self._consecutive_failures >= 3:
                    try:
                        await self._bms.disconnect()
                    except Exception:
                        pass
                raise UpdateFailed(
                    f"Timeout Bluetooth avec {self.address} (la batterie est probablement connectée à un smartphone)"
                ) from err

            except BleakError as err:
                self._consecutive_failures += 1
                _LOGGER.warning("Erreur BLE avec Seplos BMS %s: %s", self.address, err)
                if self._consecutive_failures >= 3:
                    try:
                        await self._bms.disconnect()
                    except Exception:
                        pass
                raise UpdateFailed(f"Erreur Bluetooth avec {self.address}: {err}") from err

            except Exception as err:
                self._consecutive_failures += 1
                _LOGGER.error("Erreur inattendue avec Seplos BMS %s: %s", self.address, err)
                raise UpdateFailed(f"Erreur de communication avec {self.address}: {err}") from err

            # 5. Mettre à jour les informations matériel en cache
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

        # États binaires
        data["charging_allowed"] = data.get("chrg_mosfet", False)
        data["discharging_allowed"] = data.get("dischrg_mosfet", False)
        data["balancer_active"] = bool(data.get("balancer", 0))
        data["heater_active"] = bool(data.get("heater", False))

        # Alarme / Problème
        problem_code = data.get("problem_code", 0)
        data["has_problem"] = bool(problem_code)

        return data

    async def async_disconnect(self) -> None:
        """Cleanly disconnect the BLE client."""
        async with self._lock:
            if self._bms is not None:
                try:
                    await self._bms.disconnect()
                except Exception as err:
                    _LOGGER.debug("Erreur lors de la déconnexion de %s: %s", self.address, err)
