"""The Seplos BMS integration."""

from __future__ import annotations

import logging
from typing import Any

from aiobmsble import BMSConfig
from aiobmsble.basebms import BaseBMS
from aiobmsble.bms.seplos_bms import BMS as SeplosV3BMS
from aiobmsble.bms.seplos_v2_bms import BMS as SeplosV2BMS
from aiobmsble.utils import bms_cls
from bleak.backends.device import BLEDevice

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import (
    CONF_ADDRESS,
    CONF_KEEP_ALIVE,
    CONF_PROTOCOL,
    CONF_TYPE,
    DEFAULT_KEEP_ALIVE,
    DOMAIN,
    PROTOCOL_V2,
    PROTOCOL_V3,
    UUID_SERVICE_V2,
    UUID_SERVICE_V3,
)
from .coordinator import SeplosBMSCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def _resolve_bms_class(entry: ConfigEntry, ble_device: BLEDevice, hass: HomeAssistant) -> type[BaseBMS]:
    """Resolve the appropriate BMS class for this entry."""
    # 1. Type explicitement stocké dans entry.data (ex: aiobmsble.bms.seplos_bms)
    bms_type = entry.data.get(CONF_TYPE)
    if bms_type:
        mod_name = bms_type.rsplit(".", 1)[-1]
        resolved = await bms_cls(mod_name)
        if resolved:
            return resolved

    # 2. Protocole configuré par l'utilisateur
    protocol = entry.options.get(CONF_PROTOCOL, entry.data.get(CONF_PROTOCOL))
    if protocol == PROTOCOL_V2:
        return SeplosV2BMS
    if protocol == PROTOCOL_V3:
        return SeplosV3BMS

    # 3. Détection par nom d'annonce Bluetooth
    dev_name = (ble_device.name or "").strip()
    if dev_name.startswith(("BP0", "BP1", "BP2")):
        return SeplosV2BMS

    # 4. Détection par service UUIDs annoncés
    service_info = bluetooth.async_last_service_info(hass, ble_device.address, connectable=True)
    if service_info:
        uuids = [u.lower() for u in (service_info.service_uuids or [])]
        if UUID_SERVICE_V2.lower() in uuids or "0000ff00-0000-1000-8000-00805f9b34fb" in uuids:
            return SeplosV2BMS
        if UUID_SERVICE_V3.lower() in uuids or "0000fff0-0000-1000-8000-00805f9b34fb" in uuids:
            return SeplosV3BMS

    # Par défaut, Seplos V3
    return SeplosV3BMS


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Seplos BMS integration from configuration.yaml (not supported)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Seplos BMS from a config entry."""
    address = entry.unique_id or entry.data.get(CONF_ADDRESS)
    if not address:
        raise ConfigEntryError("Missing unique_id / address for Seplos BMS")

    ble_device: BLEDevice | None = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if ble_device is None:
        _LOGGER.debug("BLE device %s not currently found in HA Bluetooth cache", address)
        raise ConfigEntryNotReady(f"Périphérique Bluetooth {address} non détecté pour le moment")

    bms_class = await _resolve_bms_class(entry, ble_device, hass)
    keep_alive = entry.options.get(
        CONF_KEEP_ALIVE,
        entry.data.get(CONF_KEEP_ALIVE, DEFAULT_KEEP_ALIVE),
    )

    bms_device: BaseBMS = bms_class(
        ble_device,
        config=BMSConfig(keep_alive=keep_alive),
    )

    coordinator = SeplosBMSCoordinator(hass, ble_device, bms_device, entry)

    started = False
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        started = True
    finally:
        if not started:
            await coordinator.async_shutdown()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: SeplosBMSCoordinator | None = getattr(entry, "runtime_data", None)
    if coordinator is None and DOMAIN in hass.data:
        coordinator = hass.data[DOMAIN].get(entry.entry_id)

    if unload_ok and coordinator is not None:
        if DOMAIN in hass.data:
            hass.data[DOMAIN].pop(entry.entry_id, None)
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Reload config entry."""
    return await hass.config_entries.async_reload(entry.entry_id)
