"""Button platform for Seplos BMS integration."""

from __future__ import annotations

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS button platform."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([SeplosBMSUpdateButton(coordinator)])


class SeplosBMSUpdateButton(
    CoordinatorEntity[SeplosBMSCoordinator], ButtonEntity
):
    """Button to force a manual refresh of the Seplos BMS data."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_now"
    _attr_name = "Actualiser maintenant (Force Update)"
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: SeplosBMSCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_force_update"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.device_name,
            manufacturer=coordinator.bms_device_info.get("manufacturer", "Seplos"),
            model=coordinator.bms_device_info.get("model", "Smart BMS"),
            sw_version=coordinator.bms_device_info.get("sw_version"),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()

