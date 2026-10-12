"""Constants for the XT500 Energy Manager integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "xt500_energy_manager"
VERSION: Final = "1.11.2"
PLATFORMS: Final = (
    "sensor",
    "binary_sensor",
    "switch",
    "select",
    "number",
    "time",
    "button",
)

CONF_SOC_ENTITY: Final = "soc_entity"
CONF_PV_POWER_ENTITY: Final = "pv_power_entity"
CONF_AC_PV_POWER_ENTITY: Final = "ac_pv_power_entity"
CONF_EXTERNAL_GRID_POWER_ENTITY: Final = "external_grid_power_entity"
CONF_EXTERNAL_GRID_INVERT: Final = "external_grid_invert"
CONF_GRID_POWER_ENTITY: Final = "grid_power_entity"
CONF_GRID_PORT_POWER_ENTITY: Final = "grid_port_power_entity"
CONF_LOAD_PORT_POWER_ENTITY: Final = "load_port_power_entity"
CONF_GRID_SETPOINT_ENTITY: Final = "grid_setpoint_entity"
CONF_INVERTER_SETPOINT_ENTITY: Final = "inverter_setpoint_entity"
CONF_MAX_CHARGE_SOC_ENTITY: Final = "max_charge_soc_entity"
CONF_MIN_DISCHARGE_SOC_ENTITY: Final = "min_discharge_soc_entity"
CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY: Final = "discharge_soc_hysteresis_entity"
CONF_CHARGE_SOC_HYSTERESIS_ENTITY: Final = "charge_soc_hysteresis_entity"
CONF_LOAD_DISCHARGE_LIMIT_ENTITY: Final = "load_discharge_limit_entity"
CONF_BATTERY_POWER_ENTITY: Final = "battery_power_entity"
CONF_BATTERY_INPUT_POWER_ENTITY: Final = "battery_input_power_entity"
CONF_BATTERY_OUTPUT_POWER_ENTITY: Final = "battery_output_power_entity"
CONF_PV_DAILY_ENERGY_ENTITY: Final = "pv_daily_energy_entity"
CONF_GRID_CHARGE_DAILY_ENERGY_ENTITY: Final = "grid_charge_daily_energy_entity"
CONF_GRID_EXPORT_DAILY_ENERGY_ENTITY: Final = "grid_export_daily_energy_entity"
CONF_OFFGRID_DAILY_ENERGY_ENTITY: Final = "offgrid_daily_energy_entity"
CONF_METER_SIGN: Final = "meter_sign"
CONF_AC_PV_SIGN: Final = "ac_pv_sign"
CONF_XT500_DEVICE: Final = "xt500_device"

INPUT_LABELS: Final = {
    CONF_SOC_ENTITY: "Speicherstand (SOC)",
    CONF_PV_POWER_ENTITY: "PV direkt am XT500",
    CONF_AC_PV_POWER_ENTITY: "PV-Leistung über AC (optional)",
    CONF_GRID_POWER_ENTITY: "Öffentlicher Netzanschlusspunkt",
    CONF_GRID_PORT_POWER_ENTITY: "XT500-Netzanschluss",
    CONF_LOAD_PORT_POWER_ENTITY: "XT500-Lastanschluss",
    CONF_GRID_SETPOINT_ENTITY: "Sollwert Netzanschluss",
    CONF_INVERTER_SETPOINT_ENTITY: "Sollwert Wechselrichter-Obergrenze",
    CONF_MAX_CHARGE_SOC_ENTITY: "System-Ladegrenze",
    CONF_MIN_DISCHARGE_SOC_ENTITY: "System-Entladegrenze",
    CONF_BATTERY_POWER_ENTITY: "System-Batterieleistung",
}

METER_IMPORT_POSITIVE: Final = "import_positive"
METER_EXPORT_POSITIVE: Final = "export_positive"
METER_SIGNS: Final = (METER_IMPORT_POSITIVE, METER_EXPORT_POSITIVE)

PV_PRODUCTION_POSITIVE: Final = "production_positive"
PV_PRODUCTION_NEGATIVE: Final = "production_negative"
PV_SIGNS: Final = (PV_PRODUCTION_POSITIVE, PV_PRODUCTION_NEGATIVE)

MODE_GRID: Final = "grid_charge"
MODE_PV_SURPLUS: Final = "pv_surplus"
MODE_PV_PRIORITY: Final = "pv_priority"
MODE_PV_GRID: Final = "pv_and_grid"
CHARGE_MODES: Final = (MODE_GRID, MODE_PV_SURPLUS, MODE_PV_PRIORITY, MODE_PV_GRID)

BASE_NORMAL: Final = "normal"
BASE_PV_SURPLUS: Final = "pv_surplus"
BASE_MODES: Final = (BASE_NORMAL, BASE_PV_SURPLUS)

COUPLING_AUTO: Final = "automatic"
COUPLING_DC: Final = "dc"
COUPLING_AC: Final = "ac"
COUPLING_HYBRID: Final = "hybrid"
COUPLING_MODES: Final = (
    COUPLING_AUTO,
    COUPLING_DC,
    COUPLING_AC,
)

SETTING_MANUAL_ACTIVE: Final = "manual_active"
SETTING_TARIFF_ACTIVE: Final = "tariff_active"
SETTING_TARIFF_TARGET_SOC: Final = "tariff_target_soc"
SETTING_TARIFF_CHARGE_POWER: Final = "tariff_charge_power"
SETTING_TARIFF_REQUEST_DURATION: Final = "tariff_request_duration"
SETTING_TARIFF_EXPIRES_AT: Final = "tariff_expires_at"
SETTING_AUTO_ENABLED: Final = "automatic_enabled"
SETTING_REGULATION_ENABLED: Final = "regulation_enabled"
SETTING_AUTOMATIC_RECOVERY_ENABLED: Final = "automatic_recovery_enabled"
SETTING_RECOVERY_STABILITY_TIME: Final = "recovery_stability_time"
SETTING_FEEDBACK_SETTLE_TIME: Final = "feedback_settle_time"
SETTING_CONTROL_LARGE_MAX_STEP: Final = "control_large_max_step"
SETTING_CONTROL_SMALL_ERROR: Final = "control_small_error"
SETTING_CONTROL_LARGE_ERROR: Final = "control_large_error"
SETTING_CONTROL_SLOW_INTERVAL: Final = "control_slow_interval"
SETTING_CONTROL_MEDIUM_INTERVAL: Final = "control_medium_interval"
SETTING_CONTROL_FAST_INTERVAL: Final = "control_fast_interval"
SETTING_CONTROL_SMALL_MAX_STEP: Final = "control_small_max_step"
SETTING_CONTROL_MEDIUM_MAX_STEP: Final = "control_medium_max_step"
SETTING_PV_STOP_POWER: Final = "pv_stop_power"
SETTING_PV_START_POWER: Final = "pv_start_power"
SETTING_PV_START_DELAY: Final = "pv_start_delay"
SETTING_PV_SURPLUS_DEADBAND: Final = "pv_surplus_deadband"
SETTING_PV_SURPLUS_CHARGE_RESERVE: Final = "pv_surplus_charge_reserve"
SETTING_FULL_BATTERY_PV_EXPORT: Final = "full_battery_pv_export"
SETTING_SHOW_ADVANCED: Final = "show_advanced"
SETTING_MANUAL_MODE: Final = "manual_mode"
SETTING_AUTO_MODE: Final = "automatic_mode"
SETTING_BASE_MODE: Final = "base_mode"
SETTING_COUPLING_MODE: Final = "coupling_mode"
SETTING_TARGET_SOC: Final = "target_soc"
SETTING_AUTO_TARGET_SOC: Final = "automatic_target_soc"
SETTING_NORMAL_CHARGE_LIMIT: Final = "normal_charge_limit"
SETTING_CHARGE_POWER: Final = "charge_power"
SETTING_CYCLE_INTERVAL_DAYS: Final = "cycle_interval_days"
SETTING_CYCLE_CHECK_TIME: Final = "cycle_check_time"
SETTING_CYCLE_MANUAL_ACTIVE: Final = "cycle_manual_active"
SETTING_CYCLE_AUTOMATIC_ACTIVE: Final = "cycle_automatic_active"
SETTING_MIN_SOC: Final = "minimum_soc"
SETTING_SOC_HYSTERESIS: Final = "soc_hysteresis"
SETTING_CHARGE_SOC_HYSTERESIS: Final = "charge_soc_hysteresis"
SETTING_DISCHARGE_OVERRIDE_ACTIVE: Final = "discharge_override_active"
SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT: Final = "discharge_override_original_limit"
SETTING_TARGET_GRID_POWER: Final = "target_grid_power"
SETTING_MAX_GRID_OUTPUT: Final = "maximum_grid_output"
SETTING_MAX_INVERTER_OUTPUT: Final = "maximum_inverter_output"
SETTING_LAST_FULL: Final = "last_full"
SETTING_CYCLE_REFERENCE: Final = "cycle_reference"
SETTING_FULL_CHARGE_MIN_HOLD_MINUTES: Final = "full_charge_min_hold_minutes"
SETTING_FULL_CHARGE_TAPER_POWER: Final = "full_charge_taper_power"
SETTING_FULL_CHARGE_TAPER_MINUTES: Final = "full_charge_taper_minutes"
SETTING_FULL_CHARGE_TIMEOUT_MINUTES: Final = "full_charge_timeout_minutes"
SETTING_FULL_CHARGE_TOP_OFF_POWER: Final = "full_charge_top_off_power"
SETTING_FULL_CHARGE_CONFIRMATION_STARTED: Final = "full_charge_confirmation_started"
SETTING_FULL_CHARGE_TAPER_STARTED: Final = "full_charge_taper_started"
SETTING_FULL_CHARGE_LAST_RESULT: Final = "full_charge_last_result"

DEFAULT_SETTINGS: Final = {
    SETTING_REGULATION_ENABLED: True,
    SETTING_AUTOMATIC_RECOVERY_ENABLED: True,
    SETTING_RECOVERY_STABILITY_TIME: 60.0,
    SETTING_FEEDBACK_SETTLE_TIME: 5.0,
    SETTING_CONTROL_LARGE_MAX_STEP: 600.0,
    SETTING_CONTROL_SMALL_ERROR: 8.0,
    SETTING_CONTROL_LARGE_ERROR: 150.0,
    SETTING_CONTROL_SLOW_INTERVAL: 3.0,
    SETTING_CONTROL_MEDIUM_INTERVAL: 2.5,
    SETTING_CONTROL_FAST_INTERVAL: 1.0,
    SETTING_CONTROL_SMALL_MAX_STEP: 20.0,
    SETTING_CONTROL_MEDIUM_MAX_STEP: 120.0,
    SETTING_PV_STOP_POWER: 50.0,
    SETTING_PV_START_POWER: 80.0,
    SETTING_PV_START_DELAY: 30.0,
    SETTING_PV_SURPLUS_DEADBAND: 20.0,
    SETTING_PV_SURPLUS_CHARGE_RESERVE: 50.0,
    SETTING_FULL_BATTERY_PV_EXPORT: False,
    SETTING_SHOW_ADVANCED: False,
    SETTING_MANUAL_ACTIVE: False,
    SETTING_TARIFF_ACTIVE: False,
    SETTING_TARIFF_TARGET_SOC: 80.0,
    SETTING_TARIFF_CHARGE_POWER: 1000.0,
    SETTING_TARIFF_REQUEST_DURATION: 90.0,
    SETTING_TARIFF_EXPIRES_AT: None,
    SETTING_AUTO_ENABLED: False,
    SETTING_MANUAL_MODE: MODE_PV_PRIORITY,
    SETTING_AUTO_MODE: MODE_PV_PRIORITY,
    SETTING_BASE_MODE: BASE_NORMAL,
    SETTING_COUPLING_MODE: COUPLING_AUTO,
    SETTING_TARGET_SOC: 100.0,
    SETTING_AUTO_TARGET_SOC: 100.0,
    SETTING_NORMAL_CHARGE_LIMIT: 100.0,
    SETTING_CHARGE_POWER: 2400.0,
    SETTING_CYCLE_INTERVAL_DAYS: 14.0,
    SETTING_CYCLE_CHECK_TIME: "12:00:00",
    SETTING_CYCLE_MANUAL_ACTIVE: False,
    SETTING_CYCLE_AUTOMATIC_ACTIVE: False,
    SETTING_MIN_SOC: 10.0,
    SETTING_SOC_HYSTERESIS: 5.0,
    SETTING_CHARGE_SOC_HYSTERESIS: 5.0,
    SETTING_DISCHARGE_OVERRIDE_ACTIVE: False,
    SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT: None,
    SETTING_TARGET_GRID_POWER: 0.0,
    SETTING_MAX_GRID_OUTPUT: 2400.0,
    SETTING_MAX_INVERTER_OUTPUT: 2400.0,
    SETTING_LAST_FULL: None,
    SETTING_CYCLE_REFERENCE: None,
    SETTING_FULL_CHARGE_MIN_HOLD_MINUTES: 10.0,
    SETTING_FULL_CHARGE_TAPER_POWER: 30.0,
    SETTING_FULL_CHARGE_TAPER_MINUTES: 5.0,
    SETTING_FULL_CHARGE_TIMEOUT_MINUTES: 60.0,
    SETTING_FULL_CHARGE_TOP_OFF_POWER: 300.0,
    SETTING_FULL_CHARGE_CONFIRMATION_STARTED: None,
    SETTING_FULL_CHARGE_TAPER_STARTED: None,
    SETTING_FULL_CHARGE_LAST_RESULT: "idle",
}

FRONTEND_URL: Final = "/xt500_energy_manager/xt500-energy-dashboard-strategy.js"
