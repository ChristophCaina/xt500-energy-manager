"""Number platform for XT500 Energy Manager."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XT500ConfigEntry
from .const import (
    CONF_MAX_CHARGE_SOC_ENTITY,
    CONF_MIN_DISCHARGE_SOC_ENTITY,
    CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
    SETTING_AUTO_TARGET_SOC,
    SETTING_CHARGE_POWER,
    SETTING_CHARGE_SOC_HYSTERESIS,
    SETTING_CONTROL_FAST_INTERVAL,
    SETTING_CONTROL_LARGE_ERROR,
    SETTING_CONTROL_LARGE_MAX_STEP,
    SETTING_CONTROL_MEDIUM_INTERVAL,
    SETTING_CONTROL_MEDIUM_MAX_STEP,
    SETTING_CONTROL_SMALL_ERROR,
    SETTING_CONTROL_SMALL_MAX_STEP,
    SETTING_CONTROL_SLOW_INTERVAL,
    SETTING_CYCLE_INTERVAL_DAYS,
    SETTING_FEEDBACK_SETTLE_TIME,
    SETTING_FULL_CHARGE_MIN_HOLD_MINUTES,
    SETTING_FULL_CHARGE_TAPER_MINUTES,
    SETTING_FULL_CHARGE_TAPER_POWER,
    SETTING_FULL_CHARGE_TIMEOUT_MINUTES,
    SETTING_FULL_CHARGE_TOP_OFF_POWER,
    SETTING_MAX_GRID_OUTPUT,
    SETTING_MAX_INVERTER_OUTPUT,
    SETTING_RESERVE_ENABLED,
    SETTING_RESERVE_SOC,
    SETTING_MIN_SOC,
    SETTING_NORMAL_CHARGE_LIMIT,
    SETTING_PV_START_DELAY,
    SETTING_PV_START_POWER,
    SETTING_PV_STOP_POWER,
    SETTING_PV_SURPLUS_DEADBAND,
    SETTING_PV_SURPLUS_CHARGE_RESERVE,
    SETTING_RECOVERY_STABILITY_TIME,
    SETTING_SOC_HYSTERESIS,
    SETTING_TARGET_GRID_POWER,
    SETTING_TARGET_SOC,
    SETTING_TARIFF_CHARGE_POWER,
    SETTING_TARIFF_REQUEST_DURATION,
    SETTING_TARIFF_TARGET_SOC,
)
from .entity import XT500Entity
from .runtime import XT500Runtime

NUMBERS = (
    NumberEntityDescription(key=SETTING_TARGET_SOC, translation_key="target_soc", icon="mdi:battery-charging-100", native_min_value=50, native_max_value=100, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_TARIFF_TARGET_SOC, translation_key="tariff_target_soc", icon="mdi:battery-charging-medium", native_min_value=20, native_max_value=100, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_TARIFF_CHARGE_POWER, translation_key="tariff_charge_power", icon="mdi:transmission-tower-import", native_min_value=0, native_max_value=2400, native_step=50, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_TARIFF_REQUEST_DURATION, translation_key="tariff_request_duration", icon="mdi:timer-sand", native_min_value=5, native_max_value=360, native_step=5, native_unit_of_measurement="min", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_AUTO_TARGET_SOC, translation_key="automatic_target_soc", icon="mdi:battery-check", native_min_value=50, native_max_value=100, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_NORMAL_CHARGE_LIMIT, translation_key="normal_charge_limit", icon="mdi:battery-lock", native_min_value=0, native_max_value=100, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CHARGE_POWER, translation_key="charge_power", icon="mdi:flash", native_min_value=0, native_max_value=2400, native_step=50, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CYCLE_INTERVAL_DAYS, translation_key="cycle_interval_days", icon="mdi:calendar-range", native_min_value=1, native_max_value=90, native_step=1, native_unit_of_measurement="d", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FULL_CHARGE_MIN_HOLD_MINUTES, translation_key="full_charge_min_hold_minutes", icon="mdi:timer-sand-full", native_min_value=1, native_max_value=60, native_step=1, native_unit_of_measurement="min", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FULL_CHARGE_TAPER_POWER, translation_key="full_charge_taper_power", icon="mdi:battery-arrow-down-outline", native_min_value=0, native_max_value=300, native_step=5, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FULL_CHARGE_TAPER_MINUTES, translation_key="full_charge_taper_minutes", icon="mdi:timer-check-outline", native_min_value=1, native_max_value=30, native_step=1, native_unit_of_measurement="min", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FULL_CHARGE_TIMEOUT_MINUTES, translation_key="full_charge_timeout_minutes", icon="mdi:timer-alert-outline", native_min_value=15, native_max_value=180, native_step=5, native_unit_of_measurement="min", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FULL_CHARGE_TOP_OFF_POWER, translation_key="full_charge_top_off_power", icon="mdi:battery-charging-outline", native_min_value=50, native_max_value=1000, native_step=50, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_RECOVERY_STABILITY_TIME, translation_key="recovery_stability_time", icon="mdi:timer-shield-outline", native_min_value=15, native_max_value=300, native_step=5, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_FEEDBACK_SETTLE_TIME, translation_key="feedback_settle_time", icon="mdi:timer-cog-outline", native_min_value=1, native_max_value=30, native_step=1, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_LARGE_MAX_STEP, translation_key="control_large_max_step", icon="mdi:delta", native_min_value=50, native_max_value=2400, native_step=10, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_SMALL_ERROR, translation_key="control_small_error", icon="mdi:approximately-equal", native_min_value=1, native_max_value=300, native_step=1, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_LARGE_ERROR, translation_key="control_large_error", icon="mdi:arrow-expand-horizontal", native_min_value=10, native_max_value=1000, native_step=10, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_SLOW_INTERVAL, translation_key="control_slow_interval", icon="mdi:speedometer-slow", native_min_value=1, native_max_value=120, native_step=0.5, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_MEDIUM_INTERVAL, translation_key="control_medium_interval", icon="mdi:speedometer-medium", native_min_value=0.5, native_max_value=60, native_step=0.5, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_FAST_INTERVAL, translation_key="control_fast_interval", icon="mdi:speedometer", native_min_value=0.5, native_max_value=20, native_step=0.5, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_SMALL_MAX_STEP, translation_key="control_small_max_step", icon="mdi:delta", native_min_value=1, native_max_value=300, native_step=1, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CONTROL_MEDIUM_MAX_STEP, translation_key="control_medium_max_step", icon="mdi:delta", native_min_value=10, native_max_value=1000, native_step=10, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_PV_STOP_POWER, translation_key="pv_stop_power", icon="mdi:solar-power-variant-outline", native_min_value=0, native_max_value=500, native_step=5, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_PV_START_POWER, translation_key="pv_start_power", icon="mdi:solar-power-variant", native_min_value=0, native_max_value=1000, native_step=5, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_PV_START_DELAY, translation_key="pv_start_delay", icon="mdi:timer-play-outline", native_min_value=0, native_max_value=300, native_step=5, native_unit_of_measurement="s", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_PV_SURPLUS_DEADBAND, translation_key="pv_surplus_deadband", icon="mdi:battery-arrow-down-outline", native_min_value=0, native_max_value=200, native_step=5, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_PV_SURPLUS_CHARGE_RESERVE, translation_key="pv_surplus_charge_reserve", icon="mdi:battery-plus-outline", native_min_value=0, native_max_value=300, native_step=5, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_RESERVE_SOC, translation_key="reserve_soc", icon="mdi:battery-lock", native_min_value=1, native_max_value=99, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_MIN_SOC, translation_key="minimum_soc", icon="mdi:battery-low", native_min_value=1, native_max_value=40, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_SOC_HYSTERESIS, translation_key="soc_hysteresis", icon="mdi:arrow-expand-vertical", native_min_value=1, native_max_value=20, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_CHARGE_SOC_HYSTERESIS, translation_key="charge_soc_hysteresis", icon="mdi:battery-sync", native_min_value=0, native_max_value=100, native_step=1, native_unit_of_measurement="%", mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_TARGET_GRID_POWER, translation_key="target_grid_power", icon="mdi:transmission-tower", native_min_value=-500, native_max_value=500, native_step=10, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_MAX_GRID_OUTPUT, translation_key="maximum_grid_output", icon="mdi:transmission-tower-export", native_min_value=0, native_max_value=2400, native_step=50, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SETTING_MAX_INVERTER_OUTPUT, translation_key="maximum_inverter_output", icon="mdi:solar-power-variant", native_min_value=0, native_max_value=2400, native_step=50, native_unit_of_measurement=UnitOfPower.WATT, mode=NumberMode.BOX),
)


class XT500Number(XT500Entity, NumberEntity):
    def __init__(self, runtime: XT500Runtime, description: NumberEntityDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        if self.key == SETTING_MIN_SOC:
            if self.runtime.discharge_override_active:
                return float(self.runtime.settings[SETTING_MIN_SOC])
            state = self._source_number_state()
        elif self.key in (
            SETTING_SOC_HYSTERESIS,
            SETTING_CHARGE_SOC_HYSTERESIS,
        ):
            state = self._source_number_state()
        else:
            state = None
        if state is not None:
            try:
                return float(state.state)
            except ValueError:
                pass
        return float(self.runtime.settings[self.key])

    def _source_number_state(self):
        source_key = {
            SETTING_NORMAL_CHARGE_LIMIT: CONF_MAX_CHARGE_SOC_ENTITY,
            SETTING_MIN_SOC: CONF_MIN_DISCHARGE_SOC_ENTITY,
            SETTING_SOC_HYSTERESIS: CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
            SETTING_CHARGE_SOC_HYSTERESIS: CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
        }.get(self.key)
        if source_key is None:
            return None
        return self.runtime.hass.states.get(
            self.runtime.entry.data.get(source_key)
        )

    @property
    def native_min_value(self) -> float:
        if (state := self._source_number_state()) is not None:
            return float(
                state.attributes.get("min", self.entity_description.native_min_value)
            )
        return float(self.entity_description.native_min_value)

    @property
    def native_max_value(self) -> float:
        if (state := self._source_number_state()) is not None:
            return float(
                state.attributes.get("max", self.entity_description.native_max_value)
            )
        return float(self.entity_description.native_max_value)

    @property
    def native_step(self) -> float:
        if (state := self._source_number_state()) is not None:
            return float(
                state.attributes.get("step", self.entity_description.native_step) or 1
            )
        return float(self.entity_description.native_step)

    async def async_set_native_value(self, value: float) -> None:
        if self.key == SETTING_NORMAL_CHARGE_LIMIT:
            await self.runtime.async_set_system_charge_limit(value)
            return
        if self.key == SETTING_MIN_SOC:
            await self.runtime.async_set_system_discharge_limit(value)
            return
        if self.key == SETTING_SOC_HYSTERESIS and self.runtime.entry.data.get(
            CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY
        ):
            await self.runtime.async_set_device_soc_hysteresis(
                CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
                SETTING_SOC_HYSTERESIS,
                value,
            )
            return
        if self.key == SETTING_CHARGE_SOC_HYSTERESIS:
            await self.runtime.async_set_device_soc_hysteresis(
                CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
                SETTING_CHARGE_SOC_HYSTERESIS,
                value,
            )
            return
        self.runtime.async_set_setting(self.key, value)


async def async_setup_entry(_hass: HomeAssistant, entry: XT500ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(
        XT500Number(entry.runtime_data, description)
        for description in NUMBERS
        if description.key != SETTING_CHARGE_SOC_HYSTERESIS
        or entry.data.get(CONF_CHARGE_SOC_HYSTERESIS_ENTITY)
    )
