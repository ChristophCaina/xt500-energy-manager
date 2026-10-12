"""Unit tests for the Home Assistant independent XT500 production controller."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace, MethodType
import unittest
from unittest.mock import Mock, AsyncMock

ROOT = Path(__file__).parents[1]
PACKAGE = "custom_components.xt500_energy_manager"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "custom_components" / "xt500_energy_manager")]
sys.modules[PACKAGE] = package
_load_module(f"{PACKAGE}.const", Path(package.__path__[0]) / "const.py")
controller = _load_module(f"{PACKAGE}.controller", Path(package.__path__[0]) / "controller.py")


class ControllerTest(unittest.TestCase):
    def input(self, **changes):
        values = {
            "soc": 50,
            "pv_power": 900,
            "grid_power": 100,
            "grid_port_power": 600,
            "load_port_power": 300,
            "current_grid_setpoint": 0,
            "current_inverter_setpoint": 500,
        }
        values.update(changes)
        return controller.ControlInput(**values)

    def test_controller_statuses_are_supported_by_the_ha_sensor(self):
        sensor_tree = ast.parse(
            (ROOT / PACKAGE.replace(".", "/") / "sensor.py").read_text()
        )
        status_options = next(
            ast.literal_eval(node.value)
            for node in sensor_tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "STATUS_OPTIONS"
                    for target in node.targets)
        )
        scenarios = [
            (self.input(soc=100), controller.ControlSettings(
                full_battery_pv_export=True, full_battery_pv_hold=True)),
            (self.input(soc=10), controller.ControlSettings()),
        ]
        for mode in ("normal", "pv_surplus"):
            scenarios.append((self.input(), controller.ControlSettings(base_mode=mode)))
        for source in ("manual", "cycle_manual", "cycle_automatic", "tariff"):
            for mode in ("grid_charge", "pv_surplus", "pv_priority", "pv_and_grid"):
                if source == "tariff" and mode != "grid_charge":
                    continue
                scenarios.append((self.input(), controller.ControlSettings(
                    charge_active=True, charge_source=source, charge_mode=mode)))
        for data, settings in scenarios:
            result = controller.calculate_control(data, settings)
            with self.subTest(status=result.status):
                self.assertIn(result.status, status_options)

    def test_entity_listener_failure_does_not_interrupt_control_notifications(self):
        runtime_tree = ast.parse(
            (ROOT / PACKAGE.replace(".", "/") / "runtime.py").read_text()
        )
        runtime_class = next(node for node in runtime_tree.body
                             if isinstance(node, ast.ClassDef)
                             and node.name == "XT500Runtime")
        notify = next(node for node in runtime_class.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_notify")
        notify.decorator_list = []
        logger = Mock()
        namespace = {"_LOGGER": logger}
        exec(compile(ast.Module(body=[notify], type_ignores=[]), "runtime.py", "exec"),
             namespace)
        failing_listener = Mock(side_effect=ValueError("invalid enum state"))
        healthy_listener = Mock()
        runtime = SimpleNamespace(
            _listeners=[failing_listener, healthy_listener],
            control_ready=True, control_error_message=None,
        )
        namespace["_notify"](runtime)
        failing_listener.assert_called_once()
        healthy_listener.assert_called_once()
        logger.exception.assert_called_once()
        self.assertTrue(runtime.control_ready)
        self.assertIsNone(runtime.control_error_message)

    def test_full_battery_pv_hold_releases_on_charge_or_below_band(self):
        decide = controller.update_full_battery_pv_hold
        self.assertFalse(decide(current_hold=False, soc=99, charge_limit=100,
                                enabled=True, charge_active=False))
        self.assertTrue(decide(current_hold=False, soc=100, charge_limit=100,
                               enabled=True, charge_active=False))
        self.assertTrue(decide(current_hold=True, soc=99.5, charge_limit=100,
                               enabled=True, charge_active=False))
        self.assertFalse(decide(current_hold=True, soc=98.9, charge_limit=100,
                                enabled=True, charge_active=False))
        self.assertFalse(decide(current_hold=True, soc=100, charge_limit=100,
                                enabled=False, charge_active=False))
        self.assertFalse(decide(current_hold=True, soc=100, charge_limit=100,
                                enabled=True, charge_active=True))
        self.assertTrue(decide(current_hold=False, soc=80, charge_limit=80,
                               enabled=True, charge_active=False))

    def test_full_battery_pv_export_opens_only_when_enabled_and_held(self):
        data = self.input(soc=100, pv_power=1500, grid_power=0,
                          grid_port_power=400, load_port_power=200,
                          current_grid_setpoint=400,
                          current_inverter_setpoint=600,
                          battery_charge_power=0, battery_discharge_power=0)
        normal = controller.calculate_control(data, controller.ControlSettings(
            base_mode="pv_surplus", grid_limit=800, inverter_limit=2400,
            full_battery_pv_hold=True, pv_surplus_charge_reserve=0,
        ))
        bypass = controller.calculate_control(data, controller.ControlSettings(
            base_mode="pv_surplus", grid_limit=800, inverter_limit=2400,
            full_battery_pv_export=True, full_battery_pv_hold=True,
            pv_surplus_charge_reserve=0,
        ))
        self.assertFalse(normal.full_battery_pv_bypass_active)
        self.assertEqual(normal.recommended_grid_setpoint, 400)
        self.assertTrue(bypass.full_battery_pv_bypass_active)
        self.assertEqual(bypass.recommended_grid_setpoint, 0)
        self.assertEqual(bypass.recommended_inverter_setpoint, 1400)
        self.assertEqual(bypass.status, "full_battery_pv_bypass")

    def test_full_battery_pv_export_needs_dc_pv_and_no_charge_request(self):
        data = self.input(soc=100, pv_power=900)
        base = dict(full_battery_pv_export=True, full_battery_pv_hold=True)
        for settings in (
            controller.ControlSettings(**base, charge_active=True),
            controller.ControlSettings(**base, coupling_mode="ac"),
            controller.ControlSettings(**base, pv_release_allowed=False),
        ):
            self.assertFalse(controller.calculate_control(
                data, settings).full_battery_pv_bypass_active)
        self.assertFalse(controller.calculate_control(
            self.input(soc=100, pv_power=0),
            controller.ControlSettings(**base),
        ).full_battery_pv_bypass_active)

    def test_full_battery_bypass_reduces_measured_battery_discharge(self):
        result = controller.calculate_control(
            self.input(soc=100, pv_power=1000, grid_power=300,
                       grid_port_power=700, load_port_power=100,
                       current_inverter_setpoint=1000,
                       battery_discharge_power=100),
            controller.ControlSettings(full_battery_pv_export=True,
                                       full_battery_pv_hold=True,
                                       full_battery_pv_bypass_active=True,
                                       grid_limit=800, inverter_limit=2400),
        )
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 900)

    def test_full_battery_bypass_preserves_base_mode_when_pv_cannot_supply_load(self):
        # Reproduce the live test: 369 W DC PV, 313 W AC output and
        # 183.5 W public-grid import despite the reached device charge limit.
        data = self.input(soc=72, pv_power=369, grid_power=-183.5,
                          grid_port_power=313, load_port_power=0,
                          current_grid_setpoint=0, current_inverter_setpoint=1291,
                          battery_charge_power=10, battery_discharge_power=0)
        for mode in ("normal", "pv_surplus"):
            settings = dict(base_mode=mode, grid_limit=800,
                            full_battery_pv_hold=True)
            normal = controller.calculate_control(
                data, controller.ControlSettings(**settings))
            enabled = controller.calculate_control(
                data, controller.ControlSettings(**settings, full_battery_pv_export=True))
            with self.subTest(mode=mode):
                self.assertEqual(enabled, normal)
                self.assertFalse(enabled.full_battery_pv_bypass_active)
                if mode == "normal":
                    self.assertGreater(enabled.recommended_grid_setpoint, 0)

    def test_full_battery_bypass_exits_when_actual_pv_output_cannot_cover_load(self):
        # DC input alone appears sufficient, but conversion/device losses
        # leave an actual AC shortfall. The meter must override that estimate.
        result = controller.calculate_control(
            self.input(soc=100, pv_power=510, grid_power=-70,
                       grid_port_power=430, load_port_power=0,
                       current_grid_setpoint=0, current_inverter_setpoint=1300,
                       battery_charge_power=0, battery_discharge_power=0),
            controller.ControlSettings(full_battery_pv_export=True,
                                       full_battery_pv_hold=True, grid_limit=800),
        )
        self.assertFalse(result.full_battery_pv_bypass_active)
        self.assertEqual(result.status, "normal")
        self.assertGreater(result.recommended_grid_setpoint, 0)

    def test_full_battery_bypass_does_not_reenter_while_battery_supplies_load(self):
        # After leaving bypass, restored battery support hides the grid
        # shortfall. It must not cause immediate re-entry and repeated import.
        result = controller.calculate_control(
            self.input(soc=100, pv_power=505, grid_power=0,
                       grid_port_power=500, load_port_power=0,
                       current_grid_setpoint=500, current_inverter_setpoint=500,
                       battery_charge_power=0, battery_discharge_power=60),
            controller.ControlSettings(full_battery_pv_export=True,
                                       full_battery_pv_hold=True, grid_limit=800),
        )
        self.assertFalse(result.full_battery_pv_bypass_active)
        self.assertEqual(result.status, "normal")

    def test_full_battery_bypass_opens_headroom_for_curtailed_dc_pv(self):
        result = controller.calculate_control(
            self.input(soc=100, pv_power=500, grid_power=0,
                       grid_port_power=200, load_port_power=100),
            controller.ControlSettings(full_battery_pv_export=True,
                                       full_battery_pv_hold=True,
                                       grid_limit=800, inverter_limit=2400),
        )
        self.assertTrue(result.full_battery_pv_bypass_active)
        # IS is a ceiling, not an output request. Limiting it to measured,
        # potentially curtailed PV would prevent discovering more PV power.
        self.assertEqual(result.recommended_inverter_setpoint, 1100)

    def test_bypass_does_not_flap_when_normal_battery_export_hides_shortfall(self):
        settings = controller.ControlSettings(
            full_battery_pv_export=True, full_battery_pv_hold=True,
            grid_limit=800, inverter_limit=2400, coupling_mode="dc")
        state = controller.FullBatteryBypassState()
        for now in range(0, 100, 5):
            normal = now % 10 == 0
            data = self.input(
                soc=75, pv_power=500, load_port_power=0,
                grid_power=20 if normal else -45,
                grid_port_power=470 if normal else 405,
                current_grid_setpoint=470 if normal else 0,
                current_inverter_setpoint=470 if normal else 1250,
                battery_charge_power=0 if normal else 10,
                battery_discharge_power=45 if normal else 0)
            result, state = controller.calculate_control_with_bypass_state(
                data, settings, state=state, now=now)
            self.assertEqual(result.status, "normal")
            self.assertIsNone(state.eligible_since)

    def test_bypass_requires_continuous_entry_and_retains_wider_exit_band(self):
        settings = controller.ControlSettings(
            full_battery_pv_export=True, full_battery_pv_hold=True, grid_limit=800)
        data = self.input(soc=75, pv_power=700, grid_port_power=450,
                          load_port_power=0, grid_power=0,
                          battery_charge_power=10, battery_discharge_power=0)
        state = controller.FullBatteryBypassState()
        for now in (0, 5, 15, 29):
            result, state = controller.calculate_control_with_bypass_state(
                data, settings, state=state, now=now)
            self.assertFalse(result.full_battery_pv_bypass_active)
        # One staggered/unstable measurement resets the complete entry window.
        unstable = self.input(soc=75, pv_power=700, grid_port_power=450,
                              load_port_power=0, grid_power=-15,
                              battery_discharge_power=0)
        result, state = controller.calculate_control_with_bypass_state(
            unstable, settings, state=state, now=29.5)
        self.assertIsNone(state.eligible_since)
        for now in (30, 40, 59):
            result, state = controller.calculate_control_with_bypass_state(
                data, settings, state=state, now=now)
            self.assertFalse(result.full_battery_pv_bypass_active)
        result, state = controller.calculate_control_with_bypass_state(
            data, settings, state=state, now=60)
        self.assertTrue(result.full_battery_pv_bypass_active)
        # Same 15 W transient does not end established bypass (exit band 30 W).
        result, state = controller.calculate_control_with_bypass_state(
            unstable, settings, state=state, now=65)
        self.assertTrue(result.full_battery_pv_bypass_active)
        deficit = self.input(soc=75, pv_power=500, grid_port_power=405,
                             load_port_power=0, grid_power=-45,
                             battery_discharge_power=0)
        result, state = controller.calculate_control_with_bypass_state(
            deficit, settings, state=state, now=66)
        self.assertFalse(result.full_battery_pv_bypass_active)
        self.assertGreater(result.recommended_grid_setpoint, 0)
        result, state = controller.calculate_control_with_bypass_state(
            data, settings, state=state, now=67)
        self.assertFalse(result.full_battery_pv_bypass_active)
        self.assertEqual(state.eligible_since, 67)

    def test_active_bypass_exits_immediately_for_charge_disable_soc_and_ac(self):
        data = self.input(soc=75, pv_power=700, grid_port_power=450,
                          load_port_power=0, grid_power=0,
                          battery_discharge_power=0)
        defaults = dict(full_battery_pv_export=True, full_battery_pv_hold=True)
        for override in (dict(charge_active=True),
                         dict(full_battery_pv_export=False),
                         dict(full_battery_pv_hold=False),
                         dict(coupling_mode="ac"), dict(pv_release_allowed=False)):
            settings = controller.ControlSettings(**(defaults | override))
            result, state = controller.calculate_control_with_bypass_state(
                data, settings, state=controller.FullBatteryBypassState(active=True),
                now=1)
            self.assertFalse(result.full_battery_pv_bypass_active)
            self.assertEqual(state, controller.FullBatteryBypassState())

    def test_full_charge_waits_for_hold_and_continuous_taper(self):
        start = datetime(2026, 8, 21, 12, tzinfo=UTC)
        first = controller.update_full_charge_confirmation(
            now=start, soc=100, target_soc=100, battery_charge_power=200,
            started_at=None, taper_started_at=None, minimum_hold_minutes=10,
            taper_power_w=30, taper_minutes=5, timeout_minutes=60,
        )
        self.assertEqual(first.state, "holding")
        tapered = controller.update_full_charge_confirmation(
            now=start + timedelta(minutes=8), soc=100, target_soc=100,
            battery_charge_power=20, started_at=first.started_at,
            taper_started_at=first.taper_started_at, minimum_hold_minutes=10,
            taper_power_w=30, taper_minutes=5, timeout_minutes=60,
        )
        confirmed = controller.update_full_charge_confirmation(
            now=start + timedelta(minutes=13), soc=100, target_soc=100,
            battery_charge_power=10, started_at=tapered.started_at,
            taper_started_at=tapered.taper_started_at, minimum_hold_minutes=10,
            taper_power_w=30, taper_minutes=5, timeout_minutes=60,
        )
        self.assertTrue(confirmed.complete)
        self.assertEqual(confirmed.state, "confirmed")

    def test_full_charge_taper_must_be_continuous_and_measured(self):
        start = datetime(2026, 8, 21, 12, tzinfo=UTC)
        decision = controller.update_full_charge_confirmation(
            now=start + timedelta(minutes=12), soc=100, target_soc=100,
            battery_charge_power=None, started_at=start,
            taper_started_at=start + timedelta(minutes=6), minimum_hold_minutes=10,
            taper_power_w=30, taper_minutes=5, timeout_minutes=60,
        )
        self.assertEqual(decision.state, "waiting_taper")
        self.assertIsNone(decision.taper_started_at)
        self.assertFalse(decision.complete)

    def test_full_charge_confirmation_times_out_safely(self):
        start = datetime(2026, 8, 21, 12, tzinfo=UTC)
        decision = controller.update_full_charge_confirmation(
            now=start + timedelta(minutes=60), soc=100, target_soc=100,
            battery_charge_power=500, started_at=start, taper_started_at=None,
            minimum_hold_minutes=10, taper_power_w=30, taper_minutes=5,
            timeout_minutes=60,
        )
        self.assertTrue(decision.complete)
        self.assertTrue(decision.timed_out)
        self.assertEqual(decision.state, "timeout")

    def test_full_charge_confirmation_resets_below_target(self):
        start = datetime(2026, 8, 21, 12, tzinfo=UTC)
        decision = controller.update_full_charge_confirmation(
            now=start + timedelta(minutes=3), soc=99, target_soc=100,
            battery_charge_power=0, started_at=start, taper_started_at=start,
            minimum_hold_minutes=10, taper_power_w=30, taper_minutes=5,
            timeout_minutes=60,
        )
        self.assertEqual(decision.state, "idle")
        self.assertIsNone(decision.started_at)

    def test_ac_pv_sign_is_normalized_without_turning_consumption_into_pv(self):
        self.assertEqual(
            controller.normalize_pv_production(-600, production_negative=True),
            600,
        )
        self.assertEqual(
            controller.normalize_pv_production(600, production_negative=False),
            600,
        )
        self.assertEqual(
            controller.normalize_pv_production(40, production_negative=True),
            0,
        )

    def test_pv_priority_never_requests_grid_charge(self):
        result = controller.calculate_control(
            self.input(),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="pv_priority",
                meter_export_positive=False,
            ),
        )
        self.assertGreaterEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.active_mode, "pv_priority")

    def test_grid_charge_requests_configured_negative_setpoint(self):
        result = controller.calculate_control(
            self.input(),
            controller.ControlSettings(
                charge_active=True,
                charge_source="automatic",
                charge_mode="grid_charge",
                charge_power=1200,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -1200)
        self.assertIn("automatic", result.status)

    def test_grid_charge_is_not_limited_by_positive_house_output_limit(self):
        result = controller.calculate_control(
            self.input(),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="grid_charge",
                charge_power=2400,
                grid_limit=800,
                inverter_limit=2400,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -2400)
        self.assertEqual(result.active_mode, "grid_charge")

    def test_pv_and_grid_charge_uses_independent_charge_power_limit(self):
        result = controller.calculate_control(
            self.input(),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="pv_and_grid",
                charge_power=1800,
                grid_limit=800,
                inverter_limit=2400,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -1800)

    def test_pv_and_grid_subtracts_pv_available_for_battery(self):
        result = controller.calculate_control(
            self.input(
                pv_power=1400,
                grid_power=0,
                grid_port_power=300,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="pv_and_grid",
                charge_power=1200,
                grid_limit=800,
                inverter_limit=2400,
                target_grid_power=0,
                meter_export_positive=False,
            ),
        )
        # 300 W PV supplies the house, 1100 W PV remains for charging, and
        # the grid provides only the missing 100 W of the 1200 W target.
        self.assertEqual(result.recommended_inverter_setpoint, 300)
        self.assertEqual(result.recommended_grid_setpoint, -100)

    def test_pv_and_grid_needs_no_grid_when_pv_covers_charge_target(self):
        result = controller.calculate_control(
            self.input(
                pv_power=1600,
                grid_power=0,
                grid_port_power=300,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="automatic",
                charge_mode="pv_and_grid",
                charge_power=1200,
                target_grid_power=0,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 0)

    def test_grid_charge_keeps_fixed_grid_request_with_available_pv(self):
        result = controller.calculate_control(
            self.input(
                pv_power=1600,
                grid_power=0,
                grid_port_power=300,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="grid_charge",
                charge_power=1200,
                grid_limit=800,
                inverter_limit=2400,
                target_grid_power=0,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -1200)

    def test_pv_surplus_cannot_exceed_available_pv(self):
        result = controller.calculate_control(
            self.input(pv_power=740, grid_power=-50, grid_port_power=500),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="pv_surplus",
                meter_export_positive=False,
            ),
        )
        self.assertLessEqual(result.recommended_grid_setpoint, 740)
        self.assertEqual(
            result.recommended_grid_setpoint,
            result.recommended_inverter_setpoint,
        )

    def test_ac_only_pv_surplus_absorbs_export_without_grid_import(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
                current_grid_setpoint=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="pv_surplus",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -600)
        self.assertEqual(result.recommended_inverter_setpoint, 0)
        self.assertEqual(result.available_ac_surplus, 600)
        self.assertEqual(result.active_coupling_mode, "ac")
        self.assertEqual(result.active_energy_source, "pv")

    def test_automatic_cycle_pv_surplus_uses_reconstructed_ac_export(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=0,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
                current_grid_setpoint=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="cycle_automatic",
                charge_mode="pv_surplus",
                coupling_mode="ac",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -600)
        self.assertEqual(result.available_ac_surplus, 600)
        self.assertEqual(result.active_coupling_mode, "ac")
        self.assertEqual(result.status, "cycle_automatic_pv_surplus")
        self.assertEqual(result.active_energy_source, "pv")

    def test_ac_only_pv_priority_absorbs_only_available_surplus(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
                current_grid_setpoint=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="cycle_automatic",
                charge_mode="pv_priority",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -600)
        self.assertEqual(result.mode_state, "charging")

    def test_ac_only_pv_and_grid_uses_pv_towards_total_charge_target(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="pv_and_grid",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -1200)
        self.assertEqual(result.effective_public_grid_target, -600)
        self.assertEqual(result.active_energy_source, "pv_and_grid")

    def test_ac_only_grid_charge_preserves_configured_public_grid_share(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="grid_charge",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -1800)
        self.assertEqual(result.effective_public_grid_target, -1200)

    def test_grid_charge_respects_real_negative_device_range(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=1000,
                grid_power=1000,
                grid_port_power=0,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="grid_charge",
                charge_power=2400,
                grid_charge_limit=2400,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -2400)
        self.assertEqual(result.effective_public_grid_target, -1400)

    def test_mixed_pv_and_grid_counts_dc_and_ac_without_double_subtraction(self):
        result = controller.calculate_control(
            self.input(
                pv_power=1000,
                ac_pv_power=500,
                grid_power=300,
                grid_port_power=0,
                load_port_power=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="pv_and_grid",
                charge_power=1200,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -200)
        self.assertEqual(result.active_coupling_mode, "hybrid")
        self.assertEqual(result.active_energy_source, "pv_and_grid")

    def test_waiting_pv_mode_stays_selected_and_active(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=0,
                grid_power=0,
                grid_port_power=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="cycle_automatic",
                charge_mode="pv_priority",
                coupling_mode="automatic",
            ),
        )
        self.assertEqual(result.selected_mode, "pv_priority")
        self.assertEqual(result.active_mode, "pv_priority")
        self.assertEqual(result.mode_state, "waiting_for_pv")
        self.assertEqual(result.selected_coupling_mode, "automatic")
        self.assertEqual(result.active_coupling_mode, "none")

    def test_ac_and_dc_release_gates_do_not_unlock_each_other(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="pv_surplus",
                pv_release_allowed=False,
                ac_pv_release_allowed=True,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -600)
        self.assertEqual(result.recommended_inverter_setpoint, 0)
        self.assertEqual(result.active_coupling_mode, "ac")

    def test_normal_mode_waits_for_ac_release_before_absorbing_small_surplus(self):
        blocked = controller.calculate_control(
            self.input(
                pv_power=0,
                grid_power=40,
                grid_port_power=0,
                load_port_power=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=False,
                ac_pv_release_allowed=False,
                meter_export_positive=True,
            ),
        )
        released = controller.calculate_control(
            self.input(
                pv_power=0,
                grid_power=100,
                grid_port_power=0,
                load_port_power=0,
                current_inverter_setpoint=0,
            ),
            controller.ControlSettings(
                charge_active=False,
                ac_pv_release_allowed=True,
                meter_export_positive=True,
            ),
        )
        self.assertEqual(blocked.recommended_grid_setpoint, 0)
        self.assertEqual(released.recommended_grid_setpoint, -100)

    def test_dc_only_coupling_does_not_use_reconstructed_ac_surplus(self):
        result = controller.calculate_control(
            self.input(
                pv_power=0,
                ac_pv_power=600,
                grid_power=600,
                grid_port_power=0,
                load_port_power=0,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="pv_surplus",
                coupling_mode="dc",
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.available_ac_surplus, 0)
        self.assertEqual(result.mode_state, "waiting_for_pv")

    def test_legacy_hybrid_selection_is_normalized_to_both_pv_sources(self):
        result = controller.calculate_control(
            self.input(
                pv_power=300,
                ac_pv_power=600,
                grid_power=200,
                grid_port_power=0,
                load_port_power=0,
            ),
            controller.ControlSettings(
                coupling_mode="hybrid",
                meter_export_positive=True,
            ),
        )
        self.assertEqual(result.selected_coupling_mode, "automatic")
        self.assertEqual(result.dc_pv_power, 300)
        self.assertEqual(result.available_ac_surplus, 200)

    def test_target_soc_ends_charge_recommendation(self):
        result = controller.calculate_control(
            self.input(soc=100),
            controller.ControlSettings(
                charge_active=True,
                charge_mode="grid_charge",
                target_soc=100,
                meter_export_positive=False,
            ),
        )
        self.assertTrue(result.target_reached)
        self.assertEqual(result.status, "target_reached")
        self.assertGreaterEqual(result.recommended_grid_setpoint, 0)

    def test_normal_operation_does_not_treat_manual_target_as_reached(self):
        result = controller.calculate_control(
            self.input(soc=100),
            controller.ControlSettings(
                charge_active=False,
                target_soc=50,
                meter_export_positive=False,
            ),
        )
        self.assertFalse(result.target_reached)
        self.assertEqual(result.status, "normal")

    def test_normal_operation_compensates_sustained_grid_import(self):
        result = controller.calculate_control(
            self.input(
                grid_power=79,
                grid_port_power=173,
                load_port_power=0,
                current_grid_setpoint=250,
                current_inverter_setpoint=251,
            ),
            controller.ControlSettings(
                charge_active=False,
                target_grid_power=-10,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.normalized_grid_power, -79)
        self.assertEqual(result.recommended_grid_setpoint, 319)
        self.assertEqual(result.recommended_inverter_setpoint, 319)

    def test_normal_operation_compensates_grid_export(self):
        result = controller.calculate_control(
            self.input(
                grid_power=-100,
                grid_port_power=400,
                load_port_power=0,
                current_grid_setpoint=300,
                current_inverter_setpoint=300,
            ),
            controller.ControlSettings(
                charge_active=False,
                target_grid_power=-10,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.normalized_grid_power, 100)
        self.assertEqual(result.recommended_grid_setpoint, 190)
        self.assertEqual(result.recommended_inverter_setpoint, 190)

    def test_normal_feedback_preserves_load_port_output(self):
        result = controller.calculate_control(
            self.input(
                grid_power=79,
                grid_port_power=173,
                load_port_power=300,
                current_grid_setpoint=250,
                current_inverter_setpoint=550,
            ),
            controller.ControlSettings(
                charge_active=False,
                target_grid_power=-10,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 319)
        self.assertEqual(result.recommended_inverter_setpoint, 619)

    def test_normal_feedback_respects_configured_output_limits(self):
        result = controller.calculate_control(
            self.input(
                grid_power=500,
                grid_port_power=2300,
                load_port_power=0,
                current_grid_setpoint=2390,
                current_inverter_setpoint=2390,
            ),
            controller.ControlSettings(
                charge_active=False,
                target_grid_power=-10,
                grid_limit=2400,
                inverter_limit=2400,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 2400)
        self.assertEqual(result.recommended_inverter_setpoint, 2400)

    def test_grid_charge_does_not_use_normal_feedback_correction(self):
        result = controller.calculate_control(
            self.input(
                grid_power=500,
                current_grid_setpoint=900,
                current_inverter_setpoint=900,
            ),
            controller.ControlSettings(
                charge_active=True,
                charge_source="manual",
                charge_mode="grid_charge",
                charge_power=600,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, -600)

    def test_tariff_request_uses_separate_grid_charge_settings(self):
        decision = controller.select_charge_request(
            manual_active=False,
            manual_cycle_active=False,
            automatic_cycle_active=False,
            tariff_active=True,
            manual_mode="pv_priority",
            cycle_mode="pv_surplus",
            manual_target_soc=90,
            cycle_target_soc=100,
            tariff_target_soc=80,
            charge_power=2400,
            tariff_charge_power=1000,
        )
        self.assertTrue(decision.active)
        self.assertEqual(decision.source, "tariff")
        self.assertEqual(decision.mode, "grid_charge")
        self.assertEqual(decision.target_soc, 80)
        self.assertEqual(decision.charge_power, 1000)

        result = controller.calculate_control(
            self.input(soc=50),
            controller.ControlSettings(
                charge_active=decision.active,
                charge_source=decision.source,
                charge_mode=decision.mode,
                target_soc=decision.target_soc,
                charge_power=decision.charge_power,
            ),
        )
        self.assertEqual(result.status, "tariff_grid_charge")
        self.assertEqual(result.recommended_grid_setpoint, -1000)

    def test_manual_and_cycle_requests_override_tariff_request(self):
        manual = controller.select_charge_request(
            manual_active=True,
            manual_cycle_active=True,
            automatic_cycle_active=True,
            tariff_active=True,
            manual_mode="pv_priority",
            cycle_mode="pv_surplus",
            manual_target_soc=85,
            cycle_target_soc=100,
            tariff_target_soc=80,
            charge_power=1200,
            tariff_charge_power=600,
        )
        self.assertEqual(manual.source, "manual")
        self.assertEqual(manual.target_soc, 85)
        self.assertEqual(manual.charge_power, 1200)

        cycle = controller.select_charge_request(
            manual_active=False,
            manual_cycle_active=False,
            automatic_cycle_active=True,
            tariff_active=True,
            manual_mode="pv_priority",
            cycle_mode="pv_and_grid",
            manual_target_soc=85,
            cycle_target_soc=100,
            tariff_target_soc=80,
            charge_power=1200,
            tariff_charge_power=600,
        )
        self.assertEqual(cycle.source, "cycle_automatic")
        self.assertEqual(cycle.mode, "pv_and_grid")
        self.assertEqual(cycle.charge_power, 1200)

    def test_charge_limit_returns_to_normal_after_target_charge(self):
        self.assertEqual(
            controller.select_charge_limit(
                normal_limit=80,
                target_soc=100,
                charge_active=True,
                low=70,
                high=100,
                step=1,
            ),
            100,
        )
        self.assertEqual(
            controller.select_charge_limit(
                normal_limit=80,
                target_soc=100,
                charge_active=False,
                low=70,
                high=100,
                step=1,
            ),
            80,
        )

    def test_charge_limit_respects_device_range(self):
        self.assertEqual(
            controller.select_charge_limit(
                normal_limit=60,
                target_soc=65,
                charge_active=False,
                low=70,
                high=100,
                step=1,
            ),
            70,
        )

    def test_zero_target_uses_device_minimum_when_zero_is_not_supported(self):
        self.assertEqual(
            1,
            controller.quantize_number_value(0, low=1, high=2400, step=10),
        )
        self.assertEqual(
            0,
            controller.quantize_number_value(0, low=-2400, high=800, step=10),
        )

    def test_external_charge_limit_is_adopted_in_normal_operation(self):
        decision = controller.reconcile_normal_charge_limit(
            normal_limit=80,
            device_limit=85,
            charge_active=False,
            override_active=False,
            pending_write=None,
            low=70,
            high=100,
            step=1,
        )

        self.assertEqual(85, decision.normal_limit)
        self.assertFalse(decision.override_active)
        self.assertIsNone(decision.pending_write)

    def test_temporary_charge_limit_is_not_adopted_as_normal_limit(self):
        active = controller.reconcile_normal_charge_limit(
            normal_limit=80,
            device_limit=100,
            charge_active=True,
            override_active=False,
            pending_write=None,
            low=70,
            high=100,
            step=1,
        )
        awaiting_restore = controller.reconcile_normal_charge_limit(
            normal_limit=active.normal_limit,
            device_limit=100,
            charge_active=False,
            override_active=active.override_active,
            pending_write=None,
            low=70,
            high=100,
            step=1,
        )
        restored = controller.reconcile_normal_charge_limit(
            normal_limit=awaiting_restore.normal_limit,
            device_limit=80,
            charge_active=False,
            override_active=awaiting_restore.override_active,
            pending_write=None,
            low=70,
            high=100,
            step=1,
        )

        self.assertEqual(80, awaiting_restore.normal_limit)
        self.assertTrue(awaiting_restore.override_active)
        self.assertEqual(80, restored.normal_limit)
        self.assertFalse(restored.override_active)

    def test_pending_manager_write_prevents_old_feedback_from_winning(self):
        old_feedback = controller.reconcile_normal_charge_limit(
            normal_limit=90,
            device_limit=80,
            charge_active=False,
            override_active=False,
            pending_write=90,
            low=70,
            high=100,
            step=1,
        )
        confirmed = controller.reconcile_normal_charge_limit(
            normal_limit=old_feedback.normal_limit,
            device_limit=90,
            charge_active=False,
            override_active=old_feedback.override_active,
            pending_write=old_feedback.pending_write,
            low=70,
            high=100,
            step=1,
        )

        self.assertEqual(90, old_feedback.normal_limit)
        self.assertEqual(90, old_feedback.pending_write)
        self.assertEqual(90, confirmed.normal_limit)
        self.assertIsNone(confirmed.pending_write)

    def test_outage_limit_is_restored_before_manual_changes_are_adopted(self):
        for pending in (None, 90):
            with self.subTest(pending=pending):
                decision = controller.ChargeLimitSyncDecision(90, False, pending)
                # 23:13:38 fault, reset feedback; 23:14:53 ready still reports 100.
                for trusted, device in ((False, 90), (False, 100), (True, 100),
                                        (True, 100), (True, 90), (True, 85)):
                    decision = controller.reconcile_normal_charge_limit(
                        normal_limit=decision.normal_limit, device_limit=device,
                        charge_active=False, override_active=decision.override_active,
                        pending_write=decision.pending_write, low=0, high=100,
                        step=1, feedback_trusted=trusted,
                    )
                    self.assertEqual(85 if device == 85 else 90, decision.normal_limit)
                    if device == 100:
                        self.assertTrue(decision.override_active)
                self.assertFalse(decision.override_active)

    def test_runtime_latches_restore_at_fault_entry_without_calculation(self):
        tree = ast.parse((ROOT / PACKAGE.replace(".", "/") / "runtime.py").read_text())
        runtime_class = next(node for node in tree.body
                             if isinstance(node, ast.ClassDef) and node.name == "XT500Runtime")
        for name in ("_begin_control_error", "_begin_communication_pause"):
            with self.subTest(method=name):
                method = next(node for node in runtime_class.body
                              if isinstance(node, ast.FunctionDef) and node.name == name)
                method.decorator_list = []
                namespace = dict(datetime=datetime, UTC=UTC, monotonic=lambda: 1)
                exec(compile(ast.Module(body=[method], type_ignores=[]),
                             "runtime.py", "exec"), namespace)
                runtime = SimpleNamespace(
                    _write_blocked=False, regulation_enabled=True,
                    automatic_recovery_enabled=True, _communication_pause_active=False,
                    _charge_limit_override_active=False,
                    _communication_pause_task=SimpleNamespace(done=lambda: False),
                    _clear_communication_pause=Mock(), _cancel_recovery_task=Mock(),
                    _schedule_recovery=Mock(), _notify=Mock(), _error_detail=str,
                )
                namespace[name](runtime, ConnectionResetError("Connection reset by peer"))
                self.assertTrue(runtime._charge_limit_override_active)

    def test_runtime_fault_feedback_does_not_persist_reset_limit(self):
        tree = ast.parse((ROOT / PACKAGE.replace(".", "/") / "runtime.py").read_text())
        runtime_class = next(node for node in tree.body
                             if isinstance(node, ast.ClassDef) and node.name == "XT500Runtime")
        calculate = next(node for node in runtime_class.body
                         if isinstance(node, ast.FunctionDef) and node.name == "async_calculate")
        start = next(i for i, node in enumerate(calculate.body)
                     if isinstance(node, ast.Assign)
                     and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id == "charge_limit_sync")
        end = next(i for i, node in enumerate(calculate.body)
                   if isinstance(node, ast.Assign)
                   and isinstance(node.targets[0], ast.Attribute)
                   and node.targets[0].attr == "desired_charge_limit")
        block = compile(ast.Module(body=calculate.body[start:end + 1],
                                   type_ignores=[]), "runtime.py", "exec")
        for blocked, paused, recovery in ((True, False, "waiting_feedback"),
                                          (False, True, "ready"),
                                          (False, False, "attempting")):
            with self.subTest(blocked=blocked, paused=paused, recovery=recovery):
                runtime = SimpleNamespace(
                    settings={"normal": 90}, _store=Mock(),
                    _write_blocked=blocked, _communication_pause_active=paused,
                    _recovery_status=recovery, _charge_limit_override_active=False,
                    _normal_charge_limit_write_pending=None,
                )
                namespace = dict(self=runtime, SETTING_NORMAL_CHARGE_LIMIT="normal",
                                 CONF_MAX_CHARGE_SOC_ENTITY="device",
                                 values={"device": 100},
                                 charge_request=SimpleNamespace(active=False, target_soc=100),
                                 charge_limit_low=0, charge_limit_high=100, charge_limit_step=1,
                                 reconcile_normal_charge_limit=controller.reconcile_normal_charge_limit,
                                 select_charge_limit=controller.select_charge_limit)
                exec(block, namespace)
                runtime._store.async_delay_save.assert_not_called()
                self.assertEqual(90, runtime.settings["normal"])
                self.assertEqual(90, runtime.desired_charge_limit)
                runtime._write_blocked = runtime._communication_pause_active = False
                runtime._recovery_status = "ready"
                exec(block, namespace)
                runtime._store.async_delay_save.assert_not_called()
                self.assertEqual(90, runtime.desired_charge_limit)
                namespace["values"]["device"] = 90
                exec(block, namespace)
                namespace["values"]["device"] = 85
                exec(block, namespace)
                self.assertEqual(85, runtime.settings["normal"])
                runtime._store.async_delay_save.assert_called_once()

    def test_outage_does_not_acknowledge_pending_write(self):
        decision = controller.reconcile_normal_charge_limit(
            normal_limit=90, device_limit=90, charge_active=False,
            override_active=False, pending_write=90, low=0, high=100,
            step=1, feedback_trusted=False,
        )
        self.assertEqual(90, decision.pending_write)
        self.assertTrue(decision.override_active)

    def test_temporary_manual_cycle_and_tariff_targets_survive_outage(self):
        for target in (80, 95, 100):
            with self.subTest(target=target):
                decision = controller.ChargeLimitSyncDecision(90, False, None)
                for active, trusted, device in ((True, True, target),
                                                (True, False, 100),
                                                (True, True, target),
                                                (False, True, target),
                                                (False, True, 90)):
                    decision = controller.reconcile_normal_charge_limit(
                        normal_limit=decision.normal_limit, device_limit=device,
                        charge_active=active, override_active=decision.override_active,
                        pending_write=decision.pending_write, low=0, high=100,
                        step=1, feedback_trusted=trusted,
                    )
                    self.assertEqual(90, decision.normal_limit)
                    desired = controller.select_charge_limit(
                        normal_limit=decision.normal_limit, target_soc=target,
                        charge_active=active, low=0, high=100, step=1,
                    )
                    self.assertEqual(max(90, target) if active else 90, desired)
                self.assertFalse(decision.override_active)

    def test_new_cycle_without_reference_is_not_due(self):
        now = datetime(2026, 7, 23, 12, tzinfo=UTC)
        self.assertFalse(
            controller.cycle_is_due(
                now=now,
                last_full=None,
                cycle_reference=None,
                interval_days=14,
            )
        )

    def test_cycle_uses_reference_until_first_full_charge(self):
        reference = datetime(2026, 7, 23, 12, tzinfo=UTC)
        self.assertFalse(
            controller.cycle_is_due(
                now=reference + timedelta(days=13, hours=23),
                last_full=None,
                cycle_reference=reference,
                interval_days=14,
            )
        )
        self.assertTrue(
            controller.cycle_is_due(
                now=reference + timedelta(days=14),
                last_full=None,
                cycle_reference=reference,
                interval_days=14,
            )
        )

    def test_observed_full_charge_is_authoritative_cycle_reference(self):
        now = datetime(2026, 7, 23, 12, tzinfo=UTC)
        self.assertFalse(
            controller.cycle_is_due(
                now=now,
                last_full=now - timedelta(days=1),
                cycle_reference=now - timedelta(days=30),
                interval_days=14,
            )
        )

    def test_next_cycle_check_uses_same_day_when_due_before_check_time(self):
        self.assertEqual(
            controller.next_cycle_check_at(
                baseline=datetime(2026, 7, 1, 8, tzinfo=UTC),
                interval_days=14,
                check_time=time(12, 0),
            ),
            datetime(2026, 7, 15, 12, tzinfo=UTC),
        )

    def test_next_cycle_check_waits_until_next_day_when_due_after_check_time(self):
        self.assertEqual(
            controller.next_cycle_check_at(
                baseline=datetime(2026, 7, 1, 18, tzinfo=UTC),
                interval_days=14,
                check_time=time(12, 0),
            ),
            datetime(2026, 7, 16, 12, tzinfo=UTC),
        )

    def test_low_soc_blocks_discharge(self):
        result = controller.calculate_control(
            self.input(soc=9),
            controller.ControlSettings(minimum_soc=10, meter_export_positive=False),
        )
        self.assertTrue(result.discharge_blocked)
        self.assertLessEqual(result.recommended_grid_setpoint, 0)

    def test_unsigned_xt500_power_is_decoded(self):
        self.assertEqual(controller.decode_signed_16(65500), -36)
        self.assertEqual(controller.decode_signed_16(300), 300)

    def test_battery_flows_show_only_actual_net_discharge(self):
        self.assertEqual(controller.net_battery_flows(200, 300), (0.0, 100.0))

    def test_battery_flows_show_only_actual_net_charge(self):
        self.assertEqual(controller.net_battery_flows(500, 120), (380.0, 0.0))

    def test_battery_flows_never_return_negative_values(self):
        self.assertEqual(controller.net_battery_flows(-20, -10), (0.0, 0.0))

    def test_signed_battery_power_uses_original_xt500_sign(self):
        self.assertEqual(controller.signed_battery_flows(275), (275, 0))
        self.assertEqual(controller.signed_battery_flows(-90), (0, 90))

    def test_normal_direct_pv_charge_is_reported_as_actual_pv_source(self):
        self.assertEqual(
            controller.classify_actual_energy_source(
                net_charge_power=154,
                planned_source="none",
                coupling_mode="dc",
                dc_pv_power=154,
                available_ac_surplus=0,
            ),
            "pv",
        )

    def test_planned_charge_without_measured_charge_reports_no_source(self):
        self.assertEqual(
            controller.classify_actual_energy_source(
                net_charge_power=0,
                planned_source="grid",
                coupling_mode="dc",
                dc_pv_power=0,
                available_ac_surplus=0,
            ),
            "none",
        )

    def test_measured_grid_charge_with_direct_pv_reports_both_sources(self):
        self.assertEqual(
            controller.classify_actual_energy_source(
                net_charge_power=700,
                planned_source="grid",
                coupling_mode="dc",
                dc_pv_power=200,
                available_ac_surplus=0,
            ),
            "pv_and_grid",
        )

    def test_pv_surplus_uses_available_pv_without_false_battery_feedback(self):
        result = controller.calculate_control(
            self.input(
                pv_power=100,
                grid_power=300,
                grid_port_power=44,
                current_grid_setpoint=100,
                current_inverter_setpoint=101,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=False,
                pv_release_allowed=True,
                grid_limit=800,
                inverter_limit=2400,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 100)
        self.assertEqual(result.recommended_inverter_setpoint, 100)

    def test_pv_surplus_reduces_output_until_battery_discharge_is_near_zero(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=50,
                grid_port_power=200,
                current_grid_setpoint=150,
                current_inverter_setpoint=150,
                battery_discharge_power=120,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_deadband=20,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 170)
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 0)
        self.assertEqual(result.battery_discharge_power, 120)

    def test_pv_surplus_prefers_measured_battery_charge_reserve(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=0,
                grid_port_power=200,
                current_grid_setpoint=200,
                current_inverter_setpoint=200,
                battery_charge_power=0,
                battery_discharge_power=0,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_charge_reserve=50,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 50)
        self.assertEqual(result.recommended_grid_setpoint, 150)
        self.assertEqual(result.recommended_inverter_setpoint, 150)

    def test_pv_surplus_charge_reserve_stays_active_during_brief_grid_import(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=-100,
                grid_port_power=100,
                current_grid_setpoint=200,
                current_inverter_setpoint=200,
                battery_charge_power=0,
                battery_discharge_power=0,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_charge_reserve=50,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 50)
        self.assertEqual(result.recommended_grid_setpoint, 150)
        self.assertEqual(result.recommended_inverter_setpoint, 150)

    def test_pv_surplus_holds_output_inside_preferred_charge_band(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=-50,
                grid_port_power=300,
                current_grid_setpoint=120,
                current_inverter_setpoint=120,
                battery_charge_power=60,
                battery_discharge_power=0,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_deadband=20,
                pv_surplus_charge_reserve=50,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 0)
        self.assertEqual(result.recommended_grid_setpoint, 120)
        self.assertEqual(result.recommended_inverter_setpoint, 120)

    def test_pv_surplus_does_not_double_count_export_and_battery_discharge(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=120,
                grid_port_power=300,
                current_grid_setpoint=180,
                current_inverter_setpoint=180,
                battery_discharge_power=120,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_deadband=20,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 170)
        self.assertEqual(result.recommended_grid_setpoint, 10)
        self.assertEqual(result.recommended_inverter_setpoint, 10)

    def test_pv_surplus_continues_reducing_from_current_setpoints(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=10,
                grid_port_power=160,
                current_grid_setpoint=50,
                current_inverter_setpoint=50,
                battery_discharge_power=60,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_deadband=20,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 110)
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 0)

    def test_pv_surplus_never_increases_output_while_battery_is_discharging(self):
        for current in (0, 50, 200, 800):
            with self.subTest(current=current):
                result = controller.calculate_control(
                    self.input(
                        pv_power=1200,
                        grid_power=-100,
                        grid_port_power=500,
                        current_grid_setpoint=current,
                        current_inverter_setpoint=current,
                        battery_discharge_power=100,
                    ),
                    controller.ControlSettings(
                        base_mode="pv_surplus",
                        coupling_mode="dc",
                        meter_export_positive=True,
                        pv_release_allowed=True,
                        pv_surplus_deadband=20,
                    ),
                )

                self.assertLessEqual(result.recommended_grid_setpoint, current)
                self.assertLessEqual(result.recommended_inverter_setpoint, current)

    def test_pv_surplus_corrects_battery_discharge_inside_grid_deadband(self):
        result = controller.calculate_control(
            self.input(
                pv_power=500,
                grid_power=15,
                grid_port_power=200,
                battery_discharge_power=10,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=True,
                pv_release_allowed=True,
                pv_surplus_deadband=20,
            ),
        )

        self.assertEqual(result.pv_surplus_correction, 60)
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 0)

    def test_pv_surplus_control_still_stops_below_release_threshold(self):
        result = controller.calculate_control(
            self.input(
                pv_power=49,
                grid_power=284,
                grid_port_power=0,
                current_grid_setpoint=0,
                current_inverter_setpoint=1,
            ),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=False,
                pv_release_allowed=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 0)

    def test_xt500_grid_output_is_limited_to_800_watts(self):
        result = controller.calculate_control(
            self.input(grid_power=2000, grid_port_power=300),
            controller.ControlSettings(
                grid_limit=800,
                inverter_limit=2400,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 800)
        self.assertGreater(result.recommended_inverter_setpoint, 800)

    def test_xt500_pro_keeps_2400_watt_range(self):
        result = controller.calculate_control(
            self.input(
                grid_power=2100,
                grid_port_power=300,
                current_grid_setpoint=300,
                current_inverter_setpoint=300,
            ),
            controller.ControlSettings(
                grid_limit=2400,
                inverter_limit=2400,
                meter_export_positive=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 2400)
        self.assertEqual(result.recommended_inverter_setpoint, 2400)

    def test_legacy_charge_modes_are_normalized(self):
        expected = {
            "Netzladung": "grid_charge",
            "PV-Überschuss": "pv_surplus",
            "PV-Direkt-Bypass": "pv_surplus",
            "PV-Vorrang": "pv_priority",
            "Nur PV": "pv_priority",
            "PV + Netz": "pv_and_grid",
        }
        for legacy, normalized in expected.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(controller.normalize_charge_mode(legacy), normalized)

    def test_legacy_base_mode_is_normalized(self):
        self.assertEqual(controller.normalize_base_mode("Normalbetrieb"), "normal")
        self.assertEqual(controller.normalize_base_mode("PV-Überschuss"), "pv_surplus")

    def test_live_setpoint_change_is_limited_per_write(self):
        self.assertEqual(
            controller.limit_setpoint_change(0, 1200, -2400, 2400, 10, 200),
            200,
        )
        self.assertEqual(
            controller.limit_setpoint_change(0, -1200, -2400, 2400, 10, 200),
            -200,
        )

    def test_live_setpoint_change_respects_device_limits_after_rounding(self):
        self.assertEqual(
            controller.limit_setpoint_change(90, 200, -95, 95, 10, 200),
            95,
        )

    def test_adaptive_control_uses_small_band_below_first_threshold(self):
        profile = controller.select_adaptive_control_profile(
            7,
            small_error=8,
            large_error=150,
            slow_interval=3,
            medium_interval=2.5,
            fast_interval=1,
            small_maximum_change=20,
            medium_maximum_change=120,
            large_maximum_change=600,
        )
        self.assertEqual(profile.band, "small")
        self.assertEqual(profile.interval, 3)
        self.assertEqual(profile.maximum_change, 20)

    def test_adaptive_control_uses_medium_band_at_small_threshold(self):
        profile = controller.select_adaptive_control_profile(
            80,
            small_error=8,
            large_error=150,
            slow_interval=3,
            medium_interval=2.5,
            fast_interval=1,
            small_maximum_change=20,
            medium_maximum_change=120,
            large_maximum_change=600,
        )
        self.assertEqual(profile.band, "medium")
        self.assertEqual(profile.interval, 2.5)
        self.assertEqual(profile.maximum_change, 120)

    def test_adaptive_control_uses_large_band_at_large_threshold(self):
        profile = controller.select_adaptive_control_profile(
            900,
            small_error=8,
            large_error=150,
            slow_interval=3,
            medium_interval=2.5,
            fast_interval=1,
            small_maximum_change=20,
            medium_maximum_change=120,
            large_maximum_change=600,
        )
        self.assertEqual(profile.band, "large")
        self.assertEqual(profile.interval, 1)
        self.assertEqual(profile.maximum_change, 600)

    def test_overall_control_error_uses_largest_deviation(self):
        self.assertEqual(
            controller.overall_control_error(
                public_grid_power=250,
                public_grid_target=-10,
                current_grid_setpoint=0,
                requested_grid_setpoint=100,
                current_inverter_setpoint=500,
                requested_inverter_setpoint=650,
            ),
            260,
        )

    def test_feedback_waits_for_every_source_after_write(self):
        last_write = datetime.now(UTC)
        self.assertFalse(
            controller.feedback_samples_are_fresh(
                last_write,
                [last_write + timedelta(seconds=1), last_write],
            )
        )
        self.assertTrue(
            controller.feedback_samples_are_fresh(
                last_write,
                [
                    last_write + timedelta(seconds=1),
                    last_write + timedelta(seconds=2),
                ],
            )
        )

    def test_recovery_delays_use_limited_backoff(self):
        self.assertEqual(controller.recovery_delay_seconds(60, 0), 60)
        self.assertEqual(controller.recovery_delay_seconds(60, 1), 300)
        self.assertEqual(controller.recovery_delay_seconds(60, 2), 900)
        self.assertIsNone(controller.recovery_delay_seconds(60, 3))

    def test_recovery_delay_never_drops_below_one_second(self):
        self.assertEqual(controller.recovery_delay_seconds(0, 0), 1)
        self.assertIsNone(controller.recovery_delay_seconds(60, -1))

    def test_transient_write_retry_uses_feedback_based_backoff(self):
        self.assertEqual(controller.write_retry_delay_seconds(6, 1), 6)
        self.assertEqual(controller.write_retry_delay_seconds(6, 2), 12)

    def test_transient_write_retry_stops_after_two_retries(self):
        self.assertIsNone(controller.write_retry_delay_seconds(6, 3))

    def test_transient_readback_wait_covers_three_polling_cycles(self):
        self.assertEqual(
            controller.transient_readback_wait_seconds(5, 3),
            9,
        )
        self.assertEqual(
            controller.transient_readback_wait_seconds(12, 3),
            12,
        )

    def test_short_communication_pause_stays_hidden(self):
        self.assertFalse(controller.communication_pause_is_visible(29.9, 30))
        self.assertTrue(controller.communication_pause_is_visible(30, 30))

    def test_low_pv_stops_release_immediately(self):
        decision = controller.update_pv_release(
            active=True,
            pv_power=50,
            stop_power=50,
            start_power=80,
            start_delay=30,
            above_start_since=None,
            now=100,
        )
        self.assertFalse(decision.active)
        self.assertIsNone(decision.remaining_delay)

    def test_pv_release_requires_continuous_time_above_start_power(self):
        waiting = controller.update_pv_release(
            active=False,
            pv_power=81,
            stop_power=50,
            start_power=80,
            start_delay=30,
            above_start_since=None,
            now=100,
        )
        self.assertFalse(waiting.active)
        self.assertEqual(waiting.above_start_since, 100)
        self.assertEqual(waiting.remaining_delay, 30)

        released = controller.update_pv_release(
            active=False,
            pv_power=90,
            stop_power=50,
            start_power=80,
            start_delay=30,
            above_start_since=waiting.above_start_since,
            now=130,
        )
        self.assertTrue(released.active)

    def test_pv_release_timer_resets_below_start_power(self):
        decision = controller.update_pv_release(
            active=False,
            pv_power=70,
            stop_power=50,
            start_power=80,
            start_delay=30,
            above_start_since=100,
            now=110,
        )
        self.assertFalse(decision.active)
        self.assertIsNone(decision.above_start_since)

    def test_pv_surplus_lockout_sets_both_setpoints_to_zero(self):
        result = controller.calculate_control(
            self.input(pv_power=40),
            controller.ControlSettings(
                base_mode="pv_surplus",
                meter_export_positive=False,
                pv_release_allowed=False,
            ),
        )
        self.assertEqual(result.recommended_grid_setpoint, 0)
        self.assertEqual(result.recommended_inverter_setpoint, 0)

    def test_unknown_discharge_history_is_locked_inside_hysteresis_band(self):
        self.assertTrue(
            controller.update_discharge_hold(
                current_hold=None,
                soc=31,
                minimum_soc=30,
                hysteresis=5,
            )
        )

    def test_discharge_hold_remains_until_release_soc(self):
        self.assertTrue(
            controller.update_discharge_hold(
                current_hold=True,
                soc=34,
                minimum_soc=30,
                hysteresis=5,
            )
        )
        self.assertFalse(
            controller.update_discharge_hold(
                current_hold=True,
                soc=35,
                minimum_soc=30,
                hysteresis=5,
            )
        )

    def test_one_shot_release_ends_at_lower_limit(self):
        self.assertFalse(
            controller.update_discharge_hold(
                current_hold=True,
                soc=31,
                minimum_soc=30,
                hysteresis=5,
                temporary_release=True,
            )
        )
        self.assertTrue(
            controller.update_discharge_hold(
                current_hold=False,
                soc=30,
                minimum_soc=30,
                hysteresis=5,
                temporary_release=True,
            )
        )


class BypassEntryTimerTest(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self):
        tree = ast.parse((ROOT / PACKAGE.replace(".", "/") / "runtime.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "XT500Runtime")
        names = {"_schedule_full_battery_pv_entry",
                 "_async_wait_for_full_battery_pv_entry", "_reset_pv_release_gates"}
        methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name in names]
        for method in methods:
            method.decorator_list = []
        sleep = AsyncMock()
        namespace = {"asyncio": SimpleNamespace(sleep=sleep,
                                               CancelledError=asyncio.CancelledError),
                     "monotonic": lambda: 0.0,
                     "FullBatteryBypassState": controller.FullBatteryBypassState,
                     "FULL_BATTERY_PV_ENTRY_DELAY": controller.FULL_BATTERY_PV_ENTRY_DELAY}
        exec(compile(ast.Module(body=methods, type_ignores=[]), "runtime.py", "exec"), namespace)
        runtime = SimpleNamespace(
            _full_battery_pv_transition=controller.FullBatteryBypassState(eligible_since=0),
            _full_battery_pv_entry_task=None, async_calculate=Mock(),
            _cancel_pv_release_timer=Mock(),
            hass=SimpleNamespace(async_create_task=asyncio.create_task))
        for name in names:
            setattr(runtime, name, MethodType(namespace[name], runtime))
        return runtime, sleep

    async def test_unchanged_input_still_wakes_entry_after_delay(self):
        runtime, sleep = self.make_runtime()
        runtime._schedule_full_battery_pv_entry()
        task = runtime._full_battery_pv_entry_task
        runtime._schedule_full_battery_pv_entry()
        self.assertIs(runtime._full_battery_pv_entry_task, task)
        await task
        sleep.assert_awaited_once_with(30.0)
        runtime.async_calculate.assert_called_once()
        self.assertIsNone(runtime._full_battery_pv_entry_task)

    async def test_invalid_or_disabled_inputs_cancel_pending_entry(self):
        runtime, sleep = self.make_runtime()
        runtime._schedule_full_battery_pv_entry()
        task = runtime._full_battery_pv_entry_task
        runtime._reset_pv_release_gates()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(runtime._full_battery_pv_transition,
                         controller.FullBatteryBypassState())
        self.assertIsNone(runtime._full_battery_pv_entry_task)
        runtime.async_calculate.assert_not_called()
        sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
