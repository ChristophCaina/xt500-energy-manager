"""XT500 Energy Manager integration."""

from __future__ import annotations

from pathlib import Path
import logging

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later

from .blueprint_sync import BlueprintSyncResult, sync_bundled_blueprint
from .const import (
    CONF_AC_PV_POWER_ENTITY,
    CONF_AC_PV_SIGN,
    CONF_BATTERY_INPUT_POWER_ENTITY,
    CONF_BATTERY_OUTPUT_POWER_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_GRID_CHARGE_DAILY_ENERGY_ENTITY,
    CONF_GRID_EXPORT_DAILY_ENERGY_ENTITY,
    CONF_EXTERNAL_GRID_POWER_ENTITY,
    CONF_GRID_PORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_INVERTER_SETPOINT_ENTITY,
    CONF_LOAD_DISCHARGE_LIMIT_ENTITY,
    CONF_LOAD_PORT_POWER_ENTITY,
    CONF_MAX_CHARGE_SOC_ENTITY,
    CONF_MIN_DISCHARGE_SOC_ENTITY,
    CONF_METER_SIGN,
    CONF_OFFGRID_DAILY_ENERGY_ENTITY,
    CONF_PV_DAILY_ENERGY_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SOC_ENTITY,
    DOMAIN,
    FRONTEND_URL,
    PLATFORMS,
    PV_PRODUCTION_POSITIVE,
)
from .entity_mapping import detect_xt500_entities
from .runtime import XT500Runtime
from .dashboard_setup import async_ensure_dashboard
from .grid_meter import ExternalGridMeter

type XT500ConfigEntry = ConfigEntry[XT500Runtime]

_LOGGER = logging.getLogger(__name__)

_OPTIONAL_DISCOVERED_KEYS = (
    CONF_BATTERY_POWER_ENTITY,
    CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_PV_DAILY_ENERGY_ENTITY,
    CONF_GRID_CHARGE_DAILY_ENERGY_ENTITY,
    CONF_GRID_EXPORT_DAILY_ENERGY_ENTITY,
    CONF_OFFGRID_DAILY_ENERGY_ENTITY,
)


def _detect_configured_xt500_entities(
    hass: HomeAssistant, data: dict
) -> tuple[dict[str, str], list[str], list[str]] | None:
    """Detect original entities belonging to the already configured XT500."""
    registry = er.async_get(hass)
    device_id = None
    for key in (CONF_SOC_ENTITY, CONF_PV_POWER_ENTITY, CONF_GRID_PORT_POWER_ENTITY):
        source_entity = data.get(key)
        registry_entry = registry.async_get(source_entity) if source_entity else None
        if (
            registry_entry is not None
            and registry_entry.platform == "sunenergyxt"
            and registry_entry.device_id
        ):
            device_id = registry_entry.device_id
            break
    if device_id is None:
        return None

    return detect_xt500_entities(
        er.async_entries_for_device(
            registry, device_id, include_disabled_entities=True
        )
    )


def _discover_optional_entities(
    hass: HomeAssistant, entry: XT500ConfigEntry
) -> None:
    """Attach newly available optional sensors from the configured XT500 device."""
    result = _detect_configured_xt500_entities(hass, dict(entry.data))
    if result is None:
        return
    detected, _missing, ambiguous = result
    additions = {
        key: detected[key]
        for key in _OPTIONAL_DISCOVERED_KEYS
        if key in detected and key not in ambiguous and entry.data.get(key) != detected[key]
    }
    if additions:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **additions}
        )


async def _async_reload_automations(hass: HomeAssistant) -> None:
    """Reload automations after the managed blueprint changed."""
    if hass.services.has_service("automation", "reload"):
        await hass.services.async_call("automation", "reload", blocking=True)


@callback
def _schedule_automation_reload(hass: HomeAssistant) -> None:
    """Reload after startup so existing blueprint instances use the new body."""

    @callback
    def _reload_after_delay(_now) -> None:
        hass.async_create_task(
            _async_reload_automations(hass),
            "Reload automations after XT500 blueprint update",
        )

    async_call_later(hass, 5, _reload_after_delay)


