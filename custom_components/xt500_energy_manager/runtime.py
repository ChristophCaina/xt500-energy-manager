"""Production runtime for the XT500 Energy Manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
import logging
import math
from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AC_PV_POWER_ENTITY,
    CONF_AC_PV_SIGN,
    CONF_BATTERY_INPUT_POWER_ENTITY,
    CONF_BATTERY_OUTPUT_POWER_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
    CONF_GRID_PORT_POWER_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_GRID_SETPOINT_ENTITY,
    CONF_INVERTER_SETPOINT_ENTITY,
    CONF_LOAD_PORT_POWER_ENTITY,
    CONF_MAX_CHARGE_SOC_ENTITY,
    CONF_MIN_DISCHARGE_SOC_ENTITY,
    CONF_METER_SIGN,
    CONF_PV_POWER_ENTITY,
    CONF_SOC_ENTITY,
    DEFAULT_SETTINGS,
    DOMAIN,
    INPUT_LABELS,
    METER_EXPORT_POSITIVE,
    PV_PRODUCTION_NEGATIVE,
    SETTING_AUTO_ENABLED,
    SETTING_AUTO_MODE,
    SETTING_AUTO_TARGET_SOC,
    SETTING_AUTOMATIC_RECOVERY_ENABLED,
    SETTING_BASE_MODE,
    SETTING_CHARGE_POWER,
    SETTING_CHARGE_SOC_HYSTERESIS,
    SETTING_COUPLING_MODE,
    SETTING_CONTROL_FAST_INTERVAL,
    SETTING_CONTROL_LARGE_ERROR,
    SETTING_CONTROL_LARGE_MAX_STEP,
    SETTING_CONTROL_MEDIUM_INTERVAL,
    SETTING_CONTROL_MEDIUM_MAX_STEP,
    SETTING_CONTROL_SMALL_ERROR,
    SETTING_CONTROL_SMALL_MAX_STEP,
    SETTING_CONTROL_SLOW_INTERVAL,
    SETTING_CYCLE_REFERENCE,
    SETTING_CYCLE_AUTOMATIC_ACTIVE,
    SETTING_CYCLE_CHECK_TIME,
    SETTING_CYCLE_INTERVAL_DAYS,
    SETTING_CYCLE_MANUAL_ACTIVE,
    SETTING_DISCHARGE_OVERRIDE_ACTIVE,
    SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT,
    SETTING_FEEDBACK_SETTLE_TIME,
    SETTING_FULL_CHARGE_CONFIRMATION_STARTED,
    SETTING_FULL_CHARGE_LAST_RESULT,
    SETTING_FULL_CHARGE_MIN_HOLD_MINUTES,
    SETTING_FULL_CHARGE_TAPER_MINUTES,
    SETTING_FULL_CHARGE_TAPER_POWER,
    SETTING_FULL_CHARGE_TAPER_STARTED,
    SETTING_FULL_CHARGE_TIMEOUT_MINUTES,
    SETTING_FULL_CHARGE_TOP_OFF_POWER,
    SETTING_FULL_BATTERY_PV_EXPORT,
    SETTING_LAST_FULL,
    SETTING_MANUAL_ACTIVE,
    SETTING_MANUAL_MODE,
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
    SETTING_REGULATION_ENABLED,
    SETTING_SOC_HYSTERESIS,
    SETTING_TARGET_GRID_POWER,
    SETTING_TARGET_SOC,
    SETTING_TARIFF_ACTIVE,
    SETTING_TARIFF_CHARGE_POWER,
    SETTING_TARIFF_EXPIRES_AT,
    SETTING_TARIFF_REQUEST_DURATION,
    SETTING_TARIFF_TARGET_SOC,
)
from .controller import (
    AdaptiveControlProfile,
    ControlInput,
    ControlResult,
    ControlSettings,
    FullChargeConfirmationDecision,
    calculate_control_with_bypass_state,
    FullBatteryBypassState,
    FULL_BATTERY_PV_ENTRY_DELAY,
    classify_actual_energy_source,
    cycle_is_due,
    decode_signed_16,
    feedback_samples_are_fresh,
    limit_setpoint_change,
    net_battery_flows,
    signed_battery_flows,
    next_cycle_check_at,
    normalize_pv_production,
    overall_control_error,
    quantize_number_value,
    RECOVERY_DELAY_MULTIPLIERS,
    reconcile_normal_charge_limit,
    recovery_delay_seconds,
    communication_pause_is_visible,
    select_adaptive_control_profile,
    select_charge_limit,
    select_charge_request,
    transient_readback_wait_seconds,
    update_full_charge_confirmation,
    update_full_battery_pv_hold,
    update_pv_release,
    update_discharge_hold,
    WRITE_RETRY_DELAY_MULTIPLIERS,
    write_retry_delay_seconds,
)

if TYPE_CHECKING:
    from .grid_meter import ExternalGridMeter

_LOGGER = logging.getLogger(__name__)
_STARTUP_STABILITY_SECONDS = 5.0
_COMMUNICATION_STABILITY_SECONDS = 15.0
_COMMUNICATION_FAILURE_SECONDS = 90.0
_COMMUNICATION_DISPLAY_DELAY_SECONDS = 30.0
_RECOVERY_FEEDBACK_TIMEOUT_SECONDS = 30.0
_WRITE_MAX_ATTEMPTS = len(WRITE_RETRY_DELAY_MULTIPLIERS) + 1
_DEFAULT_SOURCE_POLLING_INTERVAL = 3.0
_MIN_SOURCE_POLLING_INTERVAL = 3.0
_MAX_SOURCE_POLLING_INTERVAL = 60.0


class TransientCommunicationError(HomeAssistantError):
    """Signal a temporary loss of readable XT500 entities."""


class XT500Runtime:
    """Own and apply one XT500 controller configuration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.grid_meter: ExternalGridMeter | None = None
        self.hass = hass
        self.entry = entry
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.result: ControlResult | None = None
        self.data_valid = False
        self.charge_request_active = False
        self.active_charge_source = "none"
        self.active_target_soc: float | None = None
        self.desired_charge_limit: float | None = None
        self.invalid_entities: list[str] = []
        self.invalid_inputs: list[dict[str, str]] = []
        self.last_invalid_inputs: list[dict[str, str]] = []
        self.last_invalid_at: str | None = None
        self.last_inputs_recovered_at: str | None = None
        self.control_error_message: str | None = None
        self.last_control_write: str | None = None
        self.last_recovery_success: str | None = None
        self.last_transient_write_error: str | None = None
        self.last_transient_write_recovery: str | None = None
        self.transient_write_timeouts = 0
        self.communication_pause_message: str | None = None
        self.ac_pv_input_valid = True
        self.ac_pv_input_issue: dict[str, str] | None = None

        self._data_valid_since_monotonic: float | None = None
        self._ha_started = hass.is_running
        self._write_blocked = False
        self._communication_pause_active = False
        self._communication_pause_at: datetime | None = None
        self._communication_pause_started_monotonic: float | None = None
        self._communication_stable_since_monotonic: float | None = None
        self._communication_pause_task: asyncio.Task | None = None
        self._communication_pause_warning_logged = False
        self._last_stable_display_status: str | None = None
        self._control_error_at: datetime | None = None
        self._recovery_attempts = 0
        self._recovery_status = "ready"
        self._recovery_stable_since_monotonic: float | None = None
        self._next_recovery_attempt: str | None = None
        self._recovery_task: asyncio.Task | None = None
        self._full_soc_latched = False
        self._full_battery_pv_hold = False
        self._full_battery_pv_transition = FullBatteryBypassState()
        self._full_battery_pv_entry_task: asyncio.Task | None = None
        self._reserve_hold: bool | None = None
        self._low_soc_hold: bool | None = None
        self._discharge_override_session_active = False
        self._discharge_override_restore_task: asyncio.Task | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsub_state: Callable[[], None] | None = None
        self._unsub_started: Callable[[], None] | None = None
        self._unsub_cycle_check: Callable[[], None] | None = None
        self._unsub_tariff_expiry: Callable[[], None] | None = None
        self._unsub_full_charge_confirmation: Callable[[], None] | None = None
        self._control_apply_task: asyncio.Task | None = None
        self._startup_ready_task: asyncio.Task | None = None
        self._control_apply_requested = False
        self._shutdown_in_progress = False
        self._shutdown_failed = False
        self._charge_limit_override_active = False
        self._normal_charge_limit_write_pending: float | None = None
        self._last_control_apply_monotonic = 0.0
        self._last_control_write_at: datetime | None = None
        self._pv_release_active = False
        self._pv_above_start_since: float | None = None
        self._pv_release_due_monotonic: float | None = None
        self._pv_release_task: asyncio.Task | None = None
        self._ac_pv_release_active = False
        self._ac_pv_above_start_since: float | None = None
        self._ac_pv_release_due_monotonic: float | None = None
        self._ac_pv_release_task: asyncio.Task | None = None
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    @property
    def source_entities(self) -> list[str]:
        """Return every configured source observed by this controller."""
        entities = [
            entity_id
            for key in (
                CONF_SOC_ENTITY,
                CONF_PV_POWER_ENTITY,
                CONF_AC_PV_POWER_ENTITY,
                CONF_GRID_POWER_ENTITY,
                CONF_GRID_PORT_POWER_ENTITY,
                CONF_LOAD_PORT_POWER_ENTITY,
                CONF_GRID_SETPOINT_ENTITY,
                CONF_INVERTER_SETPOINT_ENTITY,
                CONF_MAX_CHARGE_SOC_ENTITY,
                CONF_MIN_DISCHARGE_SOC_ENTITY,
                CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY,
                CONF_CHARGE_SOC_HYSTERESIS_ENTITY,
                CONF_BATTERY_POWER_ENTITY,
                CONF_BATTERY_INPUT_POWER_ENTITY,
                CONF_BATTERY_OUTPUT_POWER_ENTITY,
            )
            if (entity_id := self.entry.data.get(key))
        ]
        return list(dict.fromkeys(entities))

    async def async_start(self) -> None:
        """Restore settings and begin production observation."""
        stored = await self._store.async_load()
        migrated = False
        if not isinstance(stored, dict):
            # First installation observes only until the user enables control.
            self.settings[SETTING_REGULATION_ENABLED] = False
            migrated = True
        if isinstance(stored, dict):
            self.settings.update(
                {key: stored[key] for key in DEFAULT_SETTINGS if key in stored}
            )
            if self.settings[SETTING_COUPLING_MODE] == "hybrid":
                self.settings[SETTING_COUPLING_MODE] = "automatic"
                migrated = True
            if (
                SETTING_FEEDBACK_SETTLE_TIME not in stored
                and "live_write_interval" in stored
            ):
                self.settings[SETTING_FEEDBACK_SETTLE_TIME] = stored[
                    "live_write_interval"
                ]
                migrated = True
            if (
                SETTING_CONTROL_LARGE_MAX_STEP not in stored
                and "live_max_step" in stored
            ):
                self.settings[SETTING_CONTROL_LARGE_MAX_STEP] = stored[
                    "live_max_step"
                ]
                migrated = True

        charge_limit_entity = self.entry.data.get(CONF_MAX_CHARGE_SOC_ENTITY)
        if (
            (not isinstance(stored, dict) or SETTING_NORMAL_CHARGE_LIMIT not in stored)
            and charge_limit_entity
            and (current_limit := self._float_state(charge_limit_entity)) is not None
        ):
            self.settings[SETTING_NORMAL_CHARGE_LIMIT] = current_limit
            migrated = True

        for entity_key, setting_key in (
            (CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY, SETTING_SOC_HYSTERESIS),
            (CONF_CHARGE_SOC_HYSTERESIS_ENTITY, SETTING_CHARGE_SOC_HYSTERESIS),
        ):
            entity_id = self.entry.data.get(entity_key)
            if entity_id and (value := self._float_state(entity_id)) is not None:
                if float(self.settings[setting_key]) != value:
                    self.settings[setting_key] = value
                    migrated = True

        if (
            bool(self.settings[SETTING_AUTO_ENABLED])
            and self._setting_datetime(SETTING_LAST_FULL) is None
            and self._setting_datetime(SETTING_CYCLE_REFERENCE) is None
        ):
            self.settings[SETTING_CYCLE_REFERENCE] = dt_util.now().isoformat()
            migrated = True

        if self._automatic_cycle_should_start_now():
            self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = True
            self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
            self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
            self.settings[SETTING_FULL_CHARGE_LAST_RESULT] = "idle"
            migrated = True

        if not self._tariff_request_is_valid():
            if bool(self.settings[SETTING_TARIFF_ACTIVE]) or self.settings.get(
                SETTING_TARIFF_EXPIRES_AT
            ) is not None:
                self.settings[SETTING_TARIFF_ACTIVE] = False
                self.settings[SETTING_TARIFF_EXPIRES_AT] = None
                migrated = True

        if migrated:
            await self._store.async_save(self.settings)

        soc_entity = self.entry.data.get(CONF_SOC_ENTITY)
        current_soc = self._float_state(soc_entity) if soc_entity else None
        if (
            current_soc is not None
            and current_soc >= float(self.settings[SETTING_AUTO_TARGET_SOC])
            and self.settings[SETTING_FULL_CHARGE_LAST_RESULT]
            in ("confirmed", "timeout")
            and self._setting_datetime(SETTING_FULL_CHARGE_CONFIRMATION_STARTED)
            is None
        ):
            self._full_soc_latched = True

        self._schedule_cycle_check()
        self._schedule_tariff_expiry()
        self._unsub_state = async_track_state_change_event(
            self.hass, self.source_entities, self._async_state_changed
        )
        if not self._ha_started:
            self._unsub_started = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_home_assistant_started
            )
        self.async_calculate()
        self._schedule_startup_readiness()

    async def async_stop(self) -> None:
        """Stop all observation and writes without controlling external automations."""
        self._shutdown_in_progress = True
        self._control_apply_requested = False
        pending_tasks = [
            task
            for task in (
                self._control_apply_task,
                self._startup_ready_task,
                self._pv_release_task,
                self._full_battery_pv_entry_task,
                self._ac_pv_release_task,
                self._recovery_task,
                self._communication_pause_task,
                self._discharge_override_restore_task,
            )
            if task is not None and not task.done()
        ]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        if self._unsub_full_charge_confirmation:
            self._unsub_full_charge_confirmation()
            self._unsub_full_charge_confirmation = None
        self._control_apply_task = None
        self._startup_ready_task = None
        self._pv_release_task = None
        self._ac_pv_release_task = None
        self._recovery_task = None
        self._communication_pause_task = None
        self._discharge_override_restore_task = None
        if self.discharge_override_active:
            await self._async_restore_discharge_override(raise_on_error=False)
        if self._unsub_started:
            self._unsub_started()
            self._unsub_started = None
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_cycle_check:
            self._unsub_cycle_check()
            self._unsub_cycle_check = None
        if self._unsub_tariff_expiry:
            self._unsub_tariff_expiry()
            self._unsub_tariff_expiry = None

    @callback
    def _async_home_assistant_started(self, _event: Event) -> None:
        """Open the startup gate only after Home Assistant completed startup."""
        self._unsub_started = None
        self._ha_started = True
        self._data_valid_since_monotonic = monotonic() if self.data_valid else None
        self.async_calculate()
        self._schedule_startup_readiness()

    @callback
    def _schedule_startup_readiness(self) -> None:
        """Re-evaluate after inputs remained valid for the startup safety delay."""
        if (
            not self._ha_started
            or not self.data_valid
            or not self.regulation_enabled
            or self._write_blocked
            or self.control_ready
        ):
            return
        if self._startup_ready_task is None or self._startup_ready_task.done():
            self._startup_ready_task = self.hass.async_create_task(
                self._async_wait_until_ready()
            )

    async def _async_wait_until_ready(self) -> None:
        try:
            while (
                self._ha_started
                and self.data_valid
                and self.regulation_enabled
                and not self._write_blocked
                and not self.control_ready
            ):
                await asyncio.sleep(1)
            self.async_calculate()
        except asyncio.CancelledError:
            raise
        finally:
            self._startup_ready_task = None

    @callback
    def _async_state_changed(self, _event: Event) -> None:
        self.async_calculate()

    def _float_state(self, entity_id: str) -> float | None:
        state: State | None = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _input_issue(self, key: str, entity_id: str | None) -> dict[str, str] | None:
        """Describe why a required input cannot currently be used."""
        label = INPUT_LABELS.get(key, key)
        if not entity_id:
            return {
                "input": label,
                "entity_id": "",
                "state": "",
                "reason": "Nicht eingerichtet",
            }
        state: State | None = self.hass.states.get(entity_id)
        if state is None:
            return {
                "input": label,
                "entity_id": entity_id,
                "state": "",
                "reason": "Entität nicht gefunden",
            }
        if state.state == "unavailable":
            reason = "Entität nicht verfügbar"
        elif state.state == "unknown":
            reason = "Noch kein gültiger Messwert"
        elif state.state in ("none", ""):
            reason = "Messwert ist leer"
        else:
            try:
                float(state.state)
                return None
            except ValueError:
                reason = "Messwert ist keine Zahl"
        return {
            "input": label,
            "entity_id": entity_id,
            "state": state.state,
            "reason": reason,
        }

    @callback
    def async_calculate(self) -> None:
        """Calculate and, when ready, schedule production setpoint writes."""
        values: dict[str, float] = {}
        was_data_valid = self.data_valid
        previous_signature = tuple(
            (issue["input"], issue["entity_id"], issue["state"], issue["reason"])
            for issue in self.invalid_inputs
        )
        self.invalid_entities = []
        self.invalid_inputs = []
        for key in (
            CONF_SOC_ENTITY,
            CONF_PV_POWER_ENTITY,
            CONF_GRID_POWER_ENTITY,
            CONF_GRID_PORT_POWER_ENTITY,
            CONF_LOAD_PORT_POWER_ENTITY,
            CONF_GRID_SETPOINT_ENTITY,
            CONF_INVERTER_SETPOINT_ENTITY,
            CONF_MAX_CHARGE_SOC_ENTITY,
            CONF_MIN_DISCHARGE_SOC_ENTITY,
        ):
            entity_id = self.entry.data.get(key)
            issue = self._input_issue(key, entity_id)
            if issue is not None:
                self.invalid_entities.append(entity_id or f"missing:{key}")
                self.invalid_inputs.append(issue)
                continue
            values[key] = self._float_state(entity_id)

        ac_pv_power = 0.0
        ac_pv_entity = self.entry.data.get(CONF_AC_PV_POWER_ENTITY)
        self.ac_pv_input_issue = None
        self.ac_pv_input_valid = True
        if ac_pv_entity:
            self.ac_pv_input_issue = self._input_issue(
                CONF_AC_PV_POWER_ENTITY, ac_pv_entity
            )
            if self.ac_pv_input_issue is None:
                raw_ac_pv = self._float_state(ac_pv_entity) or 0.0
                ac_pv_power = normalize_pv_production(
                    raw_ac_pv,
                    production_negative=(
                        self.entry.data.get(CONF_AC_PV_SIGN)
                        == PV_PRODUCTION_NEGATIVE
                    ),
                )
            else:
                # The optional source improves display and plausibility only.
                # Public-grid feedback remains authoritative and keeps control
                # operational when this sensor is temporarily unavailable.
                self.ac_pv_input_valid = False

        self.data_valid = not self.invalid_entities
        if not self.data_valid:
            signature = tuple(
                (issue["input"], issue["entity_id"], issue["state"], issue["reason"])
                for issue in self.invalid_inputs
            )
            if signature != previous_signature:
                self.last_invalid_inputs = [dict(issue) for issue in self.invalid_inputs]
                self.last_invalid_at = datetime.now(UTC).isoformat()
                if (
                    self._ha_started
                    and (
                        was_data_valid
                        or self.result is not None
                        or self._communication_pause_active
                    )
                ):
                    _LOGGER.debug(
                        "XT500 input data invalid: %s",
                        "; ".join(
                            f"{issue['input']} ({issue['entity_id'] or 'nicht eingerichtet'}): "
                            f"{issue['reason']} [{issue['state'] or '-'}]"
                            for issue in self.invalid_inputs
                        ),
                    )
            if (
                self.regulation_enabled
                and self._ha_started
                and (self.result is not None or self._communication_pause_active)
            ):
                self._begin_communication_pause(
                    TransientCommunicationError(
                        "XT500-Eingangsdaten vorübergehend nicht lesbar"
                    )
                )
            self._data_valid_since_monotonic = None
            self._recovery_stable_since_monotonic = None
            self._next_recovery_attempt = None
            self._reset_pv_release_gates()
            self.result = None
            self.charge_request_active = False
            self.active_charge_source = "none"
            self.active_target_soc = None
            self.desired_charge_limit = None
            self._control_apply_requested = False
            self._schedule_recovery()
            self._notify()
            return

        if not was_data_valid and self.last_invalid_at is not None:
            self.last_inputs_recovered_at = datetime.now(UTC).isoformat()
            _LOGGER.info("XT500 input data is valid again")
        if self._data_valid_since_monotonic is None:
            self._data_valid_since_monotonic = monotonic()
        battery_flows = self._battery_flows()
        self._update_full_charge(
            values[CONF_SOC_ENTITY],
            battery_flows[0] if battery_flows is not None else None,
        )
        charge_hysteresis_entity = self.entry.data.get(
            CONF_CHARGE_SOC_HYSTERESIS_ENTITY
        )
        if charge_hysteresis_entity and (
            charge_hysteresis := self._float_state(charge_hysteresis_entity)
        ) is not None and float(
            self.settings[SETTING_CHARGE_SOC_HYSTERESIS]
        ) != charge_hysteresis:
            self.settings[SETTING_CHARGE_SOC_HYSTERESIS] = charge_hysteresis
            self._store.async_delay_save(lambda: self.settings, 1)

        if not self.regulation_enabled:
            self._cancel_recovery_task()
            self._recovery_status = "disabled"
            self._reset_pv_release_gates()
            self.result = None
            self.charge_request_active = False
            self.active_charge_source = "none"
            self.active_target_soc = None
            self.desired_charge_limit = None
            self._control_apply_requested = False
            self._notify()
            return

        normalized_grid = (
            values[CONF_GRID_POWER_ENTITY]
            if self.entry.data[CONF_METER_SIGN] == METER_EXPORT_POSITIVE
            else -values[CONF_GRID_POWER_ENTITY]
        )
        grid_port = decode_signed_16(values[CONF_GRID_PORT_POWER_ENTITY])
        available_ac_surplus = max(-(grid_port - normalized_grid), 0.0)
        self._update_pv_release_gates(
            values[CONF_PV_POWER_ENTITY], available_ac_surplus
        )

        manual_active = bool(self.settings[SETTING_MANUAL_ACTIVE])
        manual_target = float(self.settings[SETTING_TARGET_SOC])
        if manual_active and values[CONF_SOC_ENTITY] >= manual_target:
            self.settings[SETTING_MANUAL_ACTIVE] = False
            self._store.async_delay_save(lambda: self.settings, 1)
            manual_active = False

        manual_cycle_active = self.manual_cycle_requested
        automatic_cycle_active = self.automatic_cycle_requested
        tariff_active = self.tariff_request_active
        tariff_target = float(self.settings[SETTING_TARIFF_TARGET_SOC])
        if tariff_active and values[CONF_SOC_ENTITY] >= tariff_target:
            self.settings[SETTING_TARIFF_ACTIVE] = False
            self.settings[SETTING_TARIFF_EXPIRES_AT] = None
            self._cancel_tariff_expiry()
            self._store.async_delay_save(lambda: self.settings, 1)
            tariff_active = False

        charge_request = select_charge_request(
            manual_active=manual_active,
            manual_cycle_active=manual_cycle_active,
            automatic_cycle_active=automatic_cycle_active,
            tariff_active=tariff_active,
            manual_mode=self.settings[SETTING_MANUAL_MODE],
            cycle_mode=self.settings[SETTING_AUTO_MODE],
            manual_target_soc=float(self.settings[SETTING_TARGET_SOC]),
            cycle_target_soc=float(self.settings[SETTING_AUTO_TARGET_SOC]),
            tariff_target_soc=float(self.settings[SETTING_TARIFF_TARGET_SOC]),
            charge_power=float(self.settings[SETTING_CHARGE_POWER]),
            tariff_charge_power=float(self.settings[SETTING_TARIFF_CHARGE_POWER]),
        )
        if (
            charge_request.source in ("cycle_manual", "cycle_automatic")
            and self.full_charge_confirmation_active
        ):
            charge_request = replace(
                charge_request,
                charge_power=min(
                    charge_request.charge_power,
                    float(self.settings[SETTING_FULL_CHARGE_TOP_OFF_POWER]),
                ),
            )
        self.charge_request_active = charge_request.active
        self.active_charge_source = charge_request.source
        self.active_target_soc = (
            charge_request.target_soc if charge_request.active else None
        )

        charge_limit_state = self.hass.states.get(
            self.entry.data[CONF_MAX_CHARGE_SOC_ENTITY]
        )
        charge_limit_low = float(charge_limit_state.attributes.get("min", 0))
        charge_limit_high = float(charge_limit_state.attributes.get("max", 100))
        charge_limit_step = float(charge_limit_state.attributes.get("step", 1) or 1)
        charge_limit_sync = reconcile_normal_charge_limit(
            normal_limit=float(self.settings[SETTING_NORMAL_CHARGE_LIMIT]),
            device_limit=values[CONF_MAX_CHARGE_SOC_ENTITY],
            charge_active=charge_request.active,
            override_active=self._charge_limit_override_active,
            pending_write=self._normal_charge_limit_write_pending,
            low=charge_limit_low,
            high=charge_limit_high,
            step=charge_limit_step,
            feedback_trusted=(
                not self._write_blocked
                and not self._communication_pause_active
                and self._recovery_status in ("ready", "disabled")
            ),
        )
        if (
            float(self.settings[SETTING_NORMAL_CHARGE_LIMIT])
            != charge_limit_sync.normal_limit
        ):
            self.settings[SETTING_NORMAL_CHARGE_LIMIT] = (
                charge_limit_sync.normal_limit
            )
            self._store.async_delay_save(lambda: self.settings, 1)
        self._charge_limit_override_active = charge_limit_sync.override_active
        self._normal_charge_limit_write_pending = charge_limit_sync.pending_write
        self.desired_charge_limit = select_charge_limit(
            normal_limit=float(self.settings[SETTING_NORMAL_CHARGE_LIMIT]),
            target_soc=charge_request.target_soc,
            charge_active=charge_request.active,
            low=charge_limit_low,
            high=charge_limit_high,
            step=charge_limit_step,
        )
        self._full_battery_pv_hold = update_full_battery_pv_hold(
            current_hold=self._full_battery_pv_hold,
            soc=values[CONF_SOC_ENTITY],
            charge_limit=self.desired_charge_limit,
            enabled=bool(self.settings[SETTING_FULL_BATTERY_PV_EXPORT]),
            charge_active=charge_request.active,
        )

        device_minimum_soc = values[CONF_MIN_DISCHARGE_SOC_ENTITY]
        override_active = self.discharge_override_active
        stored_original_limit = self.settings.get(
            SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT
        )
        if override_active and stored_original_limit is not None:
            minimum_soc = float(stored_original_limit)
        else:
            minimum_soc = device_minimum_soc
            if float(self.settings[SETTING_MIN_SOC]) != minimum_soc:
                self.settings[SETTING_MIN_SOC] = minimum_soc
                self._store.async_delay_save(lambda: self.settings, 1)
        hysteresis = float(self.settings[SETTING_SOC_HYSTERESIS])
        device_hysteresis_entity = self.entry.data.get(
            CONF_DISCHARGE_SOC_HYSTERESIS_ENTITY
        )
        if device_hysteresis_entity and (
            device_hysteresis := self._float_state(device_hysteresis_entity)
        ) is not None:
            hysteresis = device_hysteresis
            if float(self.settings[SETTING_SOC_HYSTERESIS]) != hysteresis:
                self.settings[SETTING_SOC_HYSTERESIS] = hysteresis
                self._store.async_delay_save(lambda: self.settings, 1)
        temporary_release = (
            override_active
            and self._discharge_override_session_active
            and values[CONF_SOC_ENTITY] > minimum_soc
        )
        self._low_soc_hold = update_discharge_hold(
            current_hold=self._low_soc_hold,
            soc=values[CONF_SOC_ENTITY],
            minimum_soc=minimum_soc,
            hysteresis=hysteresis,
            temporary_release=temporary_release,
        )
        self._reserve_hold = update_discharge_hold(
            current_hold=self._reserve_hold,
            soc=values[CONF_SOC_ENTITY],
            minimum_soc=float(self.settings[SETTING_RESERVE_SOC]),
            hysteresis=min(hysteresis, 100 - float(self.settings[SETTING_RESERVE_SOC])),
        ) if self.settings[SETTING_RESERVE_ENABLED] else None
        if override_active and not temporary_release:
            self._schedule_discharge_override_restore()

        grid_setpoint_state = self.hass.states.get(
            self.entry.data[CONF_GRID_SETPOINT_ENTITY]
        )
        grid_charge_limit = abs(
            min(
                float(grid_setpoint_state.attributes.get("min", -2400)),
                0.0,
            )
        )

        self.result, self._full_battery_pv_transition = calculate_control_with_bypass_state(
            ControlInput(
                soc=values[CONF_SOC_ENTITY],
                pv_power=values[CONF_PV_POWER_ENTITY],
                grid_power=values[CONF_GRID_POWER_ENTITY],
                grid_port_power=values[CONF_GRID_PORT_POWER_ENTITY],
                load_port_power=values[CONF_LOAD_PORT_POWER_ENTITY],
                current_grid_setpoint=values[CONF_GRID_SETPOINT_ENTITY],
                current_inverter_setpoint=values[CONF_INVERTER_SETPOINT_ENTITY],
                ac_pv_power=ac_pv_power,
                battery_charge_power=(
                    battery_flows[0] if battery_flows is not None else None
                ),
                battery_discharge_power=(
                    battery_flows[1] if battery_flows is not None else None
                ),
            ),
            ControlSettings(
                charge_active=charge_request.active,
                charge_source=charge_request.source,
                charge_mode=charge_request.mode,
                base_mode=self.settings[SETTING_BASE_MODE],
                # At 100 percent the cycle remains active only while the
                # measured full-charge confirmation is still running.
                target_soc=(
                    101.0
                    if charge_request.source
                    in ("cycle_manual", "cycle_automatic")
                    and self.full_charge_confirmation_active
                    else charge_request.target_soc
                ),
                minimum_soc=minimum_soc,
                soc_hysteresis=hysteresis,
                discharge_hold=self.discharge_hold_active,
                charge_power=charge_request.charge_power,
                target_grid_power=float(self.settings[SETTING_TARGET_GRID_POWER]),
                grid_limit=float(self.settings[SETTING_MAX_GRID_OUTPUT]),
                grid_charge_limit=grid_charge_limit,
                inverter_limit=float(self.settings[SETTING_MAX_INVERTER_OUTPUT]),
                meter_export_positive=(
                    self.entry.data[CONF_METER_SIGN] == METER_EXPORT_POSITIVE
                ),
                pv_release_allowed=self._pv_release_active,
                ac_pv_release_allowed=self._ac_pv_release_active,
                pv_surplus_deadband=float(
                    self.settings[SETTING_PV_SURPLUS_DEADBAND]
                ),
                pv_surplus_charge_reserve=float(
                    self.settings[SETTING_PV_SURPLUS_CHARGE_RESERVE]
                ),
                full_battery_pv_export=bool(
                    self.settings[SETTING_FULL_BATTERY_PV_EXPORT]
                ) and not self.reserve_hold_active,
                full_battery_pv_hold=self._full_battery_pv_hold,
                coupling_mode=self.settings[SETTING_COUPLING_MODE],
            ),
            state=self._full_battery_pv_transition,
            now=monotonic(),
        )
        self._schedule_full_battery_pv_entry()
        self.result = replace(
            self.result,
            active_energy_source=classify_actual_energy_source(
                net_charge_power=(
                    battery_flows[0] if battery_flows is not None else None
                ),
                planned_source=self.result.active_energy_source,
                coupling_mode=self.result.selected_coupling_mode,
                dc_pv_power=self.result.dc_pv_power,
                available_ac_surplus=self.result.available_ac_surplus,
            ),
        )
        if not self._communication_pause_active:
            self._last_stable_display_status = self.result.status
        if self.control_ready:
            self._request_control_apply()
        elif self._write_blocked:
            self._schedule_recovery()
        else:
            self._schedule_startup_readiness()
        self._notify()

    @callback
    def _update_full_charge(
        self, soc: float, battery_charge_power: float | None
    ) -> None:
        """Record a full charge after a restart-safe 100 percent confirmation."""
        target = float(self.settings[SETTING_AUTO_TARGET_SOC])
        if target < 100:
            self._cancel_full_charge_confirmation_check()
            if self.full_charge_confirmation_state != "idle":
                self._clear_full_charge_confirmation("idle")
            self._update_immediate_full_charge(soc, target)
            return

        if self._full_soc_latched:
            if soc < target - 1:
                self._full_soc_latched = False
                self._clear_full_charge_confirmation("idle")
            self._cancel_full_charge_confirmation_check()
            return

        decision = update_full_charge_confirmation(
            now=dt_util.now(),
            soc=soc,
            target_soc=target,
            battery_charge_power=battery_charge_power,
            started_at=self._setting_datetime(
                SETTING_FULL_CHARGE_CONFIRMATION_STARTED
            ),
            taper_started_at=self._setting_datetime(SETTING_FULL_CHARGE_TAPER_STARTED),
            minimum_hold_minutes=float(
                self.settings[SETTING_FULL_CHARGE_MIN_HOLD_MINUTES]
            ),
            taper_power_w=float(self.settings[SETTING_FULL_CHARGE_TAPER_POWER]),
            taper_minutes=float(self.settings[SETTING_FULL_CHARGE_TAPER_MINUTES]),
            timeout_minutes=float(
                self.settings[SETTING_FULL_CHARGE_TIMEOUT_MINUTES]
            ),
        )
        changed = self._store_full_charge_decision(decision)
        if decision.complete:
            timestamp = dt_util.now().isoformat()
            self.settings[SETTING_LAST_FULL] = timestamp
            self.settings[SETTING_CYCLE_REFERENCE] = timestamp
            self.settings[SETTING_CYCLE_MANUAL_ACTIVE] = False
            self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = False
            self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
            self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
            self._full_soc_latched = True
            changed = True
            self._cancel_full_charge_confirmation_check()
        elif decision.started_at is not None:
            self._schedule_full_charge_confirmation_check()
        else:
            self._cancel_full_charge_confirmation_check()
        if changed:
            self._store.async_delay_save(lambda: self.settings, 1)

    def _update_immediate_full_charge(self, soc: float, target: float) -> None:
        """Retain the historical immediate behavior for targets below 100%."""
        if soc >= target:
            changed = False
            if not self._full_soc_latched:
                timestamp = dt_util.now().isoformat()
                self.settings[SETTING_LAST_FULL] = timestamp
                self.settings[SETTING_CYCLE_REFERENCE] = timestamp
                self._full_soc_latched = True
                changed = True
            if bool(self.settings[SETTING_CYCLE_MANUAL_ACTIVE]) or bool(
                self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE]
            ):
                self.settings[SETTING_CYCLE_MANUAL_ACTIVE] = False
                self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = False
                changed = True
            if changed:
                self._store.async_delay_save(lambda: self.settings, 1)
        elif soc < target - 1:
            self._full_soc_latched = False

    def _store_full_charge_decision(
        self, decision: FullChargeConfirmationDecision
    ) -> bool:
        """Persist confirmation progress only when one of its values changed."""
        values = {
            SETTING_FULL_CHARGE_CONFIRMATION_STARTED: (
                decision.started_at.isoformat() if decision.started_at else None
            ),
            SETTING_FULL_CHARGE_TAPER_STARTED: (
                decision.taper_started_at.isoformat()
                if decision.taper_started_at
                else None
            ),
            SETTING_FULL_CHARGE_LAST_RESULT: decision.state,
        }
        changed = any(self.settings.get(key) != value for key, value in values.items())
        self.settings.update(values)
        return changed

    def _clear_full_charge_confirmation(self, state: str = "idle") -> None:
        """Clear persisted progress after SOC leaves the full-charge band."""
        self._cancel_full_charge_confirmation_check()
        self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_LAST_RESULT] = state
        self._store.async_delay_save(lambda: self.settings, 1)

    @callback
    def _schedule_full_charge_confirmation_check(self) -> None:
        """Keep confirmation moving even when repeated values do not change."""
        self._cancel_full_charge_confirmation_check()
        self._unsub_full_charge_confirmation = async_call_later(
            self.hass,
            max(self.source_polling_interval, 3.0),
            self._async_full_charge_confirmation_check,
        )

    @callback
    def _cancel_full_charge_confirmation_check(self) -> None:
        """Cancel the pending confirmation reevaluation."""
        if self._unsub_full_charge_confirmation:
            self._unsub_full_charge_confirmation()
            self._unsub_full_charge_confirmation = None

    @callback
    def _async_full_charge_confirmation_check(self, _now: datetime) -> None:
        """Reevaluate a pending full charge from its persisted timestamps."""
        self._unsub_full_charge_confirmation = None
        self.async_calculate()

    @property
    def full_charge_confirmation_active(self) -> bool:
        """Return whether a 100 percent observation is currently pending."""
        return (
            not self._full_soc_latched
            and self._setting_datetime(SETTING_FULL_CHARGE_CONFIRMATION_STARTED)
            is not None
        )

    @property
    def full_charge_confirmation_state(self) -> str:
        """Return the persisted state of the latest confirmation attempt."""
        return str(self.settings.get(SETTING_FULL_CHARGE_LAST_RESULT, "idle"))

    @property
    def cycle_due(self) -> bool:
        """Return whether the configured full-charge interval has elapsed."""
        return cycle_is_due(
            now=dt_util.now(),
            last_full=self._setting_datetime(SETTING_LAST_FULL),
            cycle_reference=self._setting_datetime(SETTING_CYCLE_REFERENCE),
            interval_days=float(self.settings[SETTING_CYCLE_INTERVAL_DAYS]),
        )

    def _setting_datetime(self, key: str) -> datetime | None:
        """Parse one persisted scheduling timestamp."""
        value = self.settings.get(key)
        if not isinstance(value, str):
            return None
        return dt_util.parse_datetime(value)

    def _tariff_request_is_valid(self) -> bool:
        """Return whether the external tariff request is active and unexpired."""
        expires_at = self._setting_datetime(SETTING_TARIFF_EXPIRES_AT)
        return bool(self.settings[SETTING_TARIFF_ACTIVE]) and (
            expires_at is not None and expires_at > dt_util.now()
        )

    @property
    def tariff_request_active(self) -> bool:
        """Return whether a valid tariff charge request currently exists."""
        return self._tariff_request_is_valid()

    @property
    def tariff_expires_datetime(self) -> datetime | None:
        """Return the current tariff-request expiry for dashboard display."""
        if not self.tariff_request_active:
            return None
        return self._setting_datetime(SETTING_TARIFF_EXPIRES_AT)

    @callback
    def _cancel_tariff_expiry(self) -> None:
        if self._unsub_tariff_expiry:
            self._unsub_tariff_expiry()
            self._unsub_tariff_expiry = None

    @callback
    def _schedule_tariff_expiry(self) -> None:
        """Stop an external tariff request when its safety window ends."""
        self._cancel_tariff_expiry()
        expires_at = self._setting_datetime(SETTING_TARIFF_EXPIRES_AT)
        if not self.tariff_request_active or expires_at is None:
            return
        delay = max((expires_at - dt_util.now()).total_seconds(), 0.0)
        self._unsub_tariff_expiry = async_call_later(
            self.hass, delay, self._async_tariff_expired
        )

    @callback
    def _async_tariff_expired(self, _now: datetime) -> None:
        self._unsub_tariff_expiry = None
        self.settings[SETTING_TARIFF_ACTIVE] = False
        self.settings[SETTING_TARIFF_EXPIRES_AT] = None
        self._store.async_delay_save(lambda: self.settings, 1)
        self.async_calculate()

    @callback
    def async_set_tariff_active(self, active: bool) -> None:
        """Set or refresh the externally controlled tariff charge request."""
        self.settings[SETTING_TARIFF_ACTIVE] = active
        self.settings[SETTING_TARIFF_EXPIRES_AT] = (
            (
                dt_util.now()
                + timedelta(
                    minutes=max(
                        float(self.settings[SETTING_TARIFF_REQUEST_DURATION]), 1.0
                    )
                )
            ).isoformat()
            if active
            else None
        )
        self._schedule_tariff_expiry()
        self._store.async_delay_save(lambda: self.settings, 1)
        self.async_calculate()

    @property
    def next_cycle_at(self) -> str | None:
        """Return the next daily check at which a due cycle may start."""
        next_cycle = self.next_cycle_datetime
        return next_cycle.isoformat() if next_cycle is not None else None

    @property
    def next_cycle_datetime(self) -> datetime | None:
        """Return the next scheduled cycle check as a timezone-aware datetime."""
        baseline = self._setting_datetime(
            SETTING_LAST_FULL
        ) or self._setting_datetime(SETTING_CYCLE_REFERENCE)
        if baseline is None:
            return None
        return next_cycle_check_at(
            baseline=baseline,
            interval_days=float(self.settings[SETTING_CYCLE_INTERVAL_DAYS]),
            check_time=self.cycle_check_time,
        )

    def _battery_flows(self) -> tuple[float, float] | None:
        """Return actual charge/discharge, preferring the original signed BP."""
        battery_entity = self.entry.data.get(CONF_BATTERY_POWER_ENTITY)
        if battery_entity:
            battery_power = self._float_state(battery_entity)
            if battery_power is not None:
                return signed_battery_flows(battery_power)
        input_entity = self.entry.data.get(CONF_BATTERY_INPUT_POWER_ENTITY)
        output_entity = self.entry.data.get(CONF_BATTERY_OUTPUT_POWER_ENTITY)
        if not input_entity or not output_entity:
            return None
        input_power = self._float_state(input_entity)
        output_power = self._float_state(output_entity)
        if input_power is None or output_power is None:
            return None
        return net_battery_flows(input_power, output_power)

    @property
    def battery_charge_power(self) -> float | None:
        """Return actual net battery charging power."""
        flows = self._battery_flows()
        return flows[0] if flows is not None else None

    @property
    def battery_discharge_power(self) -> float | None:
        """Return actual net battery discharging power."""
        flows = self._battery_flows()
        return flows[1] if flows is not None else None

    @property
    def cycle_check_time(self) -> time:
        """Return the configured local daily cycle-check time."""
        value = self.settings.get(SETTING_CYCLE_CHECK_TIME)
        if isinstance(value, str):
            try:
                return time.fromisoformat(value)
            except ValueError:
                pass
        return time(hour=12)

    @callback
    def _schedule_cycle_check(self) -> None:
        """Schedule the persistent local-time daily cycle check."""
        if self._unsub_cycle_check:
            self._unsub_cycle_check()
        check_time = self.cycle_check_time
        self._unsub_cycle_check = async_track_time_change(
            self.hass,
            self._async_cycle_check,
            hour=check_time.hour,
            minute=check_time.minute,
            second=check_time.second,
        )

    @callback
    def _async_cycle_check(self, _now: datetime) -> None:
        """Start one due automatic cycle at the configured daily check."""
        if not self._activate_automatic_cycle_if_due():
            return
        self._store.async_delay_save(lambda: self.settings, 1)
        self.async_calculate()

    def _automatic_cycle_should_start_now(self) -> bool:
        """Return whether the first eligible daily check has already passed."""
        if (
            not bool(self.settings[SETTING_AUTO_ENABLED])
            or bool(self.settings[SETTING_CYCLE_MANUAL_ACTIVE])
            or bool(self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE])
            or not self.cycle_due
        ):
            return False
        baseline = self._setting_datetime(
            SETTING_LAST_FULL
        ) or self._setting_datetime(SETTING_CYCLE_REFERENCE)
        if baseline is None:
            return False
        scheduled = next_cycle_check_at(
            baseline=baseline,
            interval_days=float(self.settings[SETTING_CYCLE_INTERVAL_DAYS]),
            check_time=self.cycle_check_time,
        )
        return dt_util.now() >= scheduled

    @callback
    def _activate_automatic_cycle_if_due(self) -> bool:
        """Latch one automatic cycle when monitoring is enabled and due."""
        if (
            not bool(self.settings[SETTING_AUTO_ENABLED])
            or bool(self.settings[SETTING_CYCLE_MANUAL_ACTIVE])
            or bool(self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE])
            or not self.cycle_due
        ):
            return False
        self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = True
        self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_LAST_RESULT] = "idle"
        self._full_soc_latched = False
        return True

    @property
    def manual_cycle_requested(self) -> bool:
        """Return whether a manually started cycle currently requests charging."""
        return self.regulation_enabled and bool(
            self.settings[SETTING_CYCLE_MANUAL_ACTIVE]
        )

    @property
    def automatic_cycle_requested(self) -> bool:
        """Return whether the integration currently requests an automatic cycle."""
        return self.regulation_enabled and bool(
            self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE]
        )

    @property
    def cycle_charge_active(self) -> bool:
        """Return whether a cycle request is actively controlling the battery."""
        return (
            self.data_valid
            and not bool(self.settings[SETTING_MANUAL_ACTIVE])
            and (self.manual_cycle_requested or self.automatic_cycle_requested)
        )

    @property
    def cycle_state(self) -> str:
        """Return an explicit monitoring-versus-charging cycle state."""
        manual = bool(self.settings[SETTING_CYCLE_MANUAL_ACTIVE])
        automatic = bool(self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE])
        if manual or automatic:
            if (
                not self.regulation_enabled
                or not self.data_valid
                or bool(self.settings[SETTING_MANUAL_ACTIVE])
            ):
                return "paused"
            if self.full_charge_confirmation_active:
                return "confirming_full"
            return "manual_active" if manual else "automatic_active"
        if not bool(self.settings[SETTING_AUTO_ENABLED]):
            return "monitoring_disabled"
        if self.cycle_due:
            return "due_waiting"
        return "monitoring"

    @property
    def regulation_enabled(self) -> bool:
        """Return whether this production controller is enabled."""
        return bool(self.settings[SETTING_REGULATION_ENABLED])

    @property
    def discharge_hold_active(self) -> bool:
        """Return whether battery discharge is currently blocked by SOC."""
        return bool(self._low_soc_hold) or self.reserve_hold_active

    @property
    def reserve_hold_active(self) -> bool:
        return bool(self.settings[SETTING_RESERVE_ENABLED] and self._reserve_hold)

    @property
    def reserve_release_soc(self) -> float:
        return min(100.0, float(self.settings[SETTING_RESERVE_SOC]) + float(self.settings[SETTING_SOC_HYSTERESIS]))

    @property
    def discharge_override_active(self) -> bool:
        """Return whether the one-shot discharge release is active."""
        return bool(self.settings[SETTING_DISCHARGE_OVERRIDE_ACTIVE])

    @property
    def discharge_release_soc(self) -> float:
        """Return the SOC at which the normal hysteresis releases discharge."""
        minimum = self.settings.get(
            SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT,
            self.settings[SETTING_MIN_SOC],
        )
        if minimum is None:
            minimum = self.settings[SETTING_MIN_SOC]
        return float(minimum) + float(self.settings[SETTING_SOC_HYSTERESIS])

    @property
    def automatic_recovery_enabled(self) -> bool:
        """Return whether a latched write error may recover automatically."""
        return bool(self.settings[SETTING_AUTOMATIC_RECOVERY_ENABLED])

    @property
    def recovery_status(self) -> str:
        """Return the current automatic-recovery state."""
        if not self.regulation_enabled:
            return "disabled"
        if not self._write_blocked:
            return "ready"
        if not self.automatic_recovery_enabled:
            return "manual_required"
        return self._recovery_status

    @property
    def recovery_attempts(self) -> int:
        """Return the number of automatic attempts in the current error episode."""
        return self._recovery_attempts

    @property
    def recovery_max_attempts(self) -> int:
        """Return the fixed safety limit for automatic recovery attempts."""
        return len(RECOVERY_DELAY_MULTIPLIERS)

    @property
    def next_recovery_attempt(self) -> str | None:
        """Return the scheduled automatic recovery time, if any."""
        return self._next_recovery_attempt

    @property
    def control_ready(self) -> bool:
        """Return whether production writes are currently permitted."""
        return (
            self.regulation_enabled
            and self._ha_started
            and self.data_valid
            and self.result is not None
            and not self._write_blocked
            and not self._shutdown_in_progress
            and not self._communication_pause_active
            and self._data_valid_since_monotonic is not None
            and monotonic() - self._data_valid_since_monotonic
            >= _STARTUP_STABILITY_SECONDS
        )

    @property
    def control_operational(self) -> bool:
        """Return stable user-facing readiness across short communication pauses.

        Short communication pauses still stop writes immediately through
        ``control_ready``.  Only an already running controller keeps its public
        readiness state during that pause; startup and hard faults remain off.
        """
        return self.control_ready or (
            self._communication_pause_active
            and self._last_stable_display_status is not None
            and self.regulation_enabled
            and self._ha_started
            and not self._write_blocked
            and not self._shutdown_in_progress
        )

    @property
    def communication_pause_visible(self) -> bool:
        """Return whether the current transient pause outlived its grace time."""
        return (
            self._communication_pause_active
            and self._communication_pause_started_monotonic is not None
            and communication_pause_is_visible(
                monotonic() - self._communication_pause_started_monotonic,
                _COMMUNICATION_DISPLAY_DELAY_SECONDS,
            )
        )

    @property
    def display_status(self) -> str:
        """Return the user-facing production state."""
        if not self.regulation_enabled:
            return "disabled"
        if self._communication_pause_active:
            if self.communication_pause_visible:
                return "communication_pause"
            return self._last_stable_display_status or "starting"
        if not self.data_valid or self.result is None:
            return "invalid_data"
        if self._write_blocked:
            return "control_error"
        if not self.control_ready:
            return "starting"
        return self.result.status

    @property
    def pv_release_active(self) -> bool:
        """Return whether direct XT500 PV is released above the hysteresis."""
        return self._pv_release_active

    @property
    def ac_pv_release_active(self) -> bool:
        """Return whether reconstructed AC surplus passed the hysteresis."""
        return self._ac_pv_release_active

    @callback
    def _update_pv_release_gates(
        self, dc_pv_power: float, ac_surplus_power: float
    ) -> None:
        """Update independent DC and AC gates so neither unlocks the other."""
        self._update_pv_release_gate("dc", dc_pv_power)
        self._update_pv_release_gate("ac", ac_surplus_power)

    @callback
    def _update_pv_release_gate(self, source: str, pv_power: float) -> None:
        """Update one low-PV lockout and its continuous-start timer."""
        now = monotonic()
        is_ac = source == "ac"
        active = self._ac_pv_release_active if is_ac else self._pv_release_active
        above_since = (
            self._ac_pv_above_start_since
            if is_ac
            else self._pv_above_start_since
        )
        decision = update_pv_release(
            active=active,
            pv_power=pv_power,
            stop_power=float(self.settings[SETTING_PV_STOP_POWER]),
            start_power=float(self.settings[SETTING_PV_START_POWER]),
            start_delay=float(self.settings[SETTING_PV_START_DELAY]),
            above_start_since=above_since,
            now=now,
        )
        if is_ac:
            self._ac_pv_release_active = decision.active
            self._ac_pv_above_start_since = decision.above_start_since
        else:
            self._pv_release_active = decision.active
            self._pv_above_start_since = decision.above_start_since

        if decision.remaining_delay is None:
            self._cancel_pv_release_timer(source)
            return

        due = now + decision.remaining_delay
        task = self._ac_pv_release_task if is_ac else self._pv_release_task
        scheduled_due = (
            self._ac_pv_release_due_monotonic
            if is_ac
            else self._pv_release_due_monotonic
        )
        if (
            task is not None
            and not task.done()
            and scheduled_due is not None
            and abs(scheduled_due - due) < 0.1
        ):
            return
        self._cancel_pv_release_timer(source)
        new_task = self.hass.async_create_task(
            self._async_pv_release_wait(source, decision.remaining_delay)
        )
        if is_ac:
            self._ac_pv_release_due_monotonic = due
            self._ac_pv_release_task = new_task
        else:
            self._pv_release_due_monotonic = due
            self._pv_release_task = new_task

    async def _async_pv_release_wait(self, source: str, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if source == "ac":
            self._ac_pv_release_task = None
            self._ac_pv_release_due_monotonic = None
        else:
            self._pv_release_task = None
            self._pv_release_due_monotonic = None
        self.async_calculate()

    @callback
    def _cancel_pv_release_timer(self, source: str) -> None:
        is_ac = source == "ac"
        task = self._ac_pv_release_task if is_ac else self._pv_release_task
        if task is not None and not task.done():
            task.cancel()
        if is_ac:
            self._ac_pv_release_task = None
            self._ac_pv_release_due_monotonic = None
        else:
            self._pv_release_task = None
            self._pv_release_due_monotonic = None

    @callback
    def _schedule_full_battery_pv_entry(self) -> None:
        """Wake up even when measurements remain unchanged during entry."""
        since = self._full_battery_pv_transition.eligible_since
        if since is None:
            if self._full_battery_pv_entry_task is not None:
                self._full_battery_pv_entry_task.cancel()
                self._full_battery_pv_entry_task = None
            return
        if self._full_battery_pv_entry_task is None:
            self._full_battery_pv_entry_task = self.hass.async_create_task(
                self._async_wait_for_full_battery_pv_entry(since)
            )

    async def _async_wait_for_full_battery_pv_entry(self, since: float) -> None:
        try:
            await asyncio.sleep(max(
                since + FULL_BATTERY_PV_ENTRY_DELAY - monotonic(), 0.0
            ))
        except asyncio.CancelledError:
            return
        self._full_battery_pv_entry_task = None
        self.async_calculate()

    @callback
    def _reset_pv_release_gates(self) -> None:
        """Cancel gate timers and reset transient PV eligibility."""
        self._full_battery_pv_transition = FullBatteryBypassState()
        self._schedule_full_battery_pv_entry()
        self._cancel_pv_release_timer("dc")
        self._cancel_pv_release_timer("ac")
        self._pv_release_active = False
        self._pv_above_start_since = None
        self._ac_pv_release_active = False
        self._ac_pv_above_start_since = None

    @property
    def control_error(self) -> float:
        """Return the largest deviation used for adaptive control."""
        if self.result is None:
            return 0.0
        current_grid = self._float_state(self.entry.data[CONF_GRID_SETPOINT_ENTITY])
        current_inverter = self._float_state(
            self.entry.data[CONF_INVERTER_SETPOINT_ENTITY]
        )
        if current_grid is None or current_inverter is None:
            return 0.0
        return overall_control_error(
            public_grid_power=self.result.normalized_grid_power,
            public_grid_target=self.result.effective_public_grid_target,
            current_grid_setpoint=current_grid,
            requested_grid_setpoint=self.result.recommended_grid_setpoint,
            current_inverter_setpoint=current_inverter,
            requested_inverter_setpoint=self.result.recommended_inverter_setpoint,
        )

    @property
    def control_profile(self) -> AdaptiveControlProfile:
        """Return the adaptive response band for the latest setpoints."""
        return select_adaptive_control_profile(
            self.control_error,
            small_error=float(self.settings[SETTING_CONTROL_SMALL_ERROR]),
            large_error=float(self.settings[SETTING_CONTROL_LARGE_ERROR]),
            slow_interval=float(self.settings[SETTING_CONTROL_SLOW_INTERVAL]),
            medium_interval=float(self.settings[SETTING_CONTROL_MEDIUM_INTERVAL]),
            fast_interval=float(self.settings[SETTING_CONTROL_FAST_INTERVAL]),
            small_maximum_change=float(
                self.settings[SETTING_CONTROL_SMALL_MAX_STEP]
            ),
            medium_maximum_change=float(
                self.settings[SETTING_CONTROL_MEDIUM_MAX_STEP]
            ),
            large_maximum_change=float(
                self.settings[SETTING_CONTROL_LARGE_MAX_STEP]
            ),
        )

    @property
    def effective_control_interval(self) -> float:
        """Return adaptive interval including feedback settling time."""
        return max(
            self.control_profile.interval,
            float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]),
        )

    @property
    def source_polling_interval(self) -> float:
        """Return the polling interval configured on SunEnergyXT 1.1.3+."""
        source_entity = self.entry.data.get(CONF_GRID_PORT_POWER_ENTITY)
        registry_entry = (
            er.async_get(self.hass).async_get(source_entity)
            if source_entity
            else None
        )
        source_entry = (
            self.hass.config_entries.async_get_entry(registry_entry.config_entry_id)
            if registry_entry is not None and registry_entry.config_entry_id
            else None
        )
        try:
            interval = float(
                source_entry.options.get(
                    "polling_interval", _DEFAULT_SOURCE_POLLING_INTERVAL
                )
                if source_entry is not None
                else _DEFAULT_SOURCE_POLLING_INTERVAL
            )
        except (TypeError, ValueError):
            interval = _DEFAULT_SOURCE_POLLING_INTERVAL
        return max(
            _MIN_SOURCE_POLLING_INTERVAL,
            min(_MAX_SOURCE_POLLING_INTERVAL, interval),
        )

    @property
    def communication_failure_seconds(self) -> float:
        """Allow at least two source polling cycles before a hard stop."""
        return max(
            _COMMUNICATION_FAILURE_SECONDS,
            self.source_polling_interval * 2,
        )

    @property
    def feedback_ready(self) -> bool:
        """Return whether both feedback sources updated after the last setpoint write."""
        return feedback_samples_are_fresh(
            self._last_control_write_at,
            self._feedback_sample_times(),
        )

    def _feedback_sample_times(self) -> tuple[datetime | None, datetime | None]:
        """Return the newest report time for both controller feedback sources."""
        samples: list[datetime | None] = []
        for key in (CONF_GRID_POWER_ENTITY, CONF_GRID_PORT_POWER_ENTITY):
            state = self.hass.states.get(self.entry.data[key])
            if state is None:
                samples.append(None)
                continue
            samples.append(
                getattr(state, "last_reported", None) or state.last_updated
            )
        return samples[0], samples[1]

    @property
    def recovery_feedback_ready(self) -> bool:
        """Return whether both feedback sources reported after the last error."""
        return feedback_samples_are_fresh(
            self._control_error_at,
            self._feedback_sample_times(),
        )

    @property
    def recovery_feedback_current(self) -> bool:
        """Return whether both recovery feedback samples are still recent."""
        max_age = max(
            float(self.settings[SETTING_RECOVERY_STABILITY_TIME]) * 1.5,
            _RECOVERY_FEEDBACK_TIMEOUT_SECONDS,
            self.source_polling_interval * 1.5 + 5.0,
        )
        now = datetime.now(UTC)
        return all(
            sample is not None
            and 0 <= (now - sample).total_seconds() <= max_age
            for sample in self._feedback_sample_times()
        )

    async def async_set_regulation_enabled(self, enabled: bool) -> None:
        """Enable or stop all production writes."""
        self._cancel_recovery_task()
        self._clear_communication_pause()
        self._recovery_stable_since_monotonic = None
        self._next_recovery_attempt = None
        self._recovery_attempts = 0
        if not enabled:
            self._shutdown_in_progress = True
            self._shutdown_failed = False
            await self._async_cancel_control_apply()
            try:
                if self.discharge_override_active:
                    await self._async_restore_discharge_override()
                await self._async_neutralize_outputs()
            except Exception as err:
                self._shutdown_failed = True
                self._write_blocked = True
                self._control_error_at = datetime.now(UTC)
                self.control_error_message = (
                    "Sicheres Abschalten fehlgeschlagen: "
                    f"{self._error_detail(err)}"
                )
                self._recovery_status = "manual_required"
                self._notify()
                raise HomeAssistantError(self.control_error_message) from err
            finally:
                self._shutdown_in_progress = False
            self._write_blocked = False
            self._control_error_at = None
            self.control_error_message = None
            self._last_control_write_at = None
            self._recovery_status = "disabled"
        else:
            self._shutdown_in_progress = False
            self._shutdown_failed = False
            self._write_blocked = False
            self._control_error_at = None
            self.control_error_message = None
            self._data_valid_since_monotonic = None
            self._recovery_status = "ready"
        self.settings[SETTING_REGULATION_ENABLED] = enabled
        await self._store.async_save(self.settings)
        self.async_calculate()

    async def _async_cancel_control_apply(self) -> None:
        """Stop a pending production write before changing controller ownership."""
        self._control_apply_requested = False
        task = self._control_apply_task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _async_neutralize_outputs(self) -> None:
        """Put every device actuator into a deterministic inactive state."""
        grid_entity = self.entry.data[CONF_GRID_SETPOINT_ENTITY]
        inverter_entity = self.entry.data[CONF_INVERTER_SETPOINT_ENTITY]
        charge_limit_entity = self.entry.data[CONF_MAX_CHARGE_SOC_ENTITY]
        targets = (
            (grid_entity, self._quantized_entity_target(grid_entity, 0.0)),
            (inverter_entity, self._quantized_entity_target(inverter_entity, 0.0)),
            (
                charge_limit_entity,
                self._quantized_entity_target(
                    charge_limit_entity,
                    float(self.settings[SETTING_NORMAL_CHARGE_LIMIT]),
                ),
            ),
        )
        confirmation_timeout = max(
            float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]) * 2,
            5.0,
        )
        wrote = False
        for entity_id, target in targets:
            if self._float_state(entity_id) is None:
                raise TransientCommunicationError(
                    f"Sollwert beim Abschalten nicht lesbar: {entity_id}"
                )
            if not self._entity_target_matches(entity_id, target):
                await self._async_set_number_resilient(entity_id, target)
                wrote = True
            if not self._entity_target_matches(
                entity_id, target
            ) and not await self._async_wait_for_entity_target(
                entity_id, target, confirmation_timeout
            ):
                raise HomeAssistantError(
                    f"Sicherer Abschaltwert {target:g} nicht bestätigt: "
                    f"{entity_id}"
                )
        self._charge_limit_override_active = False
        self._normal_charge_limit_write_pending = None
        if wrote:
            self.last_control_write = dt_util.now().isoformat()
            self._notify()

    @callback
    def _cancel_recovery_task(self) -> None:
        """Cancel a pending automatic recovery without touching the master switch."""
        if self._recovery_task is not None and not self._recovery_task.done():
            self._recovery_task.cancel()
        self._recovery_task = None
        self._next_recovery_attempt = None

    @callback
    def _request_control_apply(self) -> None:
        """Coalesce state changes into one adaptive, rate-limited write task."""
        if not self.control_ready:
            return
        self._control_apply_requested = True
        if self._control_apply_task is None or self._control_apply_task.done():
            self._control_apply_task = self.hass.async_create_task(
                self._async_control_apply_loop()
            )

    async def _async_control_apply_loop(self) -> None:
        try:
            while self._control_apply_requested and self.control_ready:
                self._control_apply_requested = False
                remaining = self.effective_control_interval - (
                    monotonic() - self._last_control_apply_monotonic
                )
                if remaining > 0:
                    await asyncio.sleep(remaining)
                if not self.control_ready:
                    return
                if not self.feedback_ready:
                    return
                await self._async_apply_control_result(
                    self.control_profile.maximum_change
                )
        except asyncio.CancelledError:
            raise
        except TransientCommunicationError as err:
            _LOGGER.debug(
                "XT500 communication interrupted; production writes paused: %s",
                self._error_detail(err),
            )
            self._begin_communication_pause(err)
        except Exception as err:
            _LOGGER.exception("XT500 production write failed")
            self._begin_control_error(err)
        finally:
            self._control_apply_task = None
            if self._control_apply_requested and self.control_ready:
                self._control_apply_task = self.hass.async_create_task(
                    self._async_control_apply_loop()
                )

    @staticmethod
    def _error_detail(err: Exception) -> str:
        """Return a useful error text even for exceptions such as TimeoutError."""
        detail = str(err).strip()
        return detail if detail else type(err).__name__

    @callback
    def _begin_control_error(self, err: Exception) -> None:
        """Latch a production write error and start the guarded recovery flow."""
        self._clear_communication_pause()
        self._write_blocked = True
        self._charge_limit_override_active = True
        self._control_error_at = datetime.now(UTC)
        self.control_error_message = f"Schreibfehler: {self._error_detail(err)}"
        self._control_apply_requested = False
        self._recovery_attempts = 0
        self._recovery_stable_since_monotonic = None
        self._next_recovery_attempt = None
        self._recovery_status = (
            "waiting_feedback"
            if self.automatic_recovery_enabled
            else "manual_required"
        )
        self._cancel_recovery_task()
        self._schedule_recovery()
        self._notify()

    @property
    def communication_pause_active(self) -> bool:
        """Return whether writes wait for stable communication."""
        return self._communication_pause_active

    @property
    def communication_pause_since(self) -> str | None:
        """Return the beginning of the current communication pause."""
        return (
            self._communication_pause_at.isoformat()
            if self._communication_pause_at is not None
            else None
        )

    @callback
    def _begin_communication_pause(self, err: Exception) -> None:
        """Pause writes for a transient outage without latching immediately."""
        if self._write_blocked or not self.regulation_enabled:
            return
        if not self._communication_pause_active:
            self._communication_pause_active = True
            self._charge_limit_override_active = True
            self._communication_pause_at = datetime.now(UTC)
            self._communication_pause_started_monotonic = monotonic()
            self._communication_stable_since_monotonic = None
            self._communication_pause_warning_logged = False
        self.communication_pause_message = self._error_detail(err)
        self._control_apply_requested = False
        self._data_valid_since_monotonic = None
        if (
            self._communication_pause_task is None
            or self._communication_pause_task.done()
        ):
            self._communication_pause_task = self.hass.async_create_task(
                self._async_monitor_communication_pause()
            )
        self._notify()

    @callback
    def _clear_communication_pause(self) -> None:
        """Clear the transient pause and cancel its watchdog when appropriate."""
        task = self._communication_pause_task
        current_task = asyncio.current_task()
        if (
            task is not None
            and not task.done()
            and task is not current_task
        ):
            task.cancel()
        if task is not current_task:
            self._communication_pause_task = None
        self._communication_pause_active = False
        self._communication_pause_at = None
        self._communication_pause_started_monotonic = None
        self._communication_stable_since_monotonic = None
        self._communication_pause_warning_logged = False
        self.communication_pause_message = None

    async def _async_monitor_communication_pause(self) -> None:
        """Resume after stable fresh feedback or hard-stop a long outage."""
        current_task = asyncio.current_task()
        try:
            while (
                self._communication_pause_active
                and self.regulation_enabled
                and not self._write_blocked
            ):
                now = monotonic()
                pause_elapsed = (
                    now - self._communication_pause_started_monotonic
                    if self._communication_pause_started_monotonic is not None
                    else 0.0
                )
                if (
                    not self._communication_pause_warning_logged
                    and communication_pause_is_visible(
                        pause_elapsed,
                        _COMMUNICATION_DISPLAY_DELAY_SECONDS,
                    )
                ):
                    self._communication_pause_warning_logged = True
                    _LOGGER.warning(
                        "XT500 communication pause persists for %.0f seconds: %s",
                        pause_elapsed,
                        self.communication_pause_message or "unknown cause",
                    )
                    self._notify()
                feedback_fresh = (
                    self._communication_pause_at is not None
                    and feedback_samples_are_fresh(
                        self._communication_pause_at,
                        self._feedback_sample_times(),
                    )
                )
                if self.data_valid and self.result is not None and feedback_fresh:
                    if self._communication_stable_since_monotonic is None:
                        self._communication_stable_since_monotonic = now
                    elif (
                        now - self._communication_stable_since_monotonic
                        >= _COMMUNICATION_STABILITY_SECONDS
                    ):
                        self._clear_communication_pause()
                        self._data_valid_since_monotonic = (
                            monotonic() - _STARTUP_STABILITY_SECONDS
                        )
                        self._notify()
                        self.async_calculate()
                        return
                else:
                    self._communication_stable_since_monotonic = None

                if (
                    self._communication_pause_started_monotonic is not None
                    and now - self._communication_pause_started_monotonic
                    >= self.communication_failure_seconds
                ):
                    self._begin_control_error(
                        HomeAssistantError(
                            "XT500-Kommunikation länger als "
                            f"{self.communication_failure_seconds:g} Sekunden "
                            "nicht stabil"
                        )
                    )
                    return
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        finally:
            if self._communication_pause_task is current_task:
                self._communication_pause_task = None

    @callback
    def _schedule_recovery(self) -> None:
        """Schedule one guarded recovery attempt after stable fresh feedback."""
        if not self._write_blocked:
            self._recovery_status = "ready"
            return
        if self._shutdown_failed:
            self._cancel_recovery_task()
            self._recovery_status = "manual_required"
            return
        if (
            self._recovery_status == "attempting"
            and self._recovery_task is not None
            and not self._recovery_task.done()
        ):
            return
        if not self.regulation_enabled:
            self._cancel_recovery_task()
            self._recovery_status = "disabled"
            return
        if not self.automatic_recovery_enabled:
            self._cancel_recovery_task()
            self._recovery_status = "manual_required"
            return
        if self._recovery_attempts >= self.recovery_max_attempts:
            self._cancel_recovery_task()
            self._recovery_status = "exhausted"
            return
        if (
            not self._ha_started
            or not self.data_valid
            or self.result is None
        ):
            self._cancel_recovery_task()
            self._recovery_stable_since_monotonic = None
            self._recovery_status = "waiting_inputs"
            return
        if (
            not self.recovery_feedback_ready
            or not self.recovery_feedback_current
        ):
            self._cancel_recovery_task()
            self._recovery_stable_since_monotonic = None
            self._recovery_status = "waiting_feedback"
            return

        now = monotonic()
        if self._recovery_stable_since_monotonic is None:
            self._recovery_stable_since_monotonic = now
        base_delay = max(
            float(self.settings[SETTING_RECOVERY_STABILITY_TIME]),
            1.0,
        )
        delay = recovery_delay_seconds(base_delay, self._recovery_attempts)
        if delay is None:
            self._recovery_status = "exhausted"
            return
        remaining = max(
            delay - (now - self._recovery_stable_since_monotonic),
            0.0,
        )
        self._recovery_status = "waiting_stable"
        self._next_recovery_attempt = (
            dt_util.now() + timedelta(seconds=remaining)
        ).isoformat()
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = self.hass.async_create_task(
                self._async_recovery_wait(remaining)
            )

    async def _async_recovery_wait(self, delay: float) -> None:
        """Wait out the stability/backoff period and run one write probe."""
        current_task = asyncio.current_task()
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if (
                not self._write_blocked
                or not self.regulation_enabled
                or not self.automatic_recovery_enabled
                or not self.data_valid
                or self.result is None
                or not self.recovery_feedback_ready
                or not self.recovery_feedback_current
            ):
                return
            await self._async_attempt_recovery()
        except asyncio.CancelledError:
            raise
        finally:
            if self._recovery_task is current_task:
                self._recovery_task = None
            if self._write_blocked:
                self._schedule_recovery()

    async def _async_attempt_recovery(self) -> None:
        """Probe the unchanged inverter value and require fresh feedback."""
        self._recovery_attempts += 1
        self._recovery_status = "attempting"
        self._next_recovery_attempt = None
        self._notify()

        try:
            probe_at = await self._async_probe_control_write()
            feedback_timeout = max(
                _RECOVERY_FEEDBACK_TIMEOUT_SECONDS,
                float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]) * 3,
                self.source_polling_interval + 10.0,
            )
            deadline = monotonic() + feedback_timeout
            while monotonic() < deadline:
                if not self.data_valid or self.result is None:
                    raise HomeAssistantError(
                        "Eingangsdaten während des Schreibtests ungültig"
                    )
                if feedback_samples_are_fresh(
                    probe_at,
                    self._feedback_sample_times(),
                ):
                    break
                await asyncio.sleep(1)
            else:
                raise HomeAssistantError(
                    "Keine neuen Messrückmeldungen nach dem Schreibtest"
                )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning(
                "XT500 automatic recovery attempt %s/%s failed: %s",
                self._recovery_attempts,
                self.recovery_max_attempts,
                self._error_detail(err),
            )
            self._control_error_at = datetime.now(UTC)
            self.control_error_message = (
                "Automatische Wiederherstellung "
                f"{self._recovery_attempts}/{self.recovery_max_attempts} "
                f"fehlgeschlagen: {self._error_detail(err)}"
            )
            self._recovery_stable_since_monotonic = None
            self._recovery_status = (
                "exhausted"
                if self._recovery_attempts >= self.recovery_max_attempts
                else "waiting_feedback"
            )
            self._notify()
            return

        self._write_blocked = False
        self._control_error_at = None
        self.control_error_message = None
        self._recovery_stable_since_monotonic = None
        self._next_recovery_attempt = None
        self._recovery_status = "ready"
        self.last_recovery_success = dt_util.now().isoformat()
        self._data_valid_since_monotonic = (
            monotonic() - _STARTUP_STABILITY_SECONDS
        )
        self._notify()
        self.async_calculate()

    async def _async_probe_control_write(self) -> datetime:
        """Write the current inverter value unchanged as a harmless reachability probe."""
        inverter_entity = self.entry.data[CONF_INVERTER_SETPOINT_ENTITY]
        current = self._float_state(inverter_entity)
        if current is None:
            raise HomeAssistantError(
                f"Sollwert nicht lesbar: {inverter_entity}"
            )
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"value": current},
            blocking=True,
            target={"entity_id": inverter_entity},
        )
        probe_at = datetime.now(UTC)
        self._last_control_write_at = probe_at
        self.last_control_write = dt_util.now().isoformat()
        self._notify()
        return probe_at

    async def _async_apply_control_result(self, maximum_change: float) -> None:
        """Write charge limit, inverter ceiling, and grid setpoint."""
        if not self.control_ready or self.result is None:
            return

        charge_limit_entity = self.entry.data[CONF_MAX_CHARGE_SOC_ENTITY]
        inverter_entity = self.entry.data[CONF_INVERTER_SETPOINT_ENTITY]
        grid_entity = self.entry.data[CONF_GRID_SETPOINT_ENTITY]
        inverter_target = self._limited_entity_target(
            inverter_entity,
            self.result.recommended_inverter_setpoint,
            maximum_change,
        )
        grid_target = self._limited_entity_target(
            grid_entity,
            self.result.recommended_grid_setpoint,
            maximum_change,
        )

        if self.reserve_hold_active:
            inverter_target = min(inverter_target, self._quantized_entity_target(
                inverter_entity, self.result.recommended_inverter_setpoint))
            grid_target = min(grid_target, self._quantized_entity_target(
                grid_entity, self.result.recommended_grid_setpoint))

        setpoint_wrote = False
        wrote = False
        for entity_id, target, is_control_setpoint in (
            (charge_limit_entity, self.desired_charge_limit, False),
            (inverter_entity, inverter_target, True),
            (grid_entity, grid_target, True),
        ):
            if target is None:
                continue
            current = self._float_state(entity_id)
            state = self.hass.states.get(entity_id)
            if current is None or state is None:
                raise TransientCommunicationError(
                    f"Sollwert vorübergehend nicht lesbar: {entity_id}"
                )
            step = float(state.attributes.get("step", 1) or 1)
            if abs(target - current) < max(step / 2, 0.5):
                continue
            await self._async_set_number_resilient(entity_id, target)
            wrote = True
            setpoint_wrote = setpoint_wrote or is_control_setpoint

        self._last_control_apply_monotonic = monotonic()
        if setpoint_wrote:
            self._last_control_write_at = datetime.now(UTC)
        if wrote:
            self.last_control_write = dt_util.now().isoformat()
            self._notify()

    async def _async_set_number_resilient(
        self,
        entity_id: str,
        target: float,
    ) -> None:
        """Retry transient SunEnergyXT timeouts before latching a control error."""
        for attempt in range(1, _WRITE_MAX_ATTEMPTS + 1):
            try:
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"value": target},
                    blocking=True,
                    target={"entity_id": entity_id},
                )
            except TimeoutError as err:
                self.transient_write_timeouts += 1
                self.last_transient_write_error = (
                    f"{dt_util.now().isoformat()} · {entity_id} · "
                    f"Ziel {target:g} · Versuch {attempt}/{_WRITE_MAX_ATTEMPTS}"
                )
                delay = write_retry_delay_seconds(
                    float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]),
                    attempt,
                )
                if delay is None:
                    if self._float_state(entity_id) is None:
                        raise TransientCommunicationError(
                            f"Sollwert nach Zeitüberschreitungen nicht lesbar: "
                            f"{entity_id}"
                        ) from err
                    raise HomeAssistantError(
                        f"Zeitüberschreitung beim Schreiben von {target:g} "
                        f"auf {entity_id} nach {_WRITE_MAX_ATTEMPTS} Versuchen"
                    ) from err
                _LOGGER.info(
                    "Temporary XT500 write timeout for %s target %s "
                    "(attempt %s/%s); waiting %.1f seconds for readback",
                    entity_id,
                    target,
                    attempt,
                    _WRITE_MAX_ATTEMPTS,
                    delay,
                )
                if await self._async_wait_for_entity_target(
                    entity_id,
                    target,
                    delay,
                ):
                    self.last_transient_write_recovery = (
                        f"{dt_util.now().isoformat()} · {entity_id} · "
                        "Zielwert nach Timeout zurückgelesen"
                    )
                    self._notify()
                    return
                continue
            except HomeAssistantError as err:
                if self._float_state(entity_id) is None:
                    readback_wait = transient_readback_wait_seconds(
                        float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]),
                        self.source_polling_interval,
                    )
                    if await self._async_wait_for_entity_target(
                        entity_id,
                        target,
                        readback_wait,
                    ):
                        self.last_transient_write_recovery = (
                            f"{dt_util.now().isoformat()} · {entity_id} · "
                            "Zielwert nach vorübergehendem Dienstfehler zurückgelesen"
                        )
                        self._notify()
                        return
                if self._float_state(entity_id) is None:
                    raise TransientCommunicationError(
                        f"Sollwert vorübergehend nicht lesbar: {entity_id}"
                    ) from err
                raise

            if self._float_state(entity_id) is None:
                readback_wait = transient_readback_wait_seconds(
                    float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]),
                    self.source_polling_interval,
                )
                if await self._async_wait_for_entity_readable(
                    entity_id,
                    readback_wait,
                ):
                    self.last_transient_write_recovery = (
                        f"{dt_util.now().isoformat()} · {entity_id} · "
                        "Sollwert nach kurzer Aktualisierung wieder lesbar"
                    )
                    self._notify()
                    return
                raise TransientCommunicationError(
                    f"Sollwert nach dem Schreiben nicht lesbar: {entity_id}"
                )
            if attempt > 1:
                self.last_transient_write_recovery = (
                    f"{dt_util.now().isoformat()} · {entity_id} · "
                    f"Schreibversuch {attempt}/{_WRITE_MAX_ATTEMPTS} erfolgreich"
                )
                self._notify()
            return

    async def _async_wait_for_entity_target(
        self,
        entity_id: str,
        target: float,
        timeout: float,
    ) -> bool:
        """Wait briefly for coordinator readback after an ambiguous timeout."""
        deadline = monotonic() + max(timeout, 0.0)
        while True:
            if self._entity_target_matches(entity_id, target):
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(1.0, remaining))

    async def _async_wait_for_entity_readable(
        self,
        entity_id: str,
        timeout: float,
    ) -> bool:
        """Wait for a temporarily unavailable coordinator value to return."""
        deadline = monotonic() + max(timeout, 0.0)
        while True:
            if self._float_state(entity_id) is not None:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(1.0, remaining))

    def _entity_target_matches(self, entity_id: str, target: float) -> bool:
        """Return whether the entity readback already reflects the target."""
        current = self._float_state(entity_id)
        state = self.hass.states.get(entity_id)
        if current is None or state is None:
            return False
        step = float(state.attributes.get("step", 1) or 1)
        return abs(target - current) < max(step / 2, 0.5)

    def _limited_entity_target(
        self, entity_id: str, requested: float, maximum_change: float
    ) -> float:
        state = self.hass.states.get(entity_id)
        current = self._float_state(entity_id)
        if state is None or current is None:
            raise TransientCommunicationError(
                f"Sollwert vorübergehend nicht lesbar: {entity_id}"
            )
        low = float(state.attributes.get("min", requested))
        high = float(state.attributes.get("max", requested))
        step = max(float(state.attributes.get("step", 1) or 1), 1)
        return limit_setpoint_change(
            current, requested, low, high, step, maximum_change
        )

    def _quantized_entity_target(self, entity_id: str, requested: float) -> float:
        """Return the nearest supported value for one number entity."""
        state = self.hass.states.get(entity_id)
        if state is None:
            raise TransientCommunicationError(
                f"Sollwert vorübergehend nicht lesbar: {entity_id}"
            )
        return quantize_number_value(
            requested,
            low=float(state.attributes.get("min", requested)),
            high=float(state.attributes.get("max", requested)),
            step=float(state.attributes.get("step", 1) or 1),
        )

    @property
    def days_since_full(self) -> float | None:
        """Return elapsed days in the current full-charge cycle."""
        baseline = self._setting_datetime(
            SETTING_LAST_FULL
        ) or self._setting_datetime(SETTING_CYCLE_REFERENCE)
        if baseline is None:
            return None
        return round(max((dt_util.now() - baseline).total_seconds(), 0) / 86400, 1)

    async def async_start_manual_cycle(self) -> None:
        """Start a cycle charge immediately with the configured cycle mode."""
        if not self.regulation_enabled:
            raise HomeAssistantError(
                "Die Regelung muss vor dem Start der Zyklusladung aktiv sein."
            )
        self.settings[SETTING_MANUAL_ACTIVE] = False
        self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = False
        self.settings[SETTING_CYCLE_MANUAL_ACTIVE] = True
        self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_LAST_RESULT] = "idle"
        self._full_soc_latched = False
        await self._store.async_save(self.settings)
        self.async_calculate()

    async def async_reset_cycle(self) -> None:
        """Reset elapsed cycle days and stop any current cycle charge."""
        self.settings[SETTING_LAST_FULL] = None
        self.settings[SETTING_CYCLE_REFERENCE] = dt_util.now().isoformat()
        self.settings[SETTING_CYCLE_MANUAL_ACTIVE] = False
        self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = False
        self.settings[SETTING_FULL_CHARGE_CONFIRMATION_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_TAPER_STARTED] = None
        self.settings[SETTING_FULL_CHARGE_LAST_RESULT] = "idle"
        self._full_soc_latched = False
        await self._store.async_save(self.settings)
        self.async_calculate()

    async def async_set_system_discharge_limit(self, value: float) -> None:
        """Write the shared discharge limit through the original XT500 entity."""
        if self.discharge_override_active:
            await self._async_restore_discharge_override()
        entity_id = self.entry.data[CONF_MIN_DISCHARGE_SOC_ENTITY]
        await self._async_set_number_resilient(entity_id, value)
        self.async_calculate()

    async def async_set_device_soc_hysteresis(
        self,
        entity_key: str,
        setting_key: str,
        value: float,
    ) -> None:
        """Write an SI1/SA1 device hysteresis and keep the manager in sync."""
        entity_id = self.entry.data.get(entity_key)
        if not entity_id:
            raise HomeAssistantError(
                "Die geräteseitige SOC-Hysterese ist nicht eingerichtet."
            )
        target = self._quantized_entity_target(entity_id, value)
        await self._async_set_number_resilient(entity_id, target)
        self.settings[setting_key] = target
        await self._store.async_save(self.settings)
        self.async_calculate()

    async def async_release_discharge_once(self) -> None:
        """Temporarily release the device lock until the lower SOC is hit again."""
        if not self.regulation_enabled:
            raise HomeAssistantError(
                "Die Regelung muss für die temporäre Entladefreigabe aktiv sein."
            )
        if not self.data_valid:
            raise HomeAssistantError(
                "Die Eingangsdaten müssen für die temporäre Entladefreigabe gültig sein."
            )
        if self.settings[SETTING_RESERVE_ENABLED]:
            raise HomeAssistantError("Bei aktiver Reserve ist die einmalige Entladefreigabe gesperrt.")
        if self.discharge_override_active:
            raise HomeAssistantError(
                "Die temporäre Entladefreigabe ist bereits aktiv."
            )

        entity_id = self.entry.data[CONF_MIN_DISCHARGE_SOC_ENTITY]
        original_limit = self._float_state(entity_id)
        soc = self._float_state(self.entry.data[CONF_SOC_ENTITY])
        if original_limit is None or soc is None:
            raise HomeAssistantError(
                "SOC oder System-Entladegrenze ist derzeit nicht lesbar."
            )
        hysteresis = max(float(self.settings[SETTING_SOC_HYSTERESIS]), 0.0)
        if soc <= original_limit:
            raise HomeAssistantError(
                "Der Speicher steht bereits an der Entladegrenze und darf nicht weiter entladen werden."
            )
        if soc >= original_limit + hysteresis or not self.discharge_hold_active:
            raise HomeAssistantError(
                "Die Entladesperre ist derzeit nicht aktiv; eine Freigabe ist nicht erforderlich."
            )

        temporary_limit = self._quantized_entity_target(
            entity_id, original_limit - max(hysteresis, 1.0)
        )
        if temporary_limit >= original_limit:
            raise HomeAssistantError(
                "Die Geräte-Entladegrenze kann nicht sicher vorübergehend abgesenkt werden."
            )

        self.settings[SETTING_DISCHARGE_OVERRIDE_ACTIVE] = True
        self.settings[SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT] = original_limit
        self._discharge_override_session_active = True
        await self._store.async_save(self.settings)
        try:
            await self._async_set_discharge_limit_confirmed(
                entity_id, temporary_limit
            )
        except Exception:
            self._discharge_override_session_active = False
            self.settings[SETTING_DISCHARGE_OVERRIDE_ACTIVE] = False
            self.settings[SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT] = None
            await self._store.async_save(self.settings)
            if not self._entity_target_matches(entity_id, original_limit):
                try:
                    await self._async_set_discharge_limit_confirmed(
                        entity_id, original_limit
                    )
                except Exception:
                    _LOGGER.exception(
                        "Could not restore XT500 discharge limit after failed release"
                    )
            self._low_soc_hold = None
            self.async_calculate()
            raise

        self._low_soc_hold = False
        self.async_calculate()

    @callback
    def _schedule_discharge_override_restore(self) -> None:
        """Restore the normal device limit after the one-shot release."""
        if (
            not self.discharge_override_active
            or (
                self._discharge_override_restore_task is not None
                and not self._discharge_override_restore_task.done()
            )
        ):
            return
        self._discharge_override_restore_task = self.hass.async_create_task(
            self._async_restore_discharge_override(raise_on_error=False)
        )

    async def _async_restore_discharge_override(
        self, *, raise_on_error: bool = True
    ) -> None:
        """Restore and confirm the saved discharge limit before clearing state."""
        current_task = asyncio.current_task()
        restored = False
        try:
            original = self.settings.get(
                SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT
            )
            if not self.discharge_override_active or original is None:
                return
            entity_id = self.entry.data[CONF_MIN_DISCHARGE_SOC_ENTITY]
            await self._async_set_discharge_limit_confirmed(
                entity_id, float(original)
            )
            self.settings[SETTING_MIN_SOC] = float(original)
            self.settings[SETTING_DISCHARGE_OVERRIDE_ACTIVE] = False
            self.settings[SETTING_DISCHARGE_OVERRIDE_ORIGINAL_LIMIT] = None
            self._discharge_override_session_active = False
            self._low_soc_hold = None
            await self._store.async_save(self.settings)
            restored = True
        except Exception as err:
            self._discharge_override_session_active = False
            self._low_soc_hold = True
            _LOGGER.error(
                "Could not restore XT500 discharge limit after temporary release: %s",
                self._error_detail(err),
            )
            if raise_on_error:
                raise
        finally:
            if self._discharge_override_restore_task is current_task:
                self._discharge_override_restore_task = None
            if restored:
                self.async_calculate()
            else:
                self._notify()

    async def _async_set_discharge_limit_confirmed(
        self, entity_id: str, target: float
    ) -> None:
        """Write the safety-relevant discharge limit and require readback."""
        await self._async_set_number_resilient(entity_id, target)
        if self._entity_target_matches(entity_id, target):
            return
        timeout = max(
            float(self.settings[SETTING_FEEDBACK_SETTLE_TIME]) * 2,
            5.0,
        )
        if await self._async_wait_for_entity_target(entity_id, target, timeout):
            return
        raise HomeAssistantError(
            f"System-Entladegrenze {target:g} wurde nicht vom XT500 bestätigt."
        )

    async def async_set_system_charge_limit(self, value: float) -> None:
        """Set the shared normal charge limit through the original XT500 entity."""
        entity_id = self.entry.data[CONF_MAX_CHARGE_SOC_ENTITY]
        target = self._quantized_entity_target(entity_id, value)
        previous = float(self.settings[SETTING_NORMAL_CHARGE_LIMIT])
        self.settings[SETTING_NORMAL_CHARGE_LIMIT] = target
        await self._store.async_save(self.settings)
        if self.charge_request_active:
            self.async_calculate()
            return
        self._normal_charge_limit_write_pending = target
        try:
            await self._async_set_number_resilient(entity_id, target)
        except Exception:
            self._normal_charge_limit_write_pending = None
            self.settings[SETTING_NORMAL_CHARGE_LIMIT] = previous
            await self._store.async_save(self.settings)
            self.async_calculate()
            raise
        self.async_calculate()

    @callback
    def async_set_setting(self, key: str, value: Any) -> None:
        """Persist an integration-owned setting and recalculate."""
        if key in (SETTING_RESERVE_ENABLED, SETTING_RESERVE_SOC):
            if key == SETTING_RESERVE_ENABLED and value and self.discharge_override_active:
                raise HomeAssistantError("Zuerst die einmalige Entladefreigabe beenden.")
            if key == SETTING_RESERVE_SOC:
                if not math.isfinite(float(value)) or not 1 <= float(value) <= 99:
                    raise HomeAssistantError("Die Reserve muss zwischen 1 und 99 % liegen.")
            self._reserve_hold = None
        self.settings[key] = value
        if (
            key == SETTING_AUTO_ENABLED
            and bool(value)
            and self._setting_datetime(SETTING_LAST_FULL) is None
            and self._setting_datetime(SETTING_CYCLE_REFERENCE) is None
        ):
            self.settings[SETTING_CYCLE_REFERENCE] = dt_util.now().isoformat()
        if key == SETTING_AUTO_ENABLED:
            if bool(value):
                if self._automatic_cycle_should_start_now():
                    self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = True
            else:
                self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = False
        elif key == SETTING_CYCLE_CHECK_TIME:
            self._schedule_cycle_check()
            if self._automatic_cycle_should_start_now():
                self.settings[SETTING_CYCLE_AUTOMATIC_ACTIVE] = True
        elif key == SETTING_TARIFF_REQUEST_DURATION and self.tariff_request_active:
            self.async_set_tariff_active(True)
            return
        self._store.async_delay_save(lambda: self.settings, 1)
        if key == SETTING_AUTOMATIC_RECOVERY_ENABLED:
            self._cancel_recovery_task()
            self._recovery_stable_since_monotonic = None
            self._next_recovery_attempt = None
            if self._write_blocked:
                if bool(value):
                    self._recovery_attempts = 0
                    self._control_error_at = datetime.now(UTC)
                    self._recovery_status = "waiting_feedback"
                else:
                    self._recovery_status = "manual_required"
        elif key == SETTING_RECOVERY_STABILITY_TIME and self._write_blocked:
            self._cancel_recovery_task()
            self._recovery_stable_since_monotonic = None
        self.async_calculate()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                # Entity publication must not turn a successful device write
                # into a production-control failure or skip other entities.
                _LOGGER.exception("XT500 entity update failed")
