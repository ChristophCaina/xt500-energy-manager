# XT500 Energy Manager 1.11.3

Community Home Assistant controller for SunEnergyXT XT500 and XT500 Pro
systems. The integration directly controls the grid-port setpoint, inverter
ceiling, and system charge limit.

Optional grid-operation reserve uses the original discharge hysteresis without
changing device SOC settings. First-time setup can create the sidebar dashboard
and register its JavaScript automatically. Existing layouts and deliberate
removal are preserved. The reserve does not guarantee island supply or protection
during a Home Assistant or network outage.

## Safety and control behavior

- Production writes start only after Home Assistant is fully running and every
  configured input remained valid for five seconds.
- Adaptive small, medium, and large response bands limit write frequency and
  setpoint changes.
- After a control write, fresh public-meter and XT500 grid-port feedback is
  required before another correction.
- A temporarily unavailable setpoint readback is checked once per second for
  up to three device polling cycles. Writes remain blocked during the gap;
  short self-healing pauses become visible only after 30 seconds, while the
  90-second hard safety stop remains unchanged.
- Invalid input data stops writes. A write error latches the controller in a
  stopped state. Optional automatic recovery waits for stable fresh feedback,
  probes the unchanged inverter setpoint, and requires new measurements before
  releasing the latch. Three failed attempts still require a manual master
  switch reset.
- In PV-surplus mode, low PV clamps both setpoints to zero immediately. Output
  is released only after PV stayed above the restart threshold for the
  configured delay.
- **Preferred battery charging power in PV-surplus mode** is a measured net
  battery-flow target used only by PV-surplus control. It reduces XT500 output
  by every measured watt of battery discharge plus the missing charge reserve,
  holds the output inside the charge band to avoid oscillation, and does not
  request fixed grid charging. The grid-export deadband does not apply to
  battery discharge.
- **Export PV surplus when battery is full** is off by default. Once the
  device charge limit is reached, and while no charge request is active, direct
  XT500 PV may feed the grid after local loads. The controller commands GS=0
  and raises IS within the configured grid-output allowance, inverter limit,
  and device limits. A 1% SOC hold band prevents rapid switching. Measured
  battery discharge reduces IS; invalid required inputs still stop writes.
- The integration does not discover, disable, or enable unrelated automations.
  Any existing automation that writes the same device setpoints must be disabled
  before this controller is enabled.
- Disabling production control first stops pending writes, neutralizes the grid
  setpoint and inverter ceiling, restores the normal charge limit, and verifies
  device feedback before the switch reports off.
- The lower-SOC discharge hold is reconstructed safely after reloads. A
  one-shot dashboard action may temporarily release it within the hysteresis
  band only while the optional reserve is disabled; the original device limit is restored with verified feedback at the
  configured lower limit, on shutdown, or after restart.

## Charge limits and targets

- **Normal-operation charge limit** and the selected device system charge-limit
  entity are synchronized in both directions during normal operation.
- Manual or automatic target charging temporarily raises the device limit when
  the requested target is higher than the normal limit.
- Reaching a target ends the corresponding charge request and restores the
  normal-operation limit.
- Reaching the automatic full-charge target through ordinary PV charging also
  records a completed full charge and resets the cycle interval.
- The configured value is clamped to the range supported by the selected device
  entity.

## Charging modes

- **Grid charging:** requests the configured charging power from the grid.
- **PV surplus:** uses available DC and AC PV surplus without intentional grid
  import. Measured battery discharge and public-grid export close the feedback
  loop around zero; the larger error reduces both GS and IS, with a configurable
  deadband to avoid oscillation.
- **PV priority:** prioritizes battery charging from DC and AC PV and prevents
  intentional battery discharge while the target remains active.
- **PV and grid:** treats the configured power as total battery charging power;
  PV reduces only the required grid remainder.

The coupling selector offers hybrid (recommended), XT500-PV-only, and external
AC-PV-only control. The public grid meter remains authoritative. An optional
signed AC PV production sensor improves display and diagnostics but never
authorizes charging by itself.

The full-battery export switch is in **Operating mode and grid target** in the
generated dashboard. It applies to direct XT500 DC PV in normal operation and
the PV-surplus base mode. Manual, cycle, and tariff charging take precedence;
AC-only coupling cannot activate the XT500 bypass. The active status reads
**Battery full – PV export**. Actual export depends on PV, local consumption,
and the configured and device limits. The separate 100% cycle-charge
confirmation does not determine this bypass.

Bypass requires enough DC PV to cover consumption after the load port.
Measured XT500 output, public-grid power, and battery discharge check that
condition with a 30 W feedback tolerance. If PV cannot cover consumption, the
selected base mode resumes. Normal operation can supply the deficit from the
battery subject to its existing discharge limits; the PV-surplus base mode
retains its existing discharge policy. This also accounts for conversion
losses and prevents repeated entry while the battery supplies a deficit.

