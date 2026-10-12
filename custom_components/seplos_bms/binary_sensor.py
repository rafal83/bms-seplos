"""Binary sensor platform for Seplos BMS integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_BITS, DOMAIN
from .coordinator import SeplosBMSCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SeplosBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Seplos BMS binary sensor entities."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[SeplosBinarySensorEntityDescription, ...] = (
    SeplosBinarySensorEntityDescription(
        key="charging_allowed",
        translation_key="charging_allowed",
        name="Charge autorisée (Charge MOSFET)",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda data: data.get("charging_allowed"),
    ),
    SeplosBinarySensorEntityDescription(
        key="discharging_allowed",
        translation_key="discharging_allowed",
        name="Décharge autorisée (Discharge MOSFET)",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda data: data.get("discharging_allowed"),
    ),
    SeplosBinarySensorEntityDescription(
        key="balancer_active",
        translation_key="balancer_active",
        name="Équilibrage actif (Balancer)",
        icon="mdi:scale-balance",
        is_on_fn=lambda data: data.get("balancer_active"),
    ),
    SeplosBinarySensorEntityDescription(
        key="heater_active",
        translation_key="heater_active",
        name="Chauffage actif (Heater)",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda data: data.get("heater_active"),
    ),
    SeplosBinarySensorEntityDescription(
        key="has_problem",
        translation_key="has_problem",
        name="Alarme / Problème (Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("has_problem"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_voltage_low",
        translation_key="alarm_voltage_low",
        name="Alarme sous-tension (Voltage Low Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_voltage_low"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_voltage_high",
        translation_key="alarm_voltage_high",
        name="Alarme surtension (Voltage High Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_voltage_high"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_temp_low",
        translation_key="alarm_temp_low",
        name="Alarme basse température (Temp Low Alarm)",
        device_class=BinarySensorDeviceClass.COLD,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_temp_low"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_temp_high",
        translation_key="alarm_temp_high",
        name="Alarme haute température (Temp High Alarm)",
        device_class=BinarySensorDeviceClass.HEAT,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_temp_high"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_charge_overcurrent",
        translation_key="alarm_charge_overcurrent",
        name="Alarme surintensité charge (Charge Overcurrent Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_charge_overcurrent"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_discharge_overcurrent",
        translation_key="alarm_discharge_overcurrent",
        name="Alarme surintensité décharge (Discharge Overcurrent Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_discharge_overcurrent"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_cell_imbalance",
        translation_key="alarm_cell_imbalance",
        name="Alarme déséquilibre cellules (Cell Imbalance Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_cell_imbalance"),
    ),
    SeplosBinarySensorEntityDescription(
        key="alarm_short_circuit",
        translation_key="alarm_short_circuit",
        name="Alarme court-circuit (Short Circuit Alarm)",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: data.get("alarm_short_circuit"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS binary sensor platform."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        SeplosBMSBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class SeplosBMSBinarySensor(
    CoordinatorEntity[SeplosBMSCoordinator], BinarySensorEntity
):
    """Representation of a Seplos BMS binary sensor."""

    entity_description: SeplosBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        description: SeplosBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return active alarms as attributes if problem sensor."""
        if self.entity_description.key == "has_problem":
            problem_code = self.coordinator.data.get("problem_code", 0)
            active_alarms = [
                desc
                for bit, desc in ALARM_BITS.items()
                if problem_code and (problem_code & bit)
            ]
            return {
                "problem_code_raw": hex(problem_code) if problem_code else 0,
                "active_alarms": active_alarms,
            }
        return None

