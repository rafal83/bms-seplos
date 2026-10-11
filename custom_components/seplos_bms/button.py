"""Button platform for Seplos BMS integration."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS button platform."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    buttons = [
        SeplosBMSUpdateButton(coordinator),
        SeplosBMSZeroCalibrationButton(coordinator),
        SeplosBMSSyncClockButton(coordinator),
        SeplosBMSResetButton(coordinator),
    ]
    async_add_entities(buttons)


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
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()


class SeplosBMSZeroCalibrationButton(
    CoordinatorEntity[SeplosBMSCoordinator], ButtonEntity
):
    """Button to trigger zero current calibration on the BMS."""

    _attr_has_entity_name = True
    _attr_translation_key = "zero_calibration"
    _attr_name = "Calibration zéro courant (Zero Calibration)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:current-dc"

    def __init__(self, coordinator: SeplosBMSCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_zero_calibration"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle zero calibration."""
        _LOGGER.info("%s: Running Zero Current Calibration", self.coordinator.name)
        is_v2 = getattr(self.coordinator._device, "uuid_tx", lambda: "fff2")() == "ff02"
        if is_v2:
            # V2: CID2_Adjust (0x48), zero current index 0, value 0
            await self.coordinator.async_write_v2_command(0x48, bytes([0x00, 0x00, 0x00]))
        else:
            # V3 Modbus: Write to SCA 0x150D (Calibration Zero = 0)
            await self.coordinator.async_write_modbus_register(0x150D, 0x0000)
        await self.coordinator.async_request_refresh()


class SeplosBMSSyncClockButton(
    CoordinatorEntity[SeplosBMSCoordinator], ButtonEntity
):
    """Button to synchronize the BMS internal clock with the host time."""

    _attr_has_entity_name = True
    _attr_translation_key = "sync_clock"
    _attr_name = "Synchroniser l'horloge (Sync Clock)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-sync"

    def __init__(self, coordinator: SeplosBMSCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_sync_clock"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle clock synchronization."""
        now = datetime.now()
        _LOGGER.info("%s: Synchronizing BMS clock to %s", self.coordinator.name, now.isoformat())
        is_v2 = getattr(self.coordinator._device, "uuid_tx", lambda: "fff2")() == "ff02"

        # Format: [year (since 2000), month, day, hour, minute, second]
        clock_bytes = bytes([
            now.year % 100,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
        ])

        if is_v2:
            # V2: CID2_SetTime (0x4E)
            await self.coordinator.async_write_v2_command(0x4E, clock_bytes)
        else:
            # V3: In Modbus, time can be set by writing year/month (reg 0x1800), day/hour (0x1801), min/sec (0x1802)
            reg1 = ((now.year % 100) << 8) | now.month
            reg2 = (now.day << 8) | now.hour
            reg3 = (now.minute << 8) | now.second
            await self.coordinator.async_write_modbus_register(0x1800, reg1)
            await self.coordinator.async_write_modbus_register(0x1801, reg2)
            await self.coordinator.async_write_modbus_register(0x1802, reg3)


class SeplosBMSResetButton(
    CoordinatorEntity[SeplosBMSCoordinator], ButtonEntity
):
    """Button to reboot/reset the BMS system."""

    _attr_has_entity_name = True
    _attr_translation_key = "reset_bms"
    _attr_name = "Redémarrer le BMS (BMS Reset)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: SeplosBMSCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_reset_bms"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        """Handle BMS reset."""
        _LOGGER.warning("%s: Sending BMS Reset / Restart command", self.coordinator.name)
        is_v2 = getattr(self.coordinator._device, "uuid_tx", lambda: "fff2")() == "ff02"
        if is_v2:
            # V2 TeleCtrl CID2 = 0x47 with reset bit (bit 5: Restore factory / reset)
            await self.coordinator.async_write_v2_command(0x47, bytes([0x20]))
        else:
            # V3: System Control reset register or broadcast restart
            await self.coordinator.async_write_modbus_register(0x150F, 0x0001)
        await self.coordinator.async_request_refresh()
