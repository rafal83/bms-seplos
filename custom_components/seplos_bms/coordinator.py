"""DataUpdateCoordinator for the Seplos BMS integration."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import timedelta
from itertools import islice
import logging
from time import monotonic
from typing import Any

from aiobmsble import BMSSample
from aiobmsble.basebms import BaseBMS
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_last_service_info,
)
from homeassistant.components.bluetooth.const import DOMAIN as BLUETOOTH_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDRESS,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SeplosBMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Seplos BMS data safely without overloading BLE."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        bms_device: BaseBMS,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.address = entry.data.get(CONF_ADDRESS, ble_device.address)
        self.device_name = entry.data.get(CONF_NAME, entry.title or DEFAULT_NAME)
        self._device: BaseBMS = bms_device
        self._mac = ble_device.address
        self._stale: bool = False
        self._link_q: deque[bool] = deque([False], maxlen=100)
        self._cached_params: dict[str, Any] = {}
        self._params_loaded: bool = False

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({self.address})",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
            config_entry=entry,
        )

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac), (BLUETOOTH_DOMAIN, self._mac)},
            connections={(CONNECTION_BLUETOOTH, self._mac)},
            name=self.device_name,
            manufacturer=self._device.INFO.get("default_manufacturer", "Seplos"),
            model=self._device.INFO.get("default_model", "Smart BMS"),
        )

        if service_info := async_last_service_info(
            self.hass, address=self._mac, connectable=True
        ):
            _LOGGER.debug("%s: Initial advertisement: %s", self.name, service_info.as_dict())

    @property
    def rssi(self) -> int | None:
        """Return RSSI value for target BMS."""
        service_info: BluetoothServiceInfoBleak | None = async_last_service_info(
            self.hass, address=self._mac, connectable=True
        )
        return service_info.rssi if service_info else None

    @property
    def link_quality(self) -> int:
        """Return percentage of successful BMS reads out of the last 100 attempts."""
        return self._link_q.count(True) * 100 // len(self._link_q)

    def invalidate_param_cache(self) -> None:
        """Invalidate parameter cache to force re-reading from BMS on next update."""
        self._params_loaded = False

    def _device_stale(self) -> bool:
        """Check if the connection has become stale and needs a clean reset."""
        if self._link_q[-1]:
            self._stale = False
        elif (
            not self._stale
            and self.link_quality <= 10
            and list(islice(reversed(self._link_q), 10)) == [False] * 10
        ):
            rssi = self.rssi
            _LOGGER.error(
                "%s: Seplos BMS is stale, triggering reconnect%s!",
                self.name,
                f", check signal strength ({rssi} dBm)" if rssi is not None else "",
            )
            self._stale = True

        return self._stale

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and disconnect safely."""
        _LOGGER.debug("Shutting down Seplos BMS coordinator (%s)", self.name)
        await super().async_shutdown()
        try:
            await self._device.disconnect()
        except Exception as err:
            _LOGGER.debug("Error disconnecting during shutdown of %s: %s", self.address, err)

    async def _async_setup(self) -> None:
        """Fetch static device information during initial setup."""
        try:
            bms_info = await self._device.device_info()
            if bms_info:
                self.device_info.update(
                    DeviceInfo(
                        name=bms_info.get("name") or self.device_name,
                        manufacturer=bms_info.get("manufacturer")
                        or self._device.INFO.get("default_manufacturer", "Seplos"),
                        model=bms_info.get("model")
                        or self._device.INFO.get("default_model", "Smart BMS"),
                        sw_version=bms_info.get("sw_version") or bms_info.get("fw_version"),
                        hw_version=bms_info.get("hw_version"),
                        model_id=bms_info.get("model_id"),
                        serial_number=bms_info.get("serial_number"),
                    )
                )
        except Exception as err:
            _LOGGER.debug("Could not read device info for %s: %s", self.address, err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Seplos BMS via aiobmsble."""
        _LOGGER.debug("%s: BMS data update started", self.name)

        if self._device_stale():
            await self._device.disconnect(reset=True)

        start = monotonic()
        update_interval_sec = self.update_interval.total_seconds() if self.update_interval else DEFAULT_SCAN_INTERVAL

        try:
            # Note: We intentionally do NOT wrap this in asyncio.timeout.
            # aiobmsble manages its own internal timeouts. Wrapping in asyncio.timeout
            # cancels Bleak mid-flight and crashes the Linux/BlueZ BLE stack.
            raw_sample: BMSSample | None = await self._device.async_update()
            if not raw_sample:
                raise UpdateFailed(f"Aucune donnée valide reçue du BMS {self.address}")

        except TimeoutError as err:
            _LOGGER.warning(
                "%s: Timeout Bluetooth. Vérifiez qu'aucune application mobile "
                "(ex: EN BMS / bms_flutter) n'est activement connectée en même temps à la batterie.",
                self.name,
            )
            raise UpdateFailed(f"Timeout Bluetooth avec {self.address}") from err

        except (BleakError, EOFError) as err:
            rssi = self.rssi
            _LOGGER.warning(
                "%s: Erreur communication BLE: %s (RSSI: %s dBm)",
                self.name,
                err,
                rssi if rssi is not None else "--",
            )
            raise UpdateFailed(f"Erreur Bluetooth avec {self.address}: {err}") from err

        except Exception as err:
            _LOGGER.error("%s: Erreur inattendue: %s", self.name, err)
            raise UpdateFailed(f"Erreur inattendue avec {self.address}: {err}") from err

        finally:
            elapsed = monotonic() - start
            slots = 1 + int(elapsed / max(update_interval_sec, 1))
            self._link_q.extend([False] * slots)

        self._link_q[-1] = True  # Mark this attempt as successful

        processed = self._process_sample(raw_sample)

        # Fusionner les paramètres de configuration déjà en cache
        processed.update(self._cached_params)

        # Lire la configuration réelle (SFA et SPA) directement depuis le BMS si pas encore chargée
        if not self._params_loaded:
            try:
                bms_params = await self._async_fetch_bms_parameters()
                if bms_params:
                    self._cached_params.update(bms_params)
                    processed.update(bms_params)
                    self._params_loaded = True
                    _LOGGER.info(
                        "%s: Configuration réelle chargée depuis la mémoire du BMS (%d paramètres)",
                        self.name,
                        len(bms_params),
                    )
            except Exception as err:
                _LOGGER.warning(
                    "%s: Impossible de lire la configuration du BMS au démarrage: %s",
                    self.name,
                    err,
                )

        _LOGGER.debug("%s: BMS data update successful: %s", self.name, processed)
        return processed

    def _process_sample(self, sample: BMSSample) -> dict[str, Any]:
        """Normalize sample data into structured dictionary."""
        data: dict[str, Any] = dict(sample)

        # Si le BMS est V3, les données de pack peuvent être dans packs[0]
        packs = data.get("packs")
        if packs and isinstance(packs, list) and len(packs) > 0:
            first_pack = packs[0]
            if isinstance(first_pack, dict):
                for k, v in first_pack.items():
                    if k not in data or data[k] is None:
                        data[k] = v

        # Puissance (W)
        voltage = data.get("voltage")
        current = data.get("current")
        if voltage is not None and current is not None:
            data["power"] = round(float(voltage) * float(current), 1)
        else:
            data["power"] = None

        # Statistiques des cellules
        cell_voltages: list[float] = data.get("cell_voltages", [])
        if cell_voltages:
            valid_cells = [float(v) for v in cell_voltages if v > 0]
            if valid_cells:
                min_v = min(valid_cells)
                max_v = max(valid_cells)
                data["min_cell_voltage"] = round(min_v, 3)
                data["max_cell_voltage"] = round(max_v, 3)
                data["cell_voltage_delta"] = round((max_v - min_v) * 1000, 1)  # mV
                data["min_cell_number"] = valid_cells.index(min_v) + 1
                data["max_cell_number"] = valid_cells.index(max_v) + 1
            data["cell_count"] = len(cell_voltages)

        # Températures détaillées
        temp_values = data.get("temp_values")
        if isinstance(temp_values, list) and temp_values:
            temps: list[float] = []
            for idx, t in enumerate(temp_values):
                val: float | None = None
                sensor_type = None
                if hasattr(t, "value"):
                    val = round(float(t.value), 1)
                    sensor_type = getattr(t, "type", None)
                elif isinstance(t, (int, float)):
                    val = round(float(t), 1)
                elif isinstance(t, dict) and "value" in t:
                    val = round(float(t["value"]), 1)

                if val is not None:
                    # Enregistrer par capteur individuel
                    # Convention Seplos : 4 premiers = sondes cellules T1..T4, puis T_ambiante, puis T_mosfet
                    if idx == 0:
                        data["temp_cell_1"] = val
                    elif idx == 1:
                        data["temp_cell_2"] = val
                    elif idx == 2:
                        data["temp_cell_3"] = val
                    elif idx == 3:
                        data["temp_cell_4"] = val
                    elif idx == 4 or (sensor_type and getattr(sensor_type, "name", "") == "AMBIENT"):
                        data["temp_ambient"] = val
                    elif idx == 5 or (sensor_type and getattr(sensor_type, "name", "") == "MOSFET"):
                        data["temp_mosfet"] = val

                    # Pour les sondes cellules (les 4 premières ou type CELL)
                    if idx < 4:
                        temps.append(val)

            if temps:
                data["temp_cell_min"] = min(temps)
                data["temp_cell_max"] = max(temps)
                data["temp_cell_avg"] = round(sum(temps) / len(temps), 1)

        # Tension Bus (Bus Voltage)
        if "bus_voltage" not in data or data["bus_voltage"] is None:
            data["bus_voltage"] = data.get("voltage")

        # États binaires
        data["charging_allowed"] = data.get("chrg_mosfet", False)
        data["discharging_allowed"] = data.get("dischrg_mosfet", False)
        data["balancer_active"] = bool(data.get("balancer", 0))
        data["heater_active"] = bool(data.get("heater", False))

        # Alarme générale & alarmes binaires détaillées
        problem_code = data.get("problem_code", 0)
        data["has_problem"] = bool(problem_code)
        data["alarm_voltage_low"] = bool(problem_code & 0x0001)
        data["alarm_voltage_high"] = bool(problem_code & 0x0002)
        data["alarm_temp_low"] = bool(problem_code & 0x0004)
        data["alarm_temp_high"] = bool(problem_code & 0x0008)
        data["alarm_charge_overcurrent"] = bool(problem_code & 0x0010)
        data["alarm_discharge_overcurrent"] = bool(problem_code & 0x0020)
        data["alarm_cell_imbalance"] = bool(problem_code & 0x0040)
        data["alarm_short_circuit"] = bool(problem_code & 0x0080)

        return data

    async def async_write_modbus_register(self, reg_addr: int, value: int, device_id: int = 0x00) -> bool:
        """Write a single 16-bit register using Modbus Function 0x06."""
        # Frame: [device_id, 0x06, reg_high, reg_low, val_high, val_low, crc_low, crc_high]
        payload = bytearray([device_id, 0x06])
        payload.extend(reg_addr.to_bytes(2, "big"))
        payload.extend(value.to_bytes(2, "big", signed=False))
        from aiobmsble.basebms import crc_modbus
        crc = crc_modbus(payload)
        payload.extend(crc.to_bytes(2, "little"))

        _LOGGER.debug(
            "%s: Writing Modbus register 0x%04X = %s (0x%04X), frame: %s",
            self.name,
            reg_addr,
            value,
            value,
            payload.hex(" "),
        )
        return await self._async_send_raw(bytes(payload))

    async def async_write_v2_command(self, cmd: int, data: bytes = b"", address: int = 0x00) -> bool:
        """Write a command using Seplos V2 ASCII protocol."""
        # Seplos V2 frame format: [HEAD (~), CMD_VER (0x10), address, 0x46, cmd, len_high, len_low, ...data, crc_high, crc_low, TAIL (\r)]
        from aiobmsble.basebms import crc_xmodem
        frame = bytearray([0x7E, 0x10, address, 0x46, cmd])
        frame.extend(len(data).to_bytes(2, "big", signed=False))
        frame.extend(data)
        crc = crc_xmodem(frame[1:])
        frame.extend(crc.to_bytes(2, "big"))
        frame.append(0x0D)

        _LOGGER.debug(
            "%s: Writing V2 command 0x%02X, frame: %s",
            self.name,
            cmd,
            frame.hex(" "),
        )
        return await self._async_send_raw(bytes(frame))

    async def async_set_switch(self, switch_key: str, state: bool) -> bool:
        """Set state of a MOSFET or function switch."""
        is_v2 = getattr(self._device, "uuid_tx", lambda: "fff2")() == "ff02"
        _LOGGER.info(
            "%s: Setting switch '%s' to %s (protocol: %s)",
            self.name,
            switch_key,
            "ON" if state else "OFF",
            "V2" if is_v2 else "V3",
        )

        if is_v2:
            # Seplos V2: TeleCtrl CID2 = 0x47
            # Byte 0 bit 0: Discharge, bit 1: Charge, bit 3: Heater
            bit_mask = 0x01 if switch_key == "dischrg_mosfet" else (
                0x02 if switch_key == "chrg_mosfet" else (
                    0x08 if switch_key == "heater_active" else 0x04
                )
            )
            cmd_data = bytes([bit_mask if state else 0x00])
            success = await self.async_write_v2_command(0x47, cmd_data)
        else:
            # Seplos V3: Write to SCA (0x150D offset) or coil control
            # Using Modbus function 0x06
            reg_map = {
                "chrg_mosfet": 0x1510,
                "dischrg_mosfet": 0x1511,
                "balancer_active": 0x1512,
                "heater_active": 0x1513,
            }
            reg_addr = reg_map.get(switch_key, 0x1510)
            val = 1 if state else 0
            success = await self.async_write_modbus_register(reg_addr, val)

        # Update local state immediately and request refresh
        if self.data and switch_key in self.data:
            self.data[switch_key] = state
            if switch_key == "chrg_mosfet":
                self.data["charging_allowed"] = state
            elif switch_key == "dischrg_mosfet":
                self.data["discharging_allowed"] = state
            elif switch_key == "heater_active":
                self.data["heater_active"] = state
            self.async_update_listeners()

        self.hass.async_create_task(self.async_request_refresh())
        return success

    async def async_set_bit_param(
        self,
        coil_addr: int,
        state: bool,
        key: str,
        v2_byte_idx: int = 0,
        v2_bit_idx: int = 0,
    ) -> bool:
        """Set a configuration function switch / bit parameter in BMS."""
        is_v2 = getattr(self._device, "uuid_tx", lambda: "fff2")() == "ff02"
        _LOGGER.info(
            "%s: Setting function switch '%s' (coil 0x%04X) to %s",
            self.name,
            key,
            coil_addr,
            "ON" if state else "OFF",
        )

        if is_v2:
            # Seplos V2: CID2_SetPara (0x49)
            val = 1 if state else 0
            cmd_data = bytes([v2_byte_idx, v2_bit_idx, val])
            success = await self.async_write_v2_command(0x49, cmd_data)
        else:
            # Seplos V3: Write Single Coil (0x05) to coil_addr
            val = 0xFF00 if state else 0x0000
            payload = bytearray([0x00, 0x05])
            payload.extend(coil_addr.to_bytes(2, "big"))
            payload.extend(val.to_bytes(2, "big"))
            from aiobmsble.basebms import crc_modbus
            crc = crc_modbus(payload)
            payload.extend(crc.to_bytes(2, "little"))
            success = await self._async_send_raw(bytes(payload))

        if success:
            self._cached_params[key] = state
            if self.data is not None:
                self.data[key] = state
            self.async_update_listeners()

        return success

    async def async_send_modbus_query(
        self,
        query_frame: bytes,
        expected_func: int,
        timeout: float = 3.5,
    ) -> bytes | None:
        """Send a Modbus query and wait for the response frame holding BLE op lock."""
        if not self._device.is_connected:
            try:
                await self._device._connect()
            except Exception as err:
                _LOGGER.warning("%s: Non connecté pour envoyer la requête: %s", self.name, err)
                return None

        async with self._device._op_lock:
            rx_buf = bytearray()
            rx_done = asyncio.Event()
            orig_handler = self._device._notification_handler

            def temp_handler(sender: Any, data: bytearray | bytes) -> None:
                rx_buf.extend(data)
                # Format réponse Modbus : [slave, func, byte_count, ...data, crc_l, crc_h]
                if len(rx_buf) >= 3:
                    if rx_buf[1] == expected_func:
                        byte_count = rx_buf[2]
                        expected_len = byte_count + 5  # slave(1) + func(1) + count(1) + data + crc(2)
                        if len(rx_buf) >= expected_len:
                            rx_done.set()
                    elif rx_buf[1] & 0x80:
                        # Trame d'erreur Modbus : [slave, func | 0x80, err_code, crc_l, crc_h]
                        if len(rx_buf) >= 5:
                            rx_done.set()

            self._device._notification_handler = temp_handler
            try:
                tx_uuid = self._device.uuid_tx()
                await self._device._client.write_gatt_char(tx_uuid, query_frame, response=False)
                await asyncio.wait_for(rx_done.wait(), timeout=timeout)
            except TimeoutError:
                _LOGGER.debug("%s: Timeout requête Modbus: %s", self.name, query_frame.hex(" "))
                return None
            except Exception as err:
                _LOGGER.debug("%s: Erreur envoi requête Modbus %s: %s", self.name, query_frame.hex(" "), err)
                return None
            finally:
                self._device._notification_handler = orig_handler

            # Valider la trame reçue
            if len(rx_buf) >= 5 and rx_buf[1] == expected_func:
                from aiobmsble.basebms import crc_modbus
                expected_len = rx_buf[2] + 5
                frame = bytes(rx_buf[:expected_len])
                calc_crc = crc_modbus(frame[:-2])
                resp_crc = int.from_bytes(frame[-2:], "little")
                if calc_crc == resp_crc:
                    return frame
                _LOGGER.warning("%s: Erreur CRC Modbus reçu", self.name)
            return None

    async def _async_fetch_bms_parameters(self) -> dict[str, Any]:
        """Read configuration parameters & function switches directly from BMS memory."""
        is_v2 = getattr(self._device, "uuid_tx", lambda: "fff2")() == "ff02"
        params: dict[str, Any] = {}

        if is_v2:
            return params

        # Pour Seplos V3 Modbus RTU
        _LOGGER.debug("%s: Lecture des tables SFA et SPA du BMS...", self.name)
        from aiobmsble.basebms import crc_modbus

        # 1. Lecture SFA (Coils à l'adresse 0x1400, 80 bobines = 10 octets)
        sfa_query = bytearray([0x00, 0x01, 0x14, 0x00, 0x00, 0x50])
        sfa_query.extend(crc_modbus(sfa_query).to_bytes(2, "little"))
        sfa_resp = await self.async_send_modbus_query(bytes(sfa_query), expected_func=0x01, timeout=3.0)

        if sfa_resp and len(sfa_resp) >= 15:
            coil_data = sfa_resp[3:13]
            _LOGGER.debug("%s: Bobines SFA lues: %s", self.name, coil_data.hex(" "))
            from .switch import FUNCTION_SWITCHES

            for desc in FUNCTION_SWITCHES:
                if desc.is_bit_param:
                    offset = desc.coil_addr - 0x1400
                    if 0 <= offset < len(coil_data) * 8:
                        byte_pos = offset // 8
                        bit_pos = offset % 8
                        is_active = bool(coil_data[byte_pos] & (1 << bit_pos))
                        params[desc.key] = is_active

        # 2. Lecture SPA Bloc 1 (0x1300, 32 registres : tensions et courants)
        spa1_query = bytearray([0x00, 0x04, 0x13, 0x00, 0x00, 0x20])
        spa1_query.extend(crc_modbus(spa1_query).to_bytes(2, "little"))
        spa1_resp = await self.async_send_modbus_query(bytes(spa1_query), expected_func=0x04, timeout=3.0)
        if not spa1_resp:
            spa1_query[1] = 0x03
            spa1_query[6:] = crc_modbus(spa1_query[:6]).to_bytes(2, "little")
            spa1_resp = await self.async_send_modbus_query(bytes(spa1_query), expected_func=0x03, timeout=3.0)

        func_code = spa1_resp[1] if spa1_resp else 0x04
        if spa1_resp and len(spa1_resp) >= 69:
            spa1_data = spa1_resp[3:-2]
            def get_u16(offset: int) -> int:
                idx = offset * 2
                return int.from_bytes(spa1_data[idx:idx + 2], "big", signed=False)

            params["pack_ovp"] = round(get_u16(0x05) * 0.01, 2)
            params["pack_uvp"] = round(get_u16(0x09) * 0.01, 2)
            params["cell_ovpr"] = round(get_u16(0x0C) * 0.001, 3)
            params["cell_ovp"] = round(get_u16(0x0D) * 0.001, 3)
            params["cell_uvpr"] = round(get_u16(0x10) * 0.001, 3)
            params["cell_uvp"] = round(get_u16(0x11) * 0.001, 3)
            params["charge_ocp"] = round(get_u16(0x17) * 0.01, 1)
            params["discharge_ocp"] = round(get_u16(0x1D) * 0.01, 1)

        # 3. Lecture SPA Bloc 2 (0x1330, 30 registres : températures)
        spa2_query = bytearray([0x00, func_code, 0x13, 0x30, 0x00, 0x1E])
        spa2_query.extend(crc_modbus(spa2_query).to_bytes(2, "little"))
        spa2_resp = await self.async_send_modbus_query(bytes(spa2_query), expected_func=func_code, timeout=3.0)

        if spa2_resp and len(spa2_resp) >= 65:
            spa2_data = spa2_resp[3:-2]
            def get_s16(offset: int) -> int:
                idx = offset * 2
                return int.from_bytes(spa2_data[idx:idx + 2], "big", signed=True)

            params["charge_temp_high_alarm"] = round(get_s16(0x00) * 0.1, 1)
            params["charge_temp_high_protect"] = round(get_s16(0x02) * 0.1, 1)
            params["charge_temp_low_protect"] = round(get_s16(0x06) * 0.1, 1)
            params["discharge_temp_high_protect"] = round(get_s16(0x0A) * 0.1, 1)
            params["discharge_temp_low_protect"] = round(get_s16(0x0E) * 0.1, 1)
            params["cell_heating_temp"] = round(get_s16(0x1C) * 0.1, 1)

        # 4. Lecture SPA Bloc 3 (0x1350, 10 registres : équilibrage et capacité)
        spa3_query = bytearray([0x00, func_code, 0x13, 0x50, 0x00, 0x0A])
        spa3_query.extend(crc_modbus(spa3_query).to_bytes(2, "little"))
        spa3_resp = await self.async_send_modbus_query(bytes(spa3_query), expected_func=func_code, timeout=3.0)

        if spa3_resp and len(spa3_resp) >= 25:
            spa3_data = spa3_resp[3:-2]
            def get_u16_3(offset: int) -> int:
                idx = offset * 2
                return int.from_bytes(spa3_data[idx:idx + 2], "big", signed=False)

            params["equalization_opening_voltage"] = round(get_u16_3(0x00) * 0.001, 3)
            params["equalization_opening_delta"] = round(get_u16_3(0x01) * 1.0, 0)
            params["rated_capacity"] = round(get_u16_3(0x08) * 0.01, 1)

        return params

    async def _async_send_raw(self, payload: bytes) -> bool:
        """Safely send raw BLE frame holding op lock."""
        try:
            await self._device._connect()
        except Exception as err:
            _LOGGER.error("%s: Connect failed before sending command: %s", self.name, err)
            return False

        async with self._device._op_lock:
            try:
                tx_uuid = self._device.uuid_tx()
                await self._device._client.write_gatt_char(tx_uuid, payload, response=False)
                _LOGGER.debug("%s: BLE command sent successfully: %s", self.name, payload.hex(" "))
                return True
            except Exception as err:
                _LOGGER.error("%s: Failed to send BLE command %s: %s", self.name, payload.hex(" "), err)
                return False
