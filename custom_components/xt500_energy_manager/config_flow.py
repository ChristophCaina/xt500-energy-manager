"""Config flow for XT500 Energy Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_AUTO_DASHBOARD,
    CONF_AC_PV_POWER_ENTITY,
    CONF_AC_PV_SIGN,
    CONF_BATTERY_INPUT_POWER_ENTITY,
    CONF_BATTERY_OUTPUT_POWER_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_EXTERNAL_GRID_POWER_ENTITY,
    CONF_EXTERNAL_GRID_INVERT,
    CONF_GRID_PORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_INVERTER_SETPOINT_ENTITY,
    CONF_LOAD_DISCHARGE_LIMIT_ENTITY,
    CONF_LOAD_PORT_POWER_ENTITY,
    CONF_MAX_CHARGE_SOC_ENTITY,
    CONF_MIN_DISCHARGE_SOC_ENTITY,
    CONF_METER_SIGN,
    CONF_PV_POWER_ENTITY,
    CONF_SOC_ENTITY,
    CONF_XT500_DEVICE,
    DOMAIN,
    METER_IMPORT_POSITIVE,
    METER_SIGNS,
    PV_PRODUCTION_POSITIVE,
    PV_SIGNS,
)
from .entity_mapping import detect_xt500_entities


def _entity_selector(domain: str, *, multiple: bool = False) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    )


def _external_grid_schema(values: dict[str, Any]) -> dict:
    """An omitted optional source disables metering, including in options."""
    return {
        vol.Optional(CONF_EXTERNAL_GRID_POWER_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power")
        ),
        vol.Required(
            CONF_EXTERNAL_GRID_INVERT,
            default=values.get(CONF_EXTERNAL_GRID_INVERT, False),
        ): selector.BooleanSelector(),
    }


def _manual_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    values = defaults or {}

    def required(key: str, fallback: Any = None) -> vol.Required:
        if key in values:
            return vol.Required(key, default=values[key])
        if fallback is not None:
            return vol.Required(key, default=fallback)
        return vol.Required(key)

    def optional(key: str) -> vol.Optional:
        return vol.Optional(key)

    return vol.Schema(
        {
            vol.Optional(CONF_AUTO_DASHBOARD, default=values.get(CONF_AUTO_DASHBOARD, True)): selector.BooleanSelector(),
            **_external_grid_schema(values),
            required(CONF_SOC_ENTITY): _entity_selector("sensor"),
            required(CONF_PV_POWER_ENTITY): _entity_selector("sensor"),
            optional(CONF_AC_PV_POWER_ENTITY): _entity_selector("sensor"),
            required(CONF_GRID_POWER_ENTITY): _entity_selector("sensor"),
            required(CONF_GRID_PORT_POWER_ENTITY): _entity_selector("sensor"),
            required(CONF_LOAD_PORT_POWER_ENTITY): _entity_selector("sensor"),
            required(CONF_GRID_SETPOINT_ENTITY): _entity_selector("number"),
            required(CONF_INVERTER_SETPOINT_ENTITY): _entity_selector("number"),
            required(CONF_MAX_CHARGE_SOC_ENTITY): _entity_selector("number"),
            required(CONF_MIN_DISCHARGE_SOC_ENTITY): _entity_selector("number"),
            optional(CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY): _entity_selector("number"),
            optional(CONF_CHARGE_SOC_HYSTERESIS_ENTITY): _entity_selector("number"),
            optional(CONF_LOAD_DISCHARGE_LIMIT_ENTITY): _entity_selector("number"),
            optional(CONF_BATTERY_POWER_ENTITY): _entity_selector("sensor"),
            optional(CONF_BATTERY_INPUT_POWER_ENTITY): _entity_selector("sensor"),
            optional(CONF_BATTERY_OUTPUT_POWER_ENTITY): _entity_selector("sensor"),
            required(CONF_METER_SIGN, METER_IMPORT_POSITIVE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(METER_SIGNS),
                    translation_key="meter_sign",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            required(
                CONF_AC_PV_SIGN, PV_PRODUCTION_POSITIVE
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(PV_SIGNS),
                    translation_key="ac_pv_sign",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _automatic_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    values = defaults or {}
    ac_pv_marker = vol.Optional(CONF_AC_PV_POWER_ENTITY)
    schema: dict[vol.Marker, Any] = {
        vol.Optional(CONF_AUTO_DASHBOARD, default=values.get(CONF_AUTO_DASHBOARD, True)): selector.BooleanSelector(),
        **_external_grid_schema(values),
        vol.Required(CONF_XT500_DEVICE): selector.DeviceSelector(
            selector.DeviceSelectorConfig(integration="sunenergyxt")
        ),
        vol.Required(CONF_GRID_POWER_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power")
        ),
        ac_pv_marker: selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="power")
        ),
        vol.Required(
            CONF_METER_SIGN,
            default=values.get(CONF_METER_SIGN, METER_IMPORT_POSITIVE),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(METER_SIGNS),
                translation_key="meter_sign",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_AC_PV_SIGN,
            default=values.get(CONF_AC_PV_SIGN, PV_PRODUCTION_POSITIVE),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(PV_SIGNS),
                translation_key="ac_pv_sign",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
    return vol.Schema(schema)


def _device_title(hass: Any, device_id: str) -> str:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return "XT500 Energiemanager"
    return f"{device.name_by_user or device.name or 'XT500'} Energiemanager"


def _detect_device_data(
    hass: Any, user_input: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve and validate all original entities for a selected XT500."""
    device_id = user_input[CONF_XT500_DEVICE]
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None, "device_not_found"

    registry = er.async_get(hass)
    entries = er.async_entries_for_device(
        registry, device_id, include_disabled_entities=True
    )
    detected, missing, ambiguous = detect_xt500_entities(entries)
    if ambiguous:
        return None, "ambiguous_xt500_entities"
    if missing:
        return None, "missing_xt500_entities"

    grid_entity = user_input[CONF_GRID_POWER_ENTITY]
    state = hass.states.get(grid_entity)
    if state is None:
        return None, "grid_meter_not_found"
    if state.state not in ("unknown", "unavailable", "none", ""):
        try:
            float(state.state)
        except ValueError:
            return None, "grid_meter_not_numeric"

    data = {
        **detected,
        CONF_EXTERNAL_GRID_INVERT: user_input.get(CONF_EXTERNAL_GRID_INVERT, False),
        CONF_GRID_POWER_ENTITY: grid_entity,
        CONF_METER_SIGN: user_input[CONF_METER_SIGN],
        CONF_AC_PV_SIGN: user_input[CONF_AC_PV_SIGN],
    }
    if external_grid_entity := user_input.get(CONF_EXTERNAL_GRID_POWER_ENTITY):
        data[CONF_EXTERNAL_GRID_POWER_ENTITY] = external_grid_entity
    if ac_pv_entity := user_input.get(CONF_AC_PV_POWER_ENTITY):
        data[CONF_AC_PV_POWER_ENTITY] = ac_pv_entity
    return data, None


