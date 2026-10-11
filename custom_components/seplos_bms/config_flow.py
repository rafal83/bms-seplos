"""Config flow for Seplos BMS integration."""

from __future__ import annotations

import logging
from typing import Any

from aiobmsble.utils import bms_identify
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_ADDRESS,
    CONF_KEEP_ALIVE,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    CONF_TYPE,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PROTOCOL_AUTO,
    PROTOCOLS,
    UUID_SERVICE_V2,
    UUID_SERVICE_V3,
)

_LOGGER = logging.getLogger(__name__)


async def async_identify_seplos(
    discovery_info: BluetoothServiceInfoBleak,
) -> tuple[bool, str | None]:
    """Check if device is a Seplos BMS and identify module type."""
    # Try identifying via aiobmsble pattern matching first
    try:
        bms_class = await bms_identify(discovery_info.advertisement, discovery_info.address)
        if bms_class:
            bms_mod = str(bms_class.get_bms_module())
            if "seplos" in bms_mod.lower():
                return True, bms_mod
    except Exception as err:
        _LOGGER.debug("bms_identify failed for %s: %s", discovery_info.address, err)

    # Fallback to local name & service UUID checks
    name = (discovery_info.name or "").strip()
    uuids = [u.lower() for u in (discovery_info.service_uuids or [])]

    is_v2 = (
        name.startswith(("BP0", "BP1", "BP2"))
        or UUID_SERVICE_V2.lower() in uuids
        or "0000ff00-0000-1000-8000-00805f9b34fb" in uuids
    )
    if is_v2:
        return True, "aiobmsble.bms.seplos_v2_bms"

    is_v3 = (
        name.startswith(("SP", "BP", "XZHX", "CSY", "ST", "SmartBat"))
        or UUID_SERVICE_V3.lower() in uuids
        or "0000fff0-0000-1000-8000-00805f9b34fb" in uuids
    )
    if is_v3:
        return True, "aiobmsble.bms.seplos_bms"

    return False, None


class SeplosBMSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seplos BMS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, tuple[BluetoothServiceInfoBleak, str | None]] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        is_seplos, bms_type = await async_identify_seplos(discovery_info)
        if not is_seplos:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEFAULT_NAME,
            "address": discovery_info.address,
        }
        self.context["bms_type"] = bms_type
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            data: dict[str, Any] = {
                CONF_ADDRESS: self._discovery_info.address,
                CONF_NAME: self._discovery_info.name or DEFAULT_NAME,
                CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, PROTOCOL_AUTO),
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            }
            if bms_type := self.context.get("bms_type"):
                data[CONF_TYPE] = bms_type

            return self.async_create_entry(
                title=self._discovery_info.name or f"Seplos BMS ({self._discovery_info.address})",
                data=data,
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_PROTOCOL, default=PROTOCOL_AUTO): vol.In(PROTOCOLS),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=schema,
            description_placeholders={
                "name": self._discovery_info.name or DEFAULT_NAME,
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick or enter a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == "manual":
                return await self.async_step_manual()

            await self.async_set_unique_id(format_mac(address), raise_on_progress=False)
            self._abort_if_unique_id_configured()

            disc_entry = self._discovered_devices.get(address)
            disc = disc_entry[0] if disc_entry else None
            bms_type = disc_entry[1] if disc_entry else None
            name = (disc.name if disc else None) or DEFAULT_NAME

            data: dict[str, Any] = {
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, PROTOCOL_AUTO),
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            }
            if bms_type:
                data[CONF_TYPE] = bms_type

            return self.async_create_entry(
                title=f"{name} ({address})",
                data=data,
            )

        # Discover devices currently advertising
        current_addresses = self._async_current_ids()
        self._discovered_devices = {}

        for disc in async_discovered_service_info(self.hass, connectable=True):
            if format_mac(disc.address) in current_addresses:
                continue
            is_seplos, bms_type = await async_identify_seplos(disc)
            if is_seplos:
                self._discovered_devices[disc.address] = (disc, bms_type)

        device_options = {
            address: f"{disc.name or 'Unknown'} ({address}) [RSSI: {disc.rssi} dBm]"
            for address, (disc, _) in self._discovered_devices.items()
        }
        device_options["manual"] = "Saisie manuelle de l'adresse MAC (Manual Entry)"

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(device_options),
                vol.Optional(CONF_PROTOCOL, default=PROTOCOL_AUTO): vol.In(PROTOCOLS),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual entry of MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            await self.async_set_unique_id(format_mac(address), raise_on_progress=False)
            self._abort_if_unique_id_configured()

            name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME

            return self.async_create_entry(
                title=f"{name} ({address})",
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: name,
                    CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, PROTOCOL_AUTO),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_PROTOCOL, default=PROTOCOL_AUTO): vol.In(PROTOCOLS),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(
            step_id="manual",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SeplosBMSOptionsFlow(config_entry)


class SeplosBMSOptionsFlow(OptionsFlow):
    """Handle options flow for Seplos BMS."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_protocol = self.config_entry.options.get(
            CONF_PROTOCOL,
            self.config_entry.data.get(CONF_PROTOCOL, PROTOCOL_AUTO),
        )
        current_keep_alive = self.config_entry.options.get(
            CONF_KEEP_ALIVE,
            self.config_entry.data.get(CONF_KEEP_ALIVE, DEFAULT_KEEP_ALIVE),
        )
        current_scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_PROTOCOL, default=current_protocol): vol.In(PROTOCOLS),
                vol.Optional(CONF_KEEP_ALIVE, default=current_keep_alive): bool,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_scan_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
