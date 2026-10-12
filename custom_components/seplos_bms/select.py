"""Select platform for Seplos BMS integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

CAN_PROTOCOLS: dict[str, int] = {
    "Pylontech (Pylon)": 1,
    "Growatt": 2,
    "Victron": 3,
    "Sofar": 4,
    "Luxpower": 5,
    "Ginlong (Solis)": 6,
}

RS485_PROTOCOLS: dict[str, int] = {
    "Pylontech": 1,
    "Growatt": 2,
    "Voltronic": 3,
    "Sofar": 4,
    "Luxpower": 5,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS select platform."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        SeplosBMSProtocolSelect(
            coordinator,
            key="can_protocol",
            name="Protocole CAN Onduleur (CAN Protocol)",
            icon="mdi:swap-horizontal-bold",
            options=list(CAN_PROTOCOLS.keys()),
            proto_map=CAN_PROTOCOLS,
            is_can=True,
        ),
        SeplosBMSProtocolSelect(
            coordinator,
            key="rs485_protocol",
            name="Protocole RS485 Onduleur (RS485 Protocol)",
            icon="mdi:serial-port",
            options=list(RS485_PROTOCOLS.keys()),
            proto_map=RS485_PROTOCOLS,
            is_can=False,
        ),
    ])


class SeplosBMSProtocolSelect(
    CoordinatorEntity[SeplosBMSCoordinator], SelectEntity
):
    """Select entity for inverter communication protocol."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        key: str,
        name: str,
        icon: str,
        options: list[str],
        proto_map: dict[str, int],
        is_can: bool,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._key = key
        self._proto_map = proto_map
        self._reverse_map = {v: k for k, v in proto_map.items()}
        self._is_can = is_can
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = options
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = coordinator.device_info
        self._current_option: str = options[0]

    @property
    def current_option(self) -> str | None:
        """Return the selected protocol option."""
        if self.coordinator.data and self._key in self.coordinator.data:
            val = self.coordinator.data[self._key]
            if isinstance(val, int) and val in self._reverse_map:
                return self._reverse_map[val]
            if isinstance(val, str) and val in self._proto_map:
                return val
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Change the selected protocol."""
        if option not in self._proto_map:
            _LOGGER.warning("Unknown protocol option: %s", option)
            return

        code = self._proto_map[option]
        _LOGGER.info(
            "%s: Setting %s to '%s' (code: %s)",
            self.coordinator.name,
            self._key,
            option,
            code,
        )

        is_v2 = getattr(self.coordinator._device, "uuid_tx", lambda: "fff2")() == "ff02"
        if is_v2:
            # V2: CID2_SetCanProtocol (0x4B) or CID2_Set485Protocol (0x4C)
            cmd = 0x4B if self._is_can else 0x4C
            success = await self.coordinator.async_write_v2_command(cmd, bytes([code]))
        else:
            # V3 Modbus: Protocol Control block (PCA 0x1800)
            reg_addr = 0x1810 if self._is_can else 0x1811
            success = await self.coordinator.async_write_modbus_register(reg_addr, code)

        if success:
            self._current_option = option
            if self.coordinator.data is not None:
                self.coordinator.data[self._key] = option
            self.async_write_ha_state()
            self.hass.async_create_task(self.coordinator.async_request_refresh())

