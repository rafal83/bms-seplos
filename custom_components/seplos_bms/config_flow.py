"""Config flow for Seplos BMS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_process_meldfiles,
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
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
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


def is_seplos_device(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Check if the discovered device is a Seplos BMS."""
    name = (discovery_info.name or "").strip()
    if name.startswith(("SP", "BP", "XZHX", "CSY", "ST", "SmartBat")):
        return True

    uuids = [u.lower() for u in (discovery_info.service_uuids or [])]
    return (
        UUID_SERVICE_V2.lower() in uuids
        or UUID_SERVICE_V3.lower() in uuids
        or "0000ff00-0000-1000-8000-00805f9b34fb" in uuids
        or "0000fff0-0000-1000-8000-00805f9b34fb" in uuids
    )


class SeplosBMSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seplos BMS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEFAULT_NAME,
            "address": discovery_info.address,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or f"Seplos BMS ({self._discovery_info.address})",
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: self._discovery_info.name or DEFAULT_NAME,
                    CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, PROTOCOL_AUTO),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
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

            disc = self._discovered_devices.get(address)
            name = (disc.name if disc else None) or DEFAULT_NAME

            return self.async_create_entry(
                title=f"{name} ({address})",
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: name,
                    CONF_PROTOCOL: user_input.get(CONF_PROTOCOL, PROTOCOL_AUTO),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
            )

        # Discover devices currently advertising
        current_addresses = self._async_current_ids()
        self._discovered_devices = {}

        for disc in async_discovered_service_info(self.hass, connectable=True):
            if format_mac(disc.address) in current_addresses:
                continue
            if is_seplos_device(disc):
                self._discovered_devices[disc.address] = disc

        device_options = {
            address: f"{disc.name or 'Unknown'} ({address}) [RSSI: {disc.rssi} dBm]"
            for address, disc in self._discovered_devices.items()
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

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL,
                        self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

