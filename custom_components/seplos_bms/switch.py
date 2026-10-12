"""Switch platform for Seplos BMS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

SWITCH_TYPES: tuple[dict[str, Any], ...] = (
    {
        "key": "chrg_mosfet",
        "name": "Interrupteur Charge (Charge MOSFET)",
        "icon": "mdi:battery-charging",
        "device_class": SwitchDeviceClass.SWITCH,
    },
    {
        "key": "dischrg_mosfet",
        "name": "Interrupteur Décharge (Discharge MOSFET)",
        "icon": "mdi:battery-arrow-down",
        "device_class": SwitchDeviceClass.SWITCH,
    },
    {
        "key": "balancer_active",
        "name": "Équilibrage actif (Balancer)",
        "icon": "mdi:scale-balance",
        "device_class": SwitchDeviceClass.SWITCH,
    },
    {
        "key": "heater_active",
        "name": "Chauffage batterie (Heater)",
        "icon": "mdi:radiator",
        "device_class": SwitchDeviceClass.SWITCH,
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS switches."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SeplosBMSSwitch(coordinator, description)
        for description in SWITCH_TYPES
    ]
    async_add_entities(entities)


class SeplosBMSSwitch(CoordinatorEntity[SeplosBMSCoordinator], SwitchEntity):
    """Representation of a Seplos BMS controllable switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        description: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._key = description["key"]
        self._attr_translation_key = self._key
        self._attr_name = description["name"]
        self._attr_icon = description["icon"]
        self._attr_device_class = description["device_class"]
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{coordinator.address}_{self._key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        if not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get(self._key, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_set_switch(self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_set_switch(self._key, False)

