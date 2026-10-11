"""Sensor platform for Seplos BMS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SeplosBMSCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SeplosSensorEntityDescription(SensorEntityDescription):
    """Class describing Seplos BMS sensor entities."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[SeplosSensorEntityDescription, ...] = (
    SeplosSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        name="Tension totale (Total Voltage)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda data: data.get("voltage"),
    ),
    SeplosSensorEntityDescription(
        key="current",
        translation_key="current",
        name="Courant (Current)",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda data: data.get("current"),
    ),
    SeplosSensorEntityDescription(
        key="power",
        translation_key="power",
        name="Puissance (Power)",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda data: data.get("power"),
    ),
    SeplosSensorEntityDescription(
        key="battery_level",
        translation_key="battery_level",
        name="Niveau de batterie (SOC)",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("battery_level"),
    ),
    SeplosSensorEntityDescription(
        key="battery_health",
        translation_key="battery_health",
        name="Santé de la batterie (SOH)",
        icon="mdi:heart-pulse",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("battery_health"),
    ),
    SeplosSensorEntityDescription(
        key="design_capacity",
        translation_key="design_capacity",
        name="Capacité nominale (Capacity)",
        icon="mdi:battery-heart-variant",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Ah",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("design_capacity"),
    ),
    SeplosSensorEntityDescription(
        key="cycle_charge",
        translation_key="cycle_charge",
        name="Capacité restante (Remaining Capacity)",
        icon="mdi:battery-charging-50",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="Ah",
        value_fn=lambda data: data.get("cycle_charge"),
    ),
    SeplosSensorEntityDescription(
        key="cycles",
        translation_key="cycles",
        name="Cycles de charge (Cycles)",
        icon="mdi:recycle-variant",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("cycles"),
    ),
    SeplosSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        name="Température moyenne (Avg Temperature)",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("temperature"),
    ),
    SeplosSensorEntityDescription(
        key="min_cell_voltage",
        translation_key="min_cell_voltage",
        name="Tension cellule min (Min Cell Voltage)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda data: data.get("min_cell_voltage"),
    ),
    SeplosSensorEntityDescription(
        key="max_cell_voltage",
        translation_key="max_cell_voltage",
        name="Tension cellule max (Max Cell Voltage)",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda data: data.get("max_cell_voltage"),
    ),
    SeplosSensorEntityDescription(
        key="cell_voltage_delta",
        translation_key="cell_voltage_delta",
        name="Écart cellules (Cell Delta)",
        icon="mdi:delta",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mV",
        value_fn=lambda data: data.get("cell_voltage_delta"),
    ),
    SeplosSensorEntityDescription(
        key="min_cell_number",
        translation_key="min_cell_number",
        name="Numéro cellule min (Min Cell #)",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("min_cell_number"),
    ),
    SeplosSensorEntityDescription(
        key="max_cell_number",
        translation_key="max_cell_number",
        name="Numéro cellule max (Max Cell #)",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("max_cell_number"),
    ),
    SeplosSensorEntityDescription(
        key="cell_count",
        translation_key="cell_count",
        name="Nombre de cellules (Cell Count)",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("cell_count"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS sensor platform."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        SeplosBMSSensor(coordinator, description) for description in SENSORS
    ]

    # Add individual cell voltage sensors
    cell_voltages: list[float] = coordinator.data.get("cell_voltages", [])
    num_cells = len(cell_voltages) if cell_voltages else 16
    for idx in range(num_cells):
        entities.append(SeplosCellVoltageSensor(coordinator, idx + 1))

    async_add_entities(entities)


class SeplosBMSSensor(CoordinatorEntity[SeplosBMSCoordinator], SensorEntity):
    """Representation of a Seplos BMS sensor."""

    entity_description: SeplosSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        description: SeplosSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> Any:
        """Return native value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class SeplosCellVoltageSensor(CoordinatorEntity[SeplosBMSCoordinator], SensorEntity):
    """Sensor representing individual cell voltage."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_icon = "mdi:battery-outline"

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        cell_index: int,
    ) -> None:
        """Initialize cell voltage sensor."""
        super().__init__(coordinator)
        self.cell_index = cell_index
        self._attr_name = f"Tension cellule {cell_index} (Cell {cell_index} Voltage)"
        self._attr_unique_id = f"{coordinator.address}_cell_voltage_{cell_index}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        """Return the voltage of the cell."""
        cell_voltages: list[float] = self.coordinator.data.get("cell_voltages", [])
        if 0 <= self.cell_index - 1 < len(cell_voltages):
            val = cell_voltages[self.cell_index - 1]
            return round(val, 3) if val > 0 else None
        return None

