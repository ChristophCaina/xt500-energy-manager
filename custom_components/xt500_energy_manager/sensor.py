"""Sensor platform for XT500 Energy Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XT500ConfigEntry
from .entity import XT500Entity
from .runtime import XT500Runtime


@dataclass(frozen=True, kw_only=True)
class XT500SensorDescription(SensorEntityDescription):
    value_fn: Callable[[XT500Runtime], Any]


STATUS_OPTIONS = (
    "disabled", "invalid_data", "communication_pause", "starting",
    "control_error", "target_reached", "full_battery_pv_bypass",
    "minimum_soc_hold", "normal", "pv_surplus", "manual_grid_charge",
    "manual_pv_surplus", "manual_pv_priority", "manual_pv_and_grid",
    "automatic_grid_charge", "automatic_pv_surplus", "automatic_pv_priority",
    "automatic_pv_and_grid",
    "cycle_manual_grid_charge", "cycle_manual_pv_surplus",
    "cycle_manual_pv_priority", "cycle_manual_pv_and_grid",
    "cycle_automatic_grid_charge", "cycle_automatic_pv_surplus",
    "cycle_automatic_pv_priority", "cycle_automatic_pv_and_grid",
    "tariff_grid_charge",
)

SENSORS = (
    XT500SensorDescription(key="reserve_release_soc", translation_key="reserve_release_soc", icon="mdi:battery-arrow-up", native_unit_of_measurement=PERCENTAGE, value_fn=lambda r: r.reserve_release_soc),
    XT500SensorDescription(key="status", translation_key="status", icon="mdi:shield-search", device_class=SensorDeviceClass.ENUM, options=STATUS_OPTIONS, value_fn=lambda r: r.display_status),
    XT500SensorDescription(
        key="recovery_status",
        translation_key="recovery_status",
        icon="mdi:shield-refresh",
        device_class=SensorDeviceClass.ENUM,
        options=(
            "ready",
            "disabled",
            "manual_required",
            "waiting_inputs",
            "waiting_feedback",
            "waiting_stable",
            "attempting",
            "exhausted",
        ),
        value_fn=lambda r: r.recovery_status,
    ),
    XT500SensorDescription(key="active_mode", translation_key="active_mode", icon="mdi:battery-sync", device_class=SensorDeviceClass.ENUM, options=("normal", "grid_charge", "pv_surplus", "pv_priority", "pv_and_grid"), value_fn=lambda r: r.result.active_mode if r.result else None),
    XT500SensorDescription(key="selected_mode", translation_key="selected_mode", icon="mdi:tune", device_class=SensorDeviceClass.ENUM, options=("normal", "grid_charge", "pv_surplus", "pv_priority", "pv_and_grid"), value_fn=lambda r: r.result.selected_mode if r.result else None),
    XT500SensorDescription(key="active_operation", translation_key="active_operation", icon="mdi:source-branch", device_class=SensorDeviceClass.ENUM, options=("normal", "manual", "cycle_manual", "cycle_automatic", "tariff"), value_fn=lambda r: r.active_charge_source if r.charge_request_active else "normal"),
    XT500SensorDescription(key="mode_state", translation_key="mode_state", icon="mdi:list-status", device_class=SensorDeviceClass.ENUM, options=("normal", "charging", "waiting_for_pv", "target_reached", "minimum_soc_hold"), value_fn=lambda r: r.result.mode_state if r.result else None),
    XT500SensorDescription(key="selected_coupling_mode", translation_key="selected_coupling_mode", icon="mdi:connection", device_class=SensorDeviceClass.ENUM, options=("automatic", "dc", "ac", "hybrid"), value_fn=lambda r: r.result.selected_coupling_mode if r.result else None),
    XT500SensorDescription(key="active_coupling_mode", translation_key="active_coupling_mode", icon="mdi:transit-connection-variant", device_class=SensorDeviceClass.ENUM, options=("none", "dc", "ac", "hybrid"), value_fn=lambda r: r.result.active_coupling_mode if r.result else None),
    XT500SensorDescription(key="active_energy_source", translation_key="active_energy_source", icon="mdi:lightning-bolt-circle", device_class=SensorDeviceClass.ENUM, options=("none", "pv", "grid", "pv_and_grid"), value_fn=lambda r: r.result.active_energy_source if r.result else None),
    XT500SensorDescription(key="ac_pv_power", translation_key="ac_pv_power", icon="mdi:solar-power-variant", device_class=SensorDeviceClass.POWER, native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.ac_pv_power if r.result else None),
    XT500SensorDescription(key="available_ac_surplus", translation_key="available_ac_surplus", icon="mdi:transmission-tower-export", device_class=SensorDeviceClass.POWER, native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.available_ac_surplus if r.result else None),
    XT500SensorDescription(key="recommended_grid_setpoint", translation_key="recommended_grid_setpoint", icon="mdi:transmission-tower", native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.recommended_grid_setpoint if r.result else None),
    XT500SensorDescription(key="recommended_inverter_setpoint", translation_key="recommended_inverter_setpoint", icon="mdi:solar-power", native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.recommended_inverter_setpoint if r.result else None),
    XT500SensorDescription(key="estimated_home_load", translation_key="estimated_home_load", icon="mdi:home-lightning-bolt", native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.estimated_home_load if r.result else None),
    XT500SensorDescription(key="control_band", translation_key="control_band", icon="mdi:speedometer", device_class=SensorDeviceClass.ENUM, options=("small", "medium", "large"), value_fn=lambda r: r.control_profile.band),
    XT500SensorDescription(key="control_error", translation_key="control_error", icon="mdi:approximately-equal", native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: round(r.control_error, 1)),
    XT500SensorDescription(key="control_interval", translation_key="control_interval", icon="mdi:timer-sync-outline", native_unit_of_measurement="s", value_fn=lambda r: r.effective_control_interval),
    XT500SensorDescription(key="control_max_step", translation_key="control_max_step", icon="mdi:delta", native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.control_profile.maximum_change),
    XT500SensorDescription(key="active_target_soc", translation_key="active_target_soc", icon="mdi:battery-charging", native_unit_of_measurement=PERCENTAGE, value_fn=lambda r: r.active_target_soc),
    XT500SensorDescription(key="tariff_expires_at", translation_key="tariff_expires_at", icon="mdi:timer-sand", device_class=SensorDeviceClass.TIMESTAMP, value_fn=lambda r: r.tariff_expires_datetime),
    XT500SensorDescription(key="desired_charge_limit", translation_key="desired_charge_limit", icon="mdi:battery-lock", native_unit_of_measurement=PERCENTAGE, value_fn=lambda r: r.desired_charge_limit),
    XT500SensorDescription(key="battery_charge_power", translation_key="battery_charge_power", icon="mdi:battery-arrow-up", device_class=SensorDeviceClass.POWER, native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.battery_charge_power),
    XT500SensorDescription(key="battery_discharge_power", translation_key="battery_discharge_power", icon="mdi:battery-arrow-down", device_class=SensorDeviceClass.POWER, native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.battery_discharge_power),
    XT500SensorDescription(key="pv_surplus_correction", translation_key="pv_surplus_correction", icon="mdi:solar-power-variant-outline", device_class=SensorDeviceClass.POWER, native_unit_of_measurement=UnitOfPower.WATT, value_fn=lambda r: r.result.pv_surplus_correction if r.result else None),
    XT500SensorDescription(key="full_charge_confirmation", translation_key="full_charge_confirmation", icon="mdi:battery-check-outline", device_class=SensorDeviceClass.ENUM, options=("idle", "holding", "waiting_taper", "confirmed", "timeout"), value_fn=lambda r: r.full_charge_confirmation_state),
    XT500SensorDescription(
        key="cycle_state",
        translation_key="cycle_state",
        icon="mdi:battery-sync",
        device_class=SensorDeviceClass.ENUM,
        options=(
            "monitoring_disabled",
            "monitoring",
            "due_waiting",
            "manual_active",
            "automatic_active",
            "confirming_full",
            "paused",
        ),
        value_fn=lambda r: r.cycle_state,
    ),
    XT500SensorDescription(key="days_since_full", translation_key="days_since_full", icon="mdi:calendar-clock", value_fn=lambda r: r.days_since_full),
    XT500SensorDescription(key="next_cycle_at", translation_key="next_cycle_at", icon="mdi:calendar-clock", device_class=SensorDeviceClass.TIMESTAMP, value_fn=lambda r: r.next_cycle_datetime),
)


class XT500Sensor(XT500Entity, SensorEntity):
    def __init__(self, runtime: XT500Runtime, description: XT500SensorDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.runtime)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = dict(super().extra_state_attributes)
        if self.key == "status":
            attrs.update(
                {
                    "error": self.runtime.control_error_message,
                    "recovery_status": self.runtime.recovery_status,
                    "recovery_attempts": self.runtime.recovery_attempts,
                    "recovery_max_attempts": self.runtime.recovery_max_attempts,
                    "next_recovery_attempt": self.runtime.next_recovery_attempt,
                    "last_recovery_success": self.runtime.last_recovery_success,
                    "transient_write_timeouts": self.runtime.transient_write_timeouts,
                    "last_transient_write_error": self.runtime.last_transient_write_error,
                    "last_transient_write_recovery": self.runtime.last_transient_write_recovery,
                    "communication_pause": self.runtime.communication_pause_active,
                    "communication_pause_visible": self.runtime.communication_pause_visible,
                    "communication_pause_since": self.runtime.communication_pause_since,
                    "communication_pause_message": self.runtime.communication_pause_message,
                    "current_input_errors": self.runtime.invalid_inputs,
                    "last_input_errors": self.runtime.last_invalid_inputs,
                    "last_input_error_at": self.runtime.last_invalid_at,
                    "last_inputs_recovered_at": self.runtime.last_inputs_recovered_at,
                }
            )
        elif self.key == "recovery_status":
            attrs.update(
                {
                    "attempts": self.runtime.recovery_attempts,
                    "maximum_attempts": self.runtime.recovery_max_attempts,
                    "next_attempt": self.runtime.next_recovery_attempt,
                    "last_success": self.runtime.last_recovery_success,
                    "error": self.runtime.control_error_message,
                }
            )
        elif self.key == "full_charge_confirmation":
            attrs.update(
                {
                    "started_at": self.runtime.settings[
                        "full_charge_confirmation_started"
                    ],
                    "taper_started_at": self.runtime.settings[
                        "full_charge_taper_started"
                    ],
                    "actual_charge_power_w": self.runtime.battery_charge_power,
                    "minimum_hold_minutes": self.runtime.settings[
                        "full_charge_min_hold_minutes"
                    ],
                    "taper_threshold_w": self.runtime.settings[
                        "full_charge_taper_power"
                    ],
                    "taper_minutes": self.runtime.settings[
                        "full_charge_taper_minutes"
                    ],
                    "timeout_minutes": self.runtime.settings[
                        "full_charge_timeout_minutes"
                    ],
                    "top_off_power_w": self.runtime.settings[
                        "full_charge_top_off_power"
                    ],
                }
            )
        return attrs


async def async_setup_entry(_hass: HomeAssistant, entry: XT500ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(XT500Sensor(entry.runtime_data, description) for description in SENSORS)
    if entry.runtime_data.grid_meter is not None:
        async_add_entities(
            XT500GridSensor(entry.runtime_data, key)
            for key in ("grid_power_net", "grid_import_power", "grid_export_power",
                        "grid_import_energy", "grid_export_energy")
        )


class XT500GridSensor(XT500Entity, SensorEntity):
    """Optional external measurement; independent of controller availability."""

    _attr_should_poll = False

    def __init__(self, runtime: XT500Runtime, key: str) -> None:
        super().__init__(runtime, key)
        self.meter = runtime.grid_meter
        self._attr_translation_key = key
        energy = key.endswith("energy")
        self._attr_device_class = SensorDeviceClass.ENERGY if energy else SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR if energy else UnitOfPower.WATT
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING if energy else SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 6 if energy else 1

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.meter.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self.key.endswith("energy") or self.meter.energy.power is not None

    @property
    def native_value(self) -> float | None:
        data = self.meter.energy
        if self.key == "grid_import_energy":
            return data.import_energy
        if self.key == "grid_export_energy":
            return data.export_energy
        if data.power is None:
            return None
        if self.key == "grid_import_power":
            return max(data.power, 0.0)
        if self.key == "grid_export_power":
            return max(-data.power, 0.0)
        return data.power

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "source_entity": self.meter.source,
            "source_unit": self.meter.unit,
            "source_available": self.meter.energy.power is not None,
            "invert_sign": self.meter.invert,
            "integration_method": "left",
            "xt500_key": self.key,
            "xt500_manager_id": self.runtime.entry.entry_id,
        }
