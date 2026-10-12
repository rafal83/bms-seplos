"""Switch platform for Seplos BMS integration."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, kw_only=True)
class SeplosBMSSwitchDescription:
    """Description of a Seplos BMS switch."""

    key: str
    name: str
    icon: str
    is_bit_param: bool = False
    byte_idx: int = 0
    bit_idx: int = 0
    default_on: bool = True


# Matériel & MOSFET switches
MOSFET_SWITCHES: tuple[SeplosBMSSwitchDescription, ...] = (
    SeplosBMSSwitchDescription(
        key="chrg_mosfet",
        name="Interrupteur Charge (Charge MOSFET)",
        icon="mdi:battery-charging",
        default_on=True,
    ),
    SeplosBMSSwitchDescription(
        key="dischrg_mosfet",
        name="Interrupteur Décharge (Discharge MOSFET)",
        icon="mdi:battery-arrow-down",
        default_on=True,
    ),
    SeplosBMSSwitchDescription(
        key="balancer_active",
        name="Équilibrage actif (Balancer)",
        icon="mdi:scale-balance",
        default_on=False,
    ),
    SeplosBMSSwitchDescription(
        key="heater_active",
        name="Chauffage batterie (Heater)",
        icon="mdi:radiator",
        default_on=False,
    ),
)

# Configuration Function Switches (Activer / Désactiver les alarmes et protections)
FUNCTION_SWITCHES: tuple[SeplosBMSSwitchDescription, ...] = (
    # Byte 1: Tensions cellules et pack
    SeplosBMSSwitchDescription(
        key="switch_cell_ov_alarm",
        name="Activer alarme surtension cellule",
        icon="mdi:bell-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=0,
    ),
    SeplosBMSSwitchDescription(
        key="switch_cell_ov_protect",
        name="Activer protection surtension cellule",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=1,
    ),
    SeplosBMSSwitchDescription(
        key="switch_cell_uv_alarm",
        name="Activer alarme sous-tension cellule",
        icon="mdi:bell-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=2,
    ),
    SeplosBMSSwitchDescription(
        key="switch_cell_uv_protect",
        name="Activer protection sous-tension cellule",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=3,
    ),
    SeplosBMSSwitchDescription(
        key="switch_pack_ov_alarm",
        name="Activer alarme surtension pack",
        icon="mdi:bell-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=4,
    ),
    SeplosBMSSwitchDescription(
        key="switch_pack_ov_protect",
        name="Activer protection surtension pack",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=5,
    ),
    SeplosBMSSwitchDescription(
        key="switch_pack_uv_alarm",
        name="Activer alarme sous-tension pack",
        icon="mdi:bell-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=6,
    ),
    SeplosBMSSwitchDescription(
        key="switch_pack_uv_protect",
        name="Activer protection sous-tension pack",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=1,
        bit_idx=7,
    ),
    # Byte 2: Températures charge & décharge
    SeplosBMSSwitchDescription(
        key="switch_chrg_ot_warn",
        name="Activer alarme surchauffe charge",
        icon="mdi:thermometer-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=0,
    ),
    SeplosBMSSwitchDescription(
        key="switch_chrg_ot_protect",
        name="Activer protection surchauffe charge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=1,
    ),
    SeplosBMSSwitchDescription(
        key="switch_chrg_ut_warn",
        name="Activer alarme gel/froid charge",
        icon="mdi:snowflake-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=2,
    ),
    SeplosBMSSwitchDescription(
        key="switch_chrg_ut_protect",
        name="Activer protection froid charge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=3,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_ot_warn",
        name="Activer alarme surchauffe décharge",
        icon="mdi:thermometer-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=4,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_ot_protect",
        name="Activer protection surchauffe décharge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=5,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_ut_warn",
        name="Activer alarme froid décharge",
        icon="mdi:snowflake-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=6,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_ut_protect",
        name="Activer protection froid décharge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=2,
        bit_idx=7,
    ),
    # Byte 4: Surintensité & court-circuit
    SeplosBMSSwitchDescription(
        key="switch_chrg_oc_warn",
        name="Activer alarme surintensité charge",
        icon="mdi:flash-alert",
        is_bit_param=True,
        byte_idx=4,
        bit_idx=0,
    ),
    SeplosBMSSwitchDescription(
        key="switch_chrg_oc_protect",
        name="Activer protection surintensité charge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=4,
        bit_idx=1,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_oc_warn",
        name="Activer alarme surintensité décharge",
        icon="mdi:flash-alert",
        is_bit_param=True,
        byte_idx=4,
        bit_idx=2,
    ),
    SeplosBMSSwitchDescription(
        key="switch_dischrg_oc_protect",
        name="Activer protection surintensité décharge",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=4,
        bit_idx=3,
    ),
    SeplosBMSSwitchDescription(
        key="switch_short_circuit_protect",
        name="Activer protection court-circuit",
        icon="mdi:shield-alert",
        is_bit_param=True,
        byte_idx=4,
        bit_idx=5,
    ),
    # Byte 6: Équilibrage charge & statique
    SeplosBMSSwitchDescription(
        key="switch_charge_balance_func",
        name="Activer fonction équilibrage en charge",
        icon="mdi:scale-balance",
        is_bit_param=True,
        byte_idx=6,
        bit_idx=0,
    ),
    SeplosBMSSwitchDescription(
        key="switch_static_balance_func",
        name="Activer fonction équilibrage au repos",
        icon="mdi:scale-balance",
        is_bit_param=True,
        byte_idx=6,
        bit_idx=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Seplos BMS switches."""
    coordinator: SeplosBMSCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SeplosBMSSwitch(coordinator, desc)
        for desc in MOSFET_SWITCHES + FUNCTION_SWITCHES
    ]
    async_add_entities(entities)


class SeplosBMSSwitch(CoordinatorEntity[SeplosBMSCoordinator], SwitchEntity):
    """Representation of a Seplos BMS controllable switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SeplosBMSCoordinator,
        desc: SeplosBMSSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._desc = desc
        self._key = desc.key
        self._attr_translation_key = self._key
        self._attr_name = desc.name
        self._attr_icon = desc.icon
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_unique_id = f"{coordinator.address}_{self._key}"
        self._attr_device_info = coordinator.device_info
        self._current_state: bool | None = None

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        if self.coordinator.data and self._key in self.coordinator.data:
            return bool(self.coordinator.data.get(self._key, False))
        if self._current_state is not None:
            return self._current_state
        return self._desc.default_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._desc.is_bit_param:
            success = await self.coordinator.async_set_bit_param(
                self._desc.byte_idx, self._desc.bit_idx, True, self._key
            )
        else:
            success = await self.coordinator.async_set_switch(self._key, True)

        if success:
            self._current_state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._desc.is_bit_param:
            success = await self.coordinator.async_set_bit_param(
                self._desc.byte_idx, self._desc.bit_idx, False, self._key
            )
        else:
            success = await self.coordinator.async_set_switch(self._key, False)

        if success:
            self._current_state = False
            self.async_write_ha_state()