Entry requires 30 continuous seconds of eligibility, with at most 10 W
battery discharge and 10 W public import relative to the grid target.
Export is not deducted from battery discharge to prove entry eligibility:
export may itself come from the battery. Established bypass retains the
30 W exit tolerance and leaves immediately on a supply gap. Re-entry needs
a new qualification period; the selected base mode runs while waiting.
The device charge hysteresis and 1% SOC latch are independent of this power gate.

IS is an output ceiling, not a demand to discharge the battery. The bypass
opens that ceiling within the configured limits even if the current PV
measurement is already curtailed. Local consumption and conversion losses
must be considered when comparing DC PV input with public-grid export.

For a brief test, temporarily lower the system charge limit to a permitted
value no higher than the current SOC. The device normally permits only
70–100%. Record the original limit, finish active charge requests, observe
grid and battery power while DC PV exceeds consumption with a reserve for
losses, and restore the original limit afterwards. Version 1.10.6 fixes the missing Home Assistant enum option
for the bypass status and isolates entity-update errors from device writes.

Manual charging overrides an automatic due state. Both return to the selected
base mode after completion.

## Dynamic tariff charging

The integration exposes a separate tariff charge request with its own target
SOC, grid charging power, and safety expiry. Manual and cycle charging take
priority. An unrefreshed request expires automatically and returns to the base
mode.

The included provider-independent automation blueprint evaluates any numeric
current-price sensor with separate start and stop thresholds:

`custom_components/xt500_energy_manager/blueprints/dynamic_tariff_charging.yaml`

It refreshes a cheap-price request every 15 minutes and switches it off when
the price is invalid, the target SOC is reached, or the stop threshold is
reached. Normal operation already uses the battery for home consumption at
high prices; this feature does not request battery export to the public grid.

The integration installs its bundled copy automatically under Home Assistant's
automation blueprints and safely synchronizes it after HACS updates. A
management hash prevents locally modified copies from being overwritten.

## Installation

1. Install and configure the original
   [SunEnergyXT 500 Series](https://github.com/SunEnergyXT/SunEnergyXT-500-Series)
   integration first.
2. Add `https://github.com/achim1985/xt500-energy-manager` to HACS as a
   custom repository of type **Integration** and download it.
3. Restart Home Assistant.
4. Add **XT500 Energy Manager** under Settings → Devices & services.
5. Select the SunEnergy XT500 device. Its original measurement, setpoint, and
   limit entities are detected automatically.
6. Select the external total grid-power sensor and confirm its sign convention.
   Optionally select AC PV power and its sign. A full manual expert setup remains
   available.
7. New installations start with regulation disabled. Ensure no other automation
   writes those same number entities, then enable
   the energy manager.

## Generated dashboard

First-time setup enables **Create dashboard automatically** by default. It
registers the JavaScript module and creates the sidebar dashboard. Existing
entries retain their manual workflow. With YAML-managed resources or opt-out,
register `/xt500_energy_manager/xt500-energy-dashboard-strategy.js` as a
JavaScript module, then add the **XT500 Energiemanager** community dashboard.

The generated dashboard uses only built-in Home Assistant cards. It includes
status, power flows, manual and automatic charging, normal-operation limits,
adaptive tuning, and a collapsible operating guide.

With SunEnergyXT 1.1.2 or newer, the integration also discovers the original
daily PV production (`PD`), grid charging (`GD1`), grid export (`GD2`), and
off-grid output (`LD`) sensors on the selected device. The compact
**Energie heute** block displays those kWh values directly without creating
helper sensors. Missing optional daily sensors simply hide their tile.

SunEnergyXT 1.1.3 polling intervals from 3 to 60 seconds are detected from the
original config entry and included in communication and recovery timeouts. The
new optional `SI1` and `SA1` device hysteresis entities are discovered
automatically. Both device defaults are 5%; restore them to 5% after temporary
custom tests.

The graphical strategy editor can add individual views from other
storage-mode Home Assistant dashboards as native top-level tabs. The source
view remains authoritative and is reloaded with the strategy. Existing source
visibility restrictions are preserved; an imported view can additionally be
limited to the user who configured it.

The same editor can reorder or hide the independently generated blocks on the
overview and settings pages. Up/down controls work on desktop and mobile, and
each page can be reset to its complete default layout. The overview uses up to
three responsive columns and compact built-in tiles for power flows, quick
controls, and daily energy.

Battery charging and discharging are displayed as mutually exclusive values
from the original signed XT500 battery-power sensor (`BP`). Existing entries
are migrated automatically when the current SunEnergyXT integration provides
that sensor. Total input and output remain a compatibility fallback for older
SunEnergyXT versions without `BP`.
The cycle status also shows the next calculated cycle-charge date.

Use a maximum positive home-grid output of about 800 W for an XT500 unless the
local installation permits another value. This output setting does not limit
the negative grid-charging setpoint. Grid charging follows the configured
charging power and the source entity's real device range; XT500 Pro systems can
charge at up to 2400 W.

## Optional external net grid measurement

Select **External grid power sensor** in setup/options to create net/import/export power and persistent import/export energy sensors. Use the net active power across all phases at the house connection, not the XT500 grid-port power. Select **Grid import energy** and **Grid export energy** in the HA Energy dashboard. Sign inversion is optional; clearing the source disables measurement.
