"""Offline boundary probes of existing controller; does not model XT500 hardware."""
import importlib.util
import itertools
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('soc_tests', root / 'tests/test_xt500_controller.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
c = tests.controller
factory = tests.ControllerTest().input
checks = 0
for limit, margin, previous in itertools.product(range(1, 100), range(1, 11), (None, False, True)):
    if limit + margin > 100:
        continue
    for soc, expected in ((limit - .01, True), (limit, True),
                          (limit + .01, True if previous is None else previous),
                          (limit + margin - .01, True if previous is None else previous),
                          (limit + margin, False), (limit + margin + .01, False)):
        actual = c.update_discharge_hold(current_hold=previous, soc=soc,
                                        minimum_soc=limit, hysteresis=margin)
        assert actual == expected, (limit, margin, previous, soc, actual)
        checks += 1
scenarios = 0
for coupling, mode, pv, load, grid, current, minimum in itertools.product(
        ('ac', 'dc', 'auto'), ('normal', 'pv_surplus'), (0, 300, 2000),
        (0, 500), (-1200, 0, 1200), (0, 800), (40, 80)):
    result = c.calculate_control(factory(soc=minimum, pv_power=pv,
        load_port_power=load, grid_power=grid, current_grid_setpoint=current),
        c.ControlSettings(minimum_soc=minimum, discharge_hold=True,
                          coupling_mode=coupling, base_mode=mode))
    assert result.discharge_blocked
    assert result.recommended_grid_setpoint <= 0
    assert result.recommended_inverter_setpoint <= (0 if coupling == 'ac' else pv)
    scenarios += 1
# A low charge target only blocks an active charging request in current code.
normal = c.calculate_control(factory(soc=60, pv_power=2000),
                             c.ControlSettings(target_soc=60))
assert not normal.charge_blocked
active = c.calculate_control(factory(soc=60, pv_power=2000),
    c.ControlSettings(target_soc=60, charge_active=True, charge_mode='grid_charge'))
assert active.charge_blocked
assert active.recommended_grid_setpoint >= 0
# These results are setpoints, not a battery-charge actuator or load-port shutoff.
print(json.dumps({'hysteresis_boundary_checks': checks,
                  'discharge_controller_scenarios': scenarios,
                  'normal_mode_low_charge_target_blocks': normal.charge_blocked,
                  'active_grid_charge_target_blocks': active.charge_blocked,
                  'scope': 'existing software only; no hardware simulation'}, indent=2))