class XT500EnergyManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle XT500 Energy Manager setup."""

    VERSION = 6

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["automatic", "manual"]
        )

    async def async_step_automatic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _detect_device_data(self.hass, user_input)
            if error is None and data is not None:
                await self.async_set_unique_id(data[CONF_GRID_SETPOINT_ENTITY])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_device_title(self.hass, user_input[CONF_XT500_DEVICE]),
                    data={**data, CONF_AUTO_DASHBOARD: user_input.get(CONF_AUTO_DASHBOARD, True)},
                )
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="automatic",
            data_schema=_automatic_schema(user_input),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_GRID_SETPOINT_ENTITY])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="XT500 Energiemanager", data={**user_input, CONF_AUTO_DASHBOARD: user_input.get(CONF_AUTO_DASHBOARD, True)})
        return self.async_show_form(step_id="manual", data_schema=_manual_schema())

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        return XT500OptionsFlow()


class XT500OptionsFlow(config_entries.OptionsFlow):
    """Allow source entities to be corrected without recreating the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["automatic", "manual"]
        )

    async def async_step_automatic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = _detect_device_data(self.hass, user_input)
            if error is None and data is not None:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=_device_title(self.hass, user_input[CONF_XT500_DEVICE]),
                    data={**data, CONF_AUTO_DASHBOARD: user_input.get(
                        CONF_AUTO_DASHBOARD, self.config_entry.data.get(CONF_AUTO_DASHBOARD, False)
                    )},
                )
                return self.async_create_entry(title="", data={})
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="automatic",
            data_schema=self.add_suggested_values_to_schema(
                _automatic_schema({**self.config_entry.data, CONF_AUTO_DASHBOARD: self.config_entry.data.get(CONF_AUTO_DASHBOARD, False)}), dict(self.config_entry.data)
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=user_input
            )
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                _manual_schema({**self.config_entry.data, CONF_AUTO_DASHBOARD: self.config_entry.data.get(CONF_AUTO_DASHBOARD, False)}), dict(self.config_entry.data)
            ),
        )
