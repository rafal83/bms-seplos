"""Number platform for Seplos BMS integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SeplosBMSNumberDescription(NumberEntityDescription):
    """Class describing Seplos BMS number entities."""

    reg_addr: int
    v2_para_idx: int
    scale: float
    precision: int = 2


NUMBERS: tuple[SeplosBMSNumberDescription, ...] = (
    # Cell Overvoltage Protection (Coupe-circuit surtension cellule)
    SeplosBMSNumberDescription(
        key="cell_ovp",
        translation_key="cell_ovp",
        name="Protection surtension cellule",
        native_min_value=3.0,
        native_max_value=3.9,
        native_step=0.005,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x130D,
        v2_para_idx=4,
        scale=0.001,
        precision=3,
    ),
    # Cell Overvoltage Recovery (Reprise après surtension cellule)
    SeplosBMSNumberDescription(
        key="cell_ovpr",
        translation_key="cell_ovpr",
        name="Reprise surtension cellule",
        native_min_value=3.0,
        native_max_value=3.7,
        native_step=0.005,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x130C,
        v2_para_idx=5,
        scale=0.001,
        precision=3,
    ),
    # Cell Undervoltage Protection (Coupe-circuit sous-tension cellule)
    SeplosBMSNumberDescription(
        key="cell_uvp",
        translation_key="cell_uvp",
        name="Protection sous-tension cellule",
        native_min_value=2.0,
        native_max_value=3.1,
        native_step=0.005,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1311,
        v2_para_idx=6,
        scale=0.001,
        precision=3,
    ),
    # Cell Undervoltage Recovery (Reprise après sous-tension cellule)
    SeplosBMSNumberDescription(
        key="cell_uvpr",
        translation_key="cell_uvpr",
        name="Reprise sous-tension cellule",
        native_min_value=2.3,
        native_max_value=3.3,
        native_step=0.005,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1310,
        v2_para_idx=7,
        scale=0.001,
        precision=3,
    ),
    # Pack Overvoltage Protection (Protection surtension globale pack)
    SeplosBMSNumberDescription(
        key="pack_ovp",
        translation_key="pack_ovp",
        name="Protection surtension pack",
        native_min_value=40.0,
        native_max_value=62.0,
        native_step=0.1,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1305,
        v2_para_idx=14,
        scale=0.01,
        precision=2,
    ),
    # Pack Undervoltage Protection (Protection sous-tension globale pack)
    SeplosBMSNumberDescription(
        key="pack_uvp",
        translation_key="pack_uvp",
        name="Protection sous-tension pack",
        native_min_value=36.0,
        native_max_value=54.0,
        native_step=0.1,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1309,
        v2_para_idx=16,
        scale=0.01,
        precision=2,
    ),
    # Charge Overcurrent Protection (Courant max de charge)
    SeplosBMSNumberDescription(
        key="charge_ocp",
        translation_key="charge_ocp",
        name="Limite max courant de charge",
        native_min_value=10.0,
        native_max_value=250.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1317,
        v2_para_idx=54,
        scale=0.01,
        precision=1,
    ),
    # Discharge Overcurrent Protection (Courant max de décharge)
    SeplosBMSNumberDescription(
        key="discharge_ocp",
        translation_key="discharge_ocp",
        name="Limite max courant de décharge",
        native_min_value=10.0,
        native_max_value=250.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x131D,
        v2_para_idx=55,
        scale=0.01,
        precision=1,
    ),
    # Battery Rated Capacity (Capacité nominale totale)
    SeplosBMSNumberDescription(
        key="rated_capacity",
        translation_key="rated_capacity",
        name="Capacité nominale batterie",
        native_min_value=50.0,
        native_max_value=600.0,
        native_step=5.0,
        native_unit_of_measurement="Ah",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1358,
        v2_para_idx=58,
        scale=0.01,
        precision=1,
    ),
    # Equalization Opening Voltage (Tension début équilibrage)
    SeplosBMSNumberDescription(
        key="equalization_opening_voltage",
        translation_key="equalization_opening_voltage",
        name="Tension début équilibrage",
        native_min_value=3.2,
        native_max_value=3.6,
        native_step=0.005,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1350,
        v2_para_idx=8,
        scale=0.001,
        precision=3,
    ),
    # Equalization Opening Pressure Difference (Delta tension début équilibrage)
    SeplosBMSNumberDescription(
        key="equalization_opening_delta",
        translation_key="equalization_opening_delta",
        name="Écart tension début équilibrage",
        native_min_value=5.0,
        native_max_value=100.0,
        native_step=1.0,
        native_unit_of_measurement="mV",
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1351,
        v2_para_idx=62,
        scale=0.001,
        precision=0,
    ),
    # Charge High Temp Alarm (Alarme haute température charge)
    SeplosBMSNumberDescription(
        key="charge_temp_high_alarm",
        translation_key="charge_temp_high_alarm",
        name="Alarme haute température charge",
        native_min_value=35.0,
        native_max_value=65.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1330,
        v2_para_idx=20,
        scale=0.1,
        precision=1,
    ),
    # Charge High Temp Protection (Protection haute température charge)
    SeplosBMSNumberDescription(
        key="charge_temp_high_protect",
        translation_key="charge_temp_high_protect",
        name="Protection haute température charge",
        native_min_value=40.0,
        native_max_value=70.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1332,
        v2_para_idx=24,
        scale=0.1,
        precision=1,
    ),
    # Charge Low Temp Protection (Protection basse température charge)
    SeplosBMSNumberDescription(
        key="charge_temp_low_protect",
        translation_key="charge_temp_low_protect",
        name="Protection basse température charge",
        native_min_value=-20.0,
        native_max_value=15.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x1336,
        v2_para_idx=26,
        scale=0.1,
        precision=1,
    ),
    # Discharge High Temp Protection (Protection haute température décharge)
    SeplosBMSNumberDescription(
        key="discharge_temp_high_protect",
        translation_key="discharge_temp_high_protect",
        name="Protection haute température décharge",
        native_min_value=40.0,
        native_max_value=75.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x133A,
        v2_para_idx=32,
        scale=0.1,
        precision=1,
    ),
    # Discharge Low Temp Protection (Protection basse température décharge)
    SeplosBMSNumberDescription(
        key="discharge_temp_low_protect",
        translation_key="discharge_temp_low_protect",
        name="Protection basse température décharge",
        native_min_value=-30.0,
        native_max_value=10.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x133E,
        v2_para_idx=34,
        scale=0.1,
        precision=1,
    ),
    # Cell Low Temp Heating Start (Démarrage chauffage cellule)
    SeplosBMSNumberDescription(
        key="cell_heating_temp",
        translation_key="cell_heating_temp",
        name="Seuil démarrage chauffage cellule",
        native_min_value=-10.0,
        native_max_value=15.0,
        native_step=1.0,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.CONFIG,
        mode=NumberMode.BOX,
        reg_addr=0x134C,
        v2_para_idx=36,
        scale=0.1,
        precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS number parameters."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SeplosBMSNumber(coordinator, description)
        for description in NUMBERS
    ]
    async_add_entities(entities)


class SeplosBMSNumber(CoordinatorEntity[SeplosBMSCoordinator], NumberEntity):
    """Representation of a Seplos BMS configurable parameter."""

    entity_description: SeplosBMSNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        description: SeplosBMSNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_name = description.name
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = coordinator.device_info
        # Store locally cached value
        self._current_value: float | None = None

    @property
    def native_value(self) -> float | None:
        """Return the current parameter value."""
        # Check if coordinator data has the value
        if self.coordinator.data and self.entity_description.key in self.coordinator.data:
            val = self.coordinator.data.get(self.entity_description.key)
            if val is not None:
                return round(float(val), self.entity_description.precision)

        if self._current_value is not None:
            return round(self._current_value, self.entity_description.precision)

        # Default sensible fallbacks based on key
        defaults = {
            "cell_ovp": 3.65,
            "cell_ovpr": 3.45,
            "cell_uvp": 2.50,
            "cell_uvpr": 2.80,
            "pack_ovp": 58.4,
            "pack_uvp": 43.2,
            "charge_ocp": 100.0,
            "discharge_ocp": 150.0,
            "rated_capacity": 200.0,
            "equalization_opening_voltage": 3.40,
            "equalization_opening_delta": 30.0,
            "charge_temp_high_alarm": 50.0,
            "charge_temp_high_protect": 55.0,
            "charge_temp_low_protect": 0.0,
            "discharge_temp_high_protect": 55.0,
            "discharge_temp_low_protect": -15.0,
            "cell_heating_temp": 0.0,
        }
        return defaults.get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value for parameter."""
        desc = self.entity_description
        raw_int = int(round(value / desc.scale))
        _LOGGER.info(
            "%s: Setting parameter %s to %s (raw register: 0x%04X, val: %s)",
            self.coordinator.name,
            desc.key,
            value,
            desc.reg_addr,
            raw_int,
        )

        is_v2 = getattr(self.coordinator._device, "uuid_tx", lambda: "fff2")() == "ff02"
        if is_v2:
            # V2 protocol: CID2_SetPara (0x49)
            # data: [para_index (1 byte), val_high, val_low]
            cmd_data = bytes([desc.v2_para_idx]) + raw_int.to_bytes(2, "big", signed=False)
            success = await self.coordinator.async_write_v2_command(0x49, cmd_data)
        else:
            # V3 Modbus: Function 0x06 to reg_addr
            success = await self.coordinator.async_write_modbus_register(desc.reg_addr, raw_int)

        if success:
            self._current_value = value
            self.coordinator._cached_params[desc.key] = value
            if self.coordinator.data is not None:
                self.coordinator.data[desc.key] = value
            self.async_write_ha_state()