@callback
def _async_started_after_blueprint_update(
    hass: HomeAssistant, _event: Event
) -> None:
    _schedule_automation_reload(hass)


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Register frontend assets and synchronize the bundled blueprint."""
    try:
        result: BlueprintSyncResult = await hass.async_add_executor_job(
            sync_bundled_blueprint, hass.config.config_dir
        )
    except (OSError, ValueError):
        _LOGGER.exception("Unable to synchronize the bundled tariff blueprint")
    else:
        if result.status == "preserved":
            _LOGGER.warning(
                "Kept manually changed tariff blueprint at %s; the bundled "
                "update was not installed",
                result.target,
            )
        elif result.changed:
            _LOGGER.info("%s at %s", result.detail, result.target)
            if hass.is_running:
                _schedule_automation_reload(hass)
            else:
                hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED,
                    lambda event: _async_started_after_blueprint_update(
                        hass, event
                    ),
                )

    frontend_path = Path(__file__).parent / "frontend" / "xt500-energy-dashboard-strategy.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(frontend_path), False)]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: XT500ConfigEntry) -> bool:
    """Set up one XT500 energy controller."""
    _discover_optional_entities(hass, entry)
    runtime = XT500Runtime(hass, entry)
    entry.runtime_data = runtime
    await runtime.async_start()
    runtime.grid_meter = ExternalGridMeter(hass, entry) if entry.data.get(
        CONF_EXTERNAL_GRID_POWER_ENTITY
    ) else None
    if runtime.grid_meter is not None:
        await runtime.grid_meter.async_start()
    entry.async_on_unload(
        hass.async_add_shutdown_job(
            HassJob(runtime.async_stop, name="Stop XT500 Energy Manager")
        )
    )
    if runtime.grid_meter is not None:
        entry.async_on_unload(
            hass.async_add_shutdown_job(
                HassJob(runtime.grid_meter.async_stop, name="Stop XT500 grid meter")
            )
        )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_ensure_dashboard(hass, entry)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: XT500ConfigEntry
) -> bool:
    """Migrate development entries to the production source schema."""
    data = dict(entry.data)
    if entry.version < 2:
        retained_keys = {
            CONF_SOC_ENTITY,
            CONF_PV_POWER_ENTITY,
            CONF_GRID_POWER_ENTITY,
            CONF_GRID_PORT_POWER_ENTITY,
            CONF_LOAD_PORT_POWER_ENTITY,
            CONF_GRID_SETPOINT_ENTITY,
            CONF_INVERTER_SETPOINT_ENTITY,
            CONF_MAX_CHARGE_SOC_ENTITY,
            CONF_MIN_DISCHARGE_SOC_ENTITY,
            CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
            CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
            CONF_LOAD_DISCHARGE_LIMIT_ENTITY,
            CONF_BATTERY_INPUT_POWER_ENTITY,
            CONF_BATTERY_OUTPUT_POWER_ENTITY,
            CONF_BATTERY_POWER_ENTITY,
            CONF_PV_DAILY_ENERGY_ENTITY,
            CONF_GRID_CHARGE_DAILY_ENERGY_ENTITY,
            CONF_GRID_EXPORT_DAILY_ENERGY_ENTITY,
            CONF_OFFGRID_DAILY_ENERGY_ENTITY,
            CONF_METER_SIGN,
            CONF_AC_PV_POWER_ENTITY,
            CONF_AC_PV_SIGN,
        }
        data = {key: value for key, value in data.items() if key in retained_keys}

    if entry.version < 3 and not data.get(CONF_MIN_DISCHARGE_SOC_ENTITY):
        result = _detect_configured_xt500_entities(hass, data)
        if result is None:
            _LOGGER.error(
                "Unable to locate the configured SunEnergyXT device while "
                "migrating the system discharge limit"
            )
            return False
        detected, _missing, ambiguous = result
        if (
            CONF_MIN_DISCHARGE_SOC_ENTITY in ambiguous
            or CONF_MIN_DISCHARGE_SOC_ENTITY not in detected
        ):
            _LOGGER.error(
                "Unable to uniquely detect the SunEnergyXT system discharge "
                "limit (SI) during migration"
            )
            return False
        data[CONF_MIN_DISCHARGE_SOC_ENTITY] = detected[
            CONF_MIN_DISCHARGE_SOC_ENTITY
        ]

    if entry.version < 4:
        data.setdefault(CONF_AC_PV_SIGN, PV_PRODUCTION_POSITIVE)
    if entry.version < 5:
        result = _detect_configured_xt500_entities(hass, data)
        if result is not None:
            detected, _missing, ambiguous = result
            if (
                CONF_BATTERY_POWER_ENTITY in detected
                and CONF_BATTERY_POWER_ENTITY not in ambiguous
            ):
                data[CONF_BATTERY_POWER_ENTITY] = detected[
                    CONF_BATTERY_POWER_ENTITY
                ]
        hass.config_entries.async_update_entry(entry, data=data, version=5)
    if entry.version < 6:
        result = _detect_configured_xt500_entities(hass, data)
        if result is not None:
            detected, _missing, ambiguous = result
            for key in (
                CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
                CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
            ):
                if key in detected and key not in ambiguous:
                    data[key] = detected[key]
        hass.config_entries.async_update_entry(entry, data=data, version=6)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: XT500ConfigEntry) -> None:
    """Reload after the observed source entities were changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: XT500ConfigEntry) -> bool:
    """Unload an XT500 energy controller."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    if entry.runtime_data.grid_meter is not None:
        await entry.runtime_data.grid_meter.async_stop()
    await entry.runtime_data.async_stop()
    return True
