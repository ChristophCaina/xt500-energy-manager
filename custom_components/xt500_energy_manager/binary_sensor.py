"""Binary sensor platform for XT500 Energy Manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import XT500ConfigEntry
from .entity import XT500Entity
from .runtime import XT500Runtime


@dataclass(frozen=True, kw_only=True)
class XT500BinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[XT500Runtime], bool]


BINARY_SENSORS = (
    XT500BinaryDescription(key="data_valid", translation_key="data_valid", icon="mdi:database-check", value_fn=lambda r: r.data_valid),
    XT500BinaryDescription(key="cycle_due", translation_key="cycle_due", icon="mdi:calendar-alert", value_fn=lambda r: r.cycle_due),
    XT500BinaryDescription(key="cycle_charge_active", translation_key="cycle_charge_active", icon="mdi:battery-sync", value_fn=lambda r: r.cycle_charge_active),
    XT500BinaryDescription(key="charge_request", translation_key="charge_request", icon="mdi:battery-arrow-up", value_fn=lambda r: r.charge_request_active),
    XT500BinaryDescription(key="tariff_request", translation_key="tariff_request", icon="mdi:currency-eur", value_fn=lambda r: r.tariff_request_active),
    XT500BinaryDescription(key="control_ready", translation_key="control_ready", icon="mdi:shield-check", value_fn=lambda r: r.control_operational),
    XT500BinaryDescription(
        key="write_ready",
        translation_key="write_ready",
        icon="mdi:database-arrow-right-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.control_ready,
    ),
    XT500BinaryDescription(key="reserve_hold", translation_key="reserve_hold", icon="mdi:battery-lock", value_fn=lambda r: r.reserve_hold_active),
    XT500BinaryDescription(key="discharge_hold", translation_key="discharge_hold", icon="mdi:battery-lock", value_fn=lambda r: r.discharge_hold_active),
    XT500BinaryDescription(key="discharge_override_active", translation_key="discharge_override_active", icon="mdi:battery-unlock", value_fn=lambda r: r.discharge_override_active),
    XT500BinaryDescription(key="pv_release_active", translation_key="pv_release_active", icon="mdi:solar-power", value_fn=lambda r: r.pv_release_active),
    XT500BinaryDescription(key="ac_pv_release_active", translation_key="ac_pv_release_active", icon="mdi:transmission-tower-export", value_fn=lambda r: r.ac_pv_release_active),
    XT500BinaryDescription(key="ac_pv_input_valid", translation_key="ac_pv_input_valid", icon="mdi:solar-power-variant", value_fn=lambda r: r.ac_pv_input_valid),
)


class XT500BinarySensor(XT500Entity, BinarySensorEntity):
    def __init__(self, runtime: XT500Runtime, description: XT500BinaryDescription) -> None:
        super().__init__(runtime, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.runtime)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = dict(super().extra_state_attributes)
        if self.key == "data_valid":
            attrs["invalid_entities"] = self.runtime.invalid_entities
            attrs["current_errors"] = self.runtime.invalid_inputs
            attrs["last_errors"] = self.runtime.last_invalid_inputs
            attrs["last_error_at"] = self.runtime.last_invalid_at
            attrs["last_recovered_at"] = self.runtime.last_inputs_recovered_at
        elif self.key == "ac_pv_input_valid":
            attrs["configured"] = bool(
                self.runtime.entry.data.get("ac_pv_power_entity")
            )
            attrs["issue"] = self.runtime.ac_pv_input_issue
        elif self.key == "reserve_hold":
            attrs["reserve"] = self.runtime.settings["reserve_soc"]
            attrs["wiederfreigabe"] = self.runtime.reserve_release_soc
            attrs["regelung_verfuegbar"] = self.runtime.control_operational
        elif self.key in ("discharge_hold", "discharge_override_active"):
            attrs["entladegrenze"] = self.runtime.settings["minimum_soc"]
            attrs["regulaere_wiederfreigabe"] = self.runtime.discharge_release_soc
        return attrs


async def async_setup_entry(_hass: HomeAssistant, entry: XT500ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(XT500BinarySensor(entry.runtime_data, description) for description in BINARY_SENSORS)
