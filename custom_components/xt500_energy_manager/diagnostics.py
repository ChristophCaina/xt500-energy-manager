"""Diagnostics support for XT500 Energy Manager."""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.core import HomeAssistant

from . import XT500ConfigEntry


async def async_get_config_entry_diagnostics(_hass: HomeAssistant, entry: XT500ConfigEntry) -> dict:
    runtime = entry.runtime_data
    return {
        "control_mode": "production" if runtime.regulation_enabled else "disabled",
        "control_ready": runtime.control_ready,
        "control_operational": runtime.control_operational,
        "control_error": runtime.control_error_message,
        "communication_pause": {
            "active": runtime.communication_pause_active,
            "since": runtime.communication_pause_since,
            "message": runtime.communication_pause_message,
            "visible": runtime.communication_pause_visible,
            "visible_after_seconds": 30,
            "resume_after_stable_seconds": 15,
            "hard_stop_after_seconds": runtime.communication_failure_seconds,
        },
        "automatic_recovery": {
            "enabled": runtime.automatic_recovery_enabled,
            "status": runtime.recovery_status,
            "attempts": runtime.recovery_attempts,
            "maximum_attempts": runtime.recovery_max_attempts,
            "next_attempt": runtime.next_recovery_attempt,
            "last_success": runtime.last_recovery_success,
            "fresh_feedback_after_error": runtime.recovery_feedback_ready,
            "feedback_current": runtime.recovery_feedback_current,
        },
        "transient_write_handling": {
            "maximum_attempts_per_value": 3,
            "readback_grace_polling_cycles": 3,
            "timeouts_since_start": runtime.transient_write_timeouts,
            "last_timeout": runtime.last_transient_write_error,
            "last_recovery": runtime.last_transient_write_recovery,
        },
        "external_grid_meter": (
            {
                "source_entity": runtime.grid_meter.source,
                "source_unit": runtime.grid_meter.unit,
                "invert_sign": runtime.grid_meter.invert,
                "power_w": runtime.grid_meter.energy.power,
                **runtime.grid_meter.energy.snapshot(),
            } if runtime.grid_meter is not None else None
        ),
        "configured_entities": dict(entry.data),
        "sunenergyxt_polling_interval_seconds": runtime.source_polling_interval,
        "settings": dict(runtime.settings),
        "cycle_schedule": {
            "enabled": bool(runtime.settings["automatic_enabled"]),
            "due": runtime.cycle_due,
            "state": runtime.cycle_state,
            "manual_active": runtime.settings["cycle_manual_active"],
            "automatic_active": runtime.settings["cycle_automatic_active"],
            "check_time": runtime.settings["cycle_check_time"],
            "last_full": runtime.settings["last_full"],
            "reference": runtime.settings["cycle_reference"],
            "next_cycle": runtime.next_cycle_at,
        },
        "full_charge_confirmation": {
            "state": runtime.full_charge_confirmation_state,
            "active": runtime.full_charge_confirmation_active,
            "started_at": runtime.settings["full_charge_confirmation_started"],
            "taper_started_at": runtime.settings["full_charge_taper_started"],
            "actual_charge_power_w": runtime.battery_charge_power,
            "minimum_hold_minutes": runtime.settings["full_charge_min_hold_minutes"],
            "taper_threshold_w": runtime.settings["full_charge_taper_power"],
            "taper_minutes": runtime.settings["full_charge_taper_minutes"],
            "timeout_minutes": runtime.settings["full_charge_timeout_minutes"],
            "top_off_power_w": runtime.settings["full_charge_top_off_power"],
        },
        "full_battery_pv_export": {
            "enabled": runtime.settings["full_battery_pv_export"],
            "hold": runtime._full_battery_pv_hold,
            "active": (
                runtime.result.full_battery_pv_bypass_active
                if runtime.result else False
            ),
        },
        "tariff_request": {
            "active": runtime.tariff_request_active,
            "target_soc": runtime.settings["tariff_target_soc"],
            "charge_power": runtime.settings["tariff_charge_power"],
            "request_duration_minutes": runtime.settings["tariff_request_duration"],
            "expires_at": runtime.settings["tariff_expires_at"],
        },
        "battery_flows": {
            "net_charge_w": runtime.battery_charge_power,
            "net_discharge_w": runtime.battery_discharge_power,
        },
        "pv_surplus_feedback": {
            "deadband_w": runtime.settings["pv_surplus_deadband"],
            "charge_reserve_w": runtime.settings["pv_surplus_charge_reserve"],
            "battery_charge_w": runtime.battery_charge_power,
            "battery_discharge_w": runtime.battery_discharge_power,
            "public_grid_w": (
                runtime.result.normalized_grid_power if runtime.result else None
            ),
            "applied_correction_w": (
                runtime.result.pv_surplus_correction if runtime.result else None
            ),
        },
        "reserve": {
            "enabled": runtime.settings["reserve_enabled"],
            "soc": runtime.settings["reserve_soc"],
            "held": runtime.reserve_hold_active,
            "release_soc": runtime.reserve_release_soc,
        },
        "discharge_lock": {
            "active": runtime.discharge_hold_active,
            "temporary_release_active": runtime.discharge_override_active,
            "configured_lower_limit": runtime.settings["minimum_soc"],
            "regular_release_soc": runtime.discharge_release_soc,
        },
        "data_valid": runtime.data_valid,
        "adaptive_control": {
            "band": runtime.control_profile.band,
            "error_w": runtime.control_error,
            "effective_interval_s": runtime.effective_control_interval,
            "maximum_change_w": runtime.control_profile.maximum_change,
            "feedback_ready": runtime.feedback_ready,
            "pv_release_active": runtime.pv_release_active,
            "ac_pv_release_active": runtime.ac_pv_release_active,
            "last_control_write": runtime.last_control_write,
        },
        "invalid_entities": runtime.invalid_entities,
        "input_errors": {
            "current": runtime.invalid_inputs,
            "last": runtime.last_invalid_inputs,
            "last_error_at": runtime.last_invalid_at,
            "last_recovered_at": runtime.last_inputs_recovered_at,
        },
        "optional_ac_pv_input": {
            "valid": runtime.ac_pv_input_valid,
            "issue": runtime.ac_pv_input_issue,
        },
        "result": asdict(runtime.result) if runtime.result else None,
    }
