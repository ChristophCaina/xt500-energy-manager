import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

const strategySource = fs.readFileSync(
  new URL(
    "../custom_components/xt500_energy_manager/frontend/xt500-energy-dashboard-strategy.js",
    import.meta.url,
  ),
  "utf8",
);

const customElementRegistry = new Map();
const context = vm.createContext({
  console,
  window: {},
  customElements: {
    define: (name, elementClass) => customElementRegistry.set(name, elementClass),
    get: (name) => customElementRegistry.get(name),
  },
  document: {
    createElement: (tagName) => ({ tagName }),
  },
  HTMLElement: class {
    attachShadow() {
      this.shadowRoot = {};
      return this.shadowRoot;
    }
  },
  CustomEvent: class {},
});
vm.runInContext(strategySource, context);

const Strategy = customElementRegistry.get(
  "ll-strategy-dashboard-xt500-energy-manager",
);
const StrategyEditor = customElementRegistry.get(
  "xt500-energy-manager-strategy-editor",
);

const plain = (value) => JSON.parse(JSON.stringify(value));

const managerState = {
  state: "Normalbetrieb",
  attributes: {
    integration: "xt500_energy_manager",
    xt500_manager_id: "manager-1",
    xt500_key: "status",
  },
};

const createHass = (dashboards, userId = "user-1") => ({
  states: {
    "sensor.xt500_status": managerState,
  },
  user: { id: userId },
  callWS: async (message) => {
    assert.equal(message.type, "lovelace/config");
    if (!(message.url_path in dashboards)) {
      throw new Error("Dashboard not found");
    }
    return dashboards[message.url_path];
  },
});

const createLayoutHass = () => {
  const hass = createHass({});
  hass.states["sensor.xt500_status"] = {
    ...managerState,
    attributes: {
      ...managerState.attributes,
      source_soc_entity: "sensor.xt500_soc",
      source_pv_power_entity: "sensor.xt500_pv",
      source_ac_pv_power_entity: "sensor.ac_pv",
      source_pv_daily_energy_entity: "sensor.xt500_pd",
      source_grid_charge_daily_energy_entity: "sensor.xt500_gd1",
      source_grid_export_daily_energy_entity: "sensor.xt500_gd2",
      source_offgrid_daily_energy_entity: "sensor.xt500_ld",
    },
  };
  hass.states["sensor.xt500_soc"] = { state: "72", attributes: {} };
  hass.states["sensor.xt500_pv"] = { state: "500", attributes: {} };
  hass.states["sensor.ac_pv"] = { state: "-300", attributes: {} };
  for (const key of ["pd", "gd1", "gd2", "ld"]) {
    hass.states[`sensor.xt500_${key}`] = {
      state: "1.234",
      attributes: { unit_of_measurement: "kWh" },
    };
  }
  for (const key of [
    "recommended_grid_setpoint",
    "pv_surplus_correction",
    "selected_mode",
    "active_mode",
    "active_operation",
    "mode_state",
    "selected_coupling_mode",
    "active_coupling_mode",
    "active_energy_source",
    "ac_pv_power",
    "available_ac_surplus",
    "cycle_state",
    "full_charge_confirmation",
    "battery_charge_power",
    "regulation_enabled",
    "automatic_recovery_enabled",
    "manual_active",
    "tariff_active",
    "tariff_target_soc",
    "tariff_charge_power",
    "tariff_request_duration",
    "tariff_expires_at",
    "automatic_enabled",
    "cycle_start",
    "discharge_hold",
    "discharge_override_active",
    "discharge_release",
    "charge_soc_hysteresis",
    "pv_surplus_deadband",
    "pv_surplus_charge_reserve",
    "full_charge_min_hold_minutes",
    "full_charge_taper_power",
    "full_charge_taper_minutes",
    "full_charge_timeout_minutes",
    "full_charge_top_off_power",
    "control_band",
    "control_error",
    "control_interval",
    "control_max_step",
    "control_small_error",
    "control_large_error",
    "control_small_max_step",
    "control_medium_max_step",
    "control_large_max_step",
    "control_slow_interval",
    "control_medium_interval",
    "control_fast_interval",
    "feedback_settle_time",
    "recovery_stability_time",
    "pv_stop_power",
    "pv_start_power",
    "pv_start_delay",
    "base_mode",
    "full_battery_pv_export",
    "coupling_mode",
    "show_advanced",
  ]) {
    hass.states[`sensor.xt500_${key}`] = {
      state: "0",
      attributes: {
        integration: "xt500_energy_manager",
        xt500_manager_id: "manager-1",
        xt500_key: key,
      },
    };
  }
  return hass;
};

const sectionHeadings = (view) => view.sections.map((section) =>
  section.cards[0].heading || section.cards[0].title,
);

test("zeigt den internen Rückmeldungs-Handshake nicht im Dashboard", () => {
  assert.doesNotMatch(strategySource, /feedback_ready|Neue Rückmeldungen/);
});

test("bindet genau die ausgewählte Quellansicht als echten Reiter ein", async () => {
  const source = {
    views: [
      {
        title: "Übersicht",
        path: "home",
        cards: [{ type: "markdown", content: "Nicht auswählen" }],
      },
      {
        title: "Strom",
        path: "strom",
        icon: "mdi:flash",
        type: "sections",
        visible: [{ user: "existing-user" }],
        sections: [{ type: "grid", cards: [{ type: "gauge", entity: "sensor.pv" }] }],
      },
    ],
  };
  const originalSource = structuredClone(source);
  const result = await Strategy.generate(
    {
      additional_views: [{
        source_dashboard: "dashboard-achim",
        source_view: "path:strom",
        title: "PV",
        icon: "mdi:solar-power",
        visibility: "all",
      }],
    },
    createHass({ "dashboard-achim": source }),
  );

  assert.equal(result.views.length, 9);
  const imported = result.views[1];
  assert.equal(imported.title, "PV");
  assert.equal(imported.icon, "mdi:solar-power");
  assert.equal(imported.path, "zusatz-dashboard-achim-strom");
  assert.equal(imported.subview, false);
  assert.deepEqual(plain(imported.visible), [{ user: "existing-user" }]);
  assert.deepEqual(plain(imported.sections), source.views[1].sections);
  assert.deepEqual(plain(result.views.map((view) => view.path)), [
    "speicher",
    "zusatz-dashboard-achim-strom",
    "energie",
    "energie-verlauf",
    "energie-verbraucher",
    "energie-live",
    "einstellungen",
    "laden",
    "feinabstimmung",
  ]);
  assert.equal(result.views.at(-1).path, "feinabstimmung");
  assert.deepEqual(source, originalSource);
});

test("Nur für mich setzt die Ansicht auf den beim Speichern erfassten Benutzer", async () => {
  const result = await Strategy.generate(
    {
      additional_views: [{
        source_dashboard: "pv",
        source_view: "path:strom",
        visibility: "user",
        user_id: "saved-user",
      }],
    },
    createHass({
      pv: {
        views: [{ title: "Strom", path: "strom", cards: [] }],
      },
    }),
  );

  assert.deepEqual(plain(result.views[1].visible), [{ user: "saved-user" }]);
  assert.equal(result.views.at(-1).path, "feinabstimmung");
});

test("ignoriert doppelte Einträge und Strategie-Ansichten", async () => {
  const duplicate = {
    source_dashboard: "pv",
    source_view: "path:strom",
    visibility: "all",
  };
  const result = await Strategy.generate(
    { additional_views: [duplicate, structuredClone(duplicate)] },
    createHass({
      pv: {
        views: [
          { title: "Strom", path: "strom", cards: [] },
          {
            title: "Dynamisch",
            path: "dynamisch",
            strategy: { type: "custom:other" },
          },
        ],
      },
    }),
  );

  assert.equal(result.views.length, 9);
});

test("verhindert Selbstimport und lässt das Energiemanager-Dashboard benutzbar", async () => {
  const result = await Strategy.generate(
    {
      additional_views: [
        {
          source_dashboard: "xt500",
          source_view: "path:speicher",
          visibility: "all",
        },
        {
          source_dashboard: "missing",
          source_view: "path:strom",
          visibility: "all",
        },
      ],
    },
    createHass({
      xt500: {
        strategy: { type: "custom:xt500-energy-manager" },
      },
    }),
  );

  assert.equal(result.views.length, 8);
  assert.equal(result.views[0].path, "speicher");
  assert.equal(result.views.at(-1).path, "feinabstimmung");
});

test("stellt einen grafischen Strategy-Editor bereit", () => {
  assert.deepEqual(Strategy.getConfigElement(), {
    tagName: "xt500-energy-manager-strategy-editor",
  });
  assert.ok(customElementRegistry.has("xt500-energy-manager-strategy-editor"));
});

test("Editor verschiebt, versteckt und setzt Blöcke zurück", () => {
  let changes = 0;
  const editor = {
    _config: {},
    _changed: () => {
      changes += 1;
    },
    _render: () => {},
  };

  StrategyEditor.prototype._moveBlock.call(
    editor,
    "overview",
    "regulation_status",
    -1,
  );
  assert.deepEqual(plain(editor._config.overview_block_order.slice(0, 2)), [
    "regulation_status",
    "storage",
  ]);

  StrategyEditor.prototype._setBlockVisible.call(
    editor,
    "overview",
    "setpoints",
    false,
  );
  assert.deepEqual(plain(editor._config.overview_block_hidden), ["setpoints"]);

  StrategyEditor.prototype._resetBlockLayout.call(editor, "overview");
  assert.deepEqual(plain(editor._config.overview_block_hidden), []);
  assert.deepEqual(plain(editor._config.overview_block_order), [
    "storage",
    "regulation_status",
    "quick_controls",
    "flows",
    "energy_today",
    "cycle",
    "setpoints",
  ]);
  assert.equal(changes, 3);
});

test("Editor schaltet zwischen ausführlichen, kompakten und verborgenen Energieseiten um", () => {
  let changes = 0;
  const editor = {
    _config: {},
    _changed: () => {
      changes += 1;
    },
    _render: () => {},
  };

  StrategyEditor.prototype._setEnergyViewMode.call(editor, "compact");
  assert.equal(editor._config.energy_views_mode, "compact");
  StrategyEditor.prototype._setEnergyViewMode.call(editor, "hidden");
  assert.equal(editor._config.energy_views_mode, "hidden");
  StrategyEditor.prototype._setEnergyViewMode.call(editor, "invalid");
  assert.equal(editor._config.energy_views_mode, "detailed");
  assert.equal(changes, 3);
});

test("teilt die Speicheransicht standardmäßig in einzeln anordenbare Blöcke", async () => {
  const result = await Strategy.generate({}, createLayoutHass());

  assert.deepEqual(plain(sectionHeadings(result.views[0])), [
    "Speicherstand",
    "Regelungsstatus",
    "Schnellsteuerung",
    "Aktuelle Leistungsflüsse",
    "Energie heute",
    "Zyklusladung",
    "Sollwerte und Berechnung",
  ]);
  const settings = result.views.find((view) => view.path === "einstellungen");
  assert.deepEqual(plain(sectionHeadings(settings)), [
    "Bedienung und Sicherheit",
    "Weitere Einstellungen",
    "Hauptsteuerung",
    "Betriebsart und Netzziel",
    "Batteriegrenzen und Schutz",
  ]);
  const charging = result.views.find((view) => view.path === "laden");
  assert.deepEqual(plain(sectionHeadings(charging)), [
    "Manuelle Zielladung",
    "Zyklusladung",
    "Dynamischer Stromtarif",
    "Bestätigung der 100-%-Vollladung",
  ]);
  const tuning = result.views.find((view) => view.path === "feinabstimmung");
  assert.deepEqual(plain(sectionHeadings(tuning)), [
    "Regelstatus und Abweichungen",
    "Leistungsschritte und Reaktionszeiten",
    "Automatische Fehlerwiederherstellung",
  ]);
  assert.equal(charging.subview, true);
  assert.equal(tuning.subview, true);
  assert.equal(charging.back_path, "/xt500-energiemanager/einstellungen");
});

test("zeigt ausgewählte und aktive Lade- sowie Kopplungszustände genau einmal", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const overview = result.views.find((view) => view.path === "speicher");
  const settings = result.views.find((view) => view.path === "einstellungen");
  const statusSection = overview.sections.find(
    (section) => section.cards[0].heading === "Regelungsstatus",
  );
  const statusNames = statusSection.cards[1].entities.map((item) => item.name);

  for (const name of [
    "Aktiver Vorgang",
    "Ausgewählter Lademodus",
    "Aktiver Lademodus",
    "Zustand des Lademodus",
    "Gewählte PV-Berücksichtigung",
    "Aktuell nutzbare PV-Quelle",
    "Tatsächliche Ladequelle",
  ]) {
    assert.equal(statusNames.filter((value) => value === name).length, 1);
  }

  const allSettingNames = settings.sections
    .flatMap((section) => section.cards)
    .flatMap((card) => card.entities?.map((item) => item.name) || [card.name]);
  assert.equal(
    allSettingNames.filter((name) => name === "PV für Regelung berücksichtigen").length,
    1,
  );
  assert.equal(
    allSettingNames.filter(
      (name) => name === "Bevorzugte Akku-Ladeleistung im PV-Überschussmodus",
    ).length,
    1,
  );
});

test("zeigt Entladesperre und einmalige Freigabe eindeutig", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const overview = result.views.find((view) => view.path === "speicher");
  const settings = result.views.find((view) => view.path === "einstellungen");
  const statusSection = overview.sections.find(
    (section) => section.cards[0].heading === "Regelungsstatus",
  );
  const statusNames = statusSection.cards[1].entities.map((item) => item.name);
  assert.equal(statusNames.filter((name) => name === "Entladesperre aktiv").length, 1);
  assert.equal(
    statusNames.filter((name) => name === "Temporäre Entladefreigabe aktiv").length,
    1,
  );

  const normalSection = settings.sections.find(
    (section) => section.cards[0].heading === "Batteriegrenzen und Schutz",
  );
  assert.equal(
    normalSection.cards.filter(
      (card) => card.name === "Entladesperre einmalig freigeben",
    ).length,
    1,
  );
});

test("zeigt den Vollakku-Einspeiseschalter in den Betriebseinstellungen", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const settings = result.views.find((view) => view.path === "einstellungen");
  const section = settings.sections.find(
    (item) => item.cards[0].heading === "Betriebsart und Netzziel",
  );
  assert.ok(section);
  assert.ok(JSON.stringify(section).includes("PV-Überschuss bei vollem Akku einspeisen"));
});

test("blendet AC-PV-Werte bei reiner XT500-PV-Auswahl aus", async () => {
  const hass = createLayoutHass();
  hass.states["sensor.xt500_coupling_mode"].state = "dc";
  const result = await Strategy.generate({}, hass);
  const overview = result.views.find((view) => view.path === "speicher");
  const flows = overview.sections.find(
    (section) => section.cards[0].heading === "Aktuelle Leistungsflüsse",
  );
  const flowNames = flows.cards.slice(1).map((card) => card.name);

  assert.ok(flowNames.includes("XT500-PV-Erzeugung (DC)"));
  assert.ok(!flowNames.includes("Externe AC-PV-Erzeugung"));
  assert.ok(!flowNames.includes("AC-PV-Überschuss am Netzanschluss"));
});

test("wendet Reihenfolge und ausgeblendete Blöcke für beide Seiten an", async () => {
  const result = await Strategy.generate(
    {
      overview_block_order: [
        "quick_controls",
        "flows",
        "energy_today",
        "storage",
        "regulation_status",
        "setpoints",
        "cycle",
      ],
      overview_block_hidden: ["flows"],
      settings_block_order: [
        "normal_limits",
        "target_charge",
        "tariff_charge",
        "main_control",
        "advanced",
        "guide",
      ],
      settings_block_hidden: ["guide", "advanced"],
    },
    createLayoutHass(),
  );

  assert.deepEqual(plain(sectionHeadings(result.views[0])), [
    "Schnellsteuerung",
    "Energie heute",
    "Speicherstand",
    "Regelungsstatus",
    "Sollwerte und Berechnung",
    "Zyklusladung",
  ]);
  const settings = result.views.find((view) => view.path === "einstellungen");
  assert.deepEqual(plain(sectionHeadings(settings)), [
    "Betriebsart und Netzziel",
    "Weitere Einstellungen",
    "Batteriegrenzen und Schutz",
    "Hauptsteuerung",
  ]);
  const charging = result.views.find((view) => view.path === "laden");
  assert.deepEqual(plain(sectionHeadings(charging)), [
    "Manuelle Zielladung",
    "Zyklusladung",
    "Dynamischer Stromtarif",
    "Bestätigung der 100-%-Vollladung",
  ]);
  assert.equal(result.views.find((view) => view.path === "feinabstimmung").sections.length, 0);
});

test("ordnet die Schnellsteuerung eindeutig und zeigt Fehlerbehebung nur in Einstellungen", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const overview = result.views.find((view) => view.path === "speicher");
  const settings = result.views.find((view) => view.path === "einstellungen");
  const charging = result.views.find((view) => view.path === "laden");
  const quickControls = overview.sections.find(
    (section) => section.cards[0].heading === "Schnellsteuerung",
  );
  const mainControl = settings.sections.find(
    (section) => section.cards[0].heading === "Hauptsteuerung",
  );
  const targetCharge = charging.sections.find(
    (section) => section.cards[0].heading === "Zyklusladung",
  );

  assert.deepEqual(plain(quickControls.cards.slice(1).map((card) => card.name)), [
    "Regelung",
    "Zielladung",
    "Automatik",
    "Zyklusstart",
  ]);
  assert.equal(
    quickControls.cards.some((card) => card.entity?.includes("automatic_recovery")),
    false,
  );
  assert.equal(
    mainControl.cards.some((card) =>
      card.entities?.some((item) => item.entity.includes("automatic_recovery"))
    ),
    true,
  );

  assert.equal(
    targetCharge.cards.some((card) =>
      card.entities?.some((item) => item.name === "Automatische Zyklusüberwachung")
    ),
    true,
  );
  assert.equal(
    targetCharge.cards.some((card) => card.name === "Jetzt manuell starten"),
    true,
  );
});

test("zeigt die Tarifladung nur einmal als eigenen Einstellungsblock", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const charging = result.views.find((view) => view.path === "laden");
  const tariffSections = charging.sections.filter(
    (section) => section.cards[0].heading === "Dynamischer Stromtarif",
  );

  assert.equal(tariffSections.length, 1);
  assert.deepEqual(plain(tariffSections[0].cards[1].entities.slice(0, 4).map((item) => item.name)), [
    "Tarifladung anfordern",
    "Ladeziel",
    "Netz-Ladeleistung",
    "Gültigkeit je Anforderung",
  ]);
});

test("erzeugt historische und aktuelle Energieansichten vor der Einstellungsseite", async () => {
  const result = await Strategy.generate({}, createLayoutHass());
  const energyViews = result.views.filter((view) =>
    view.path.startsWith("energie"),
  );

  assert.deepEqual(plain(energyViews.map((view) => view.path)), [
    "energie",
    "energie-verlauf",
    "energie-verbraucher",
    "energie-live",
  ]);
  assert.equal(result.views.at(-1).path, "feinabstimmung");

  const historicalViews = energyViews.filter((view) =>
    view.path !== "energie-live"
  );
  const historicalCards = historicalViews.flatMap((view) =>
    view.sections.flatMap((section) => section.cards),
  );
  const linkedCards = historicalCards.filter((card) =>
    card.type.startsWith("energy-"),
  );
  assert.ok(linkedCards.length > 10);
  assert.ok(linkedCards.every(
    (card) => card.collection_key === "energy_xt500_manager",
  ));
  assert.ok(historicalViews.every((view) =>
    view.sections[0].cards.some((card) => card.type === "energy-date-selection"),
  ));
  assert.ok(historicalViews.every((view) =>
    !view.sections.flatMap((section) => section.cards)
      .some((card) => card.type === "energy-compare-card"),
  ));

  const liveView = energyViews.find((view) => view.path === "energie-live");
  const liveCards = liveView.sections.flatMap((section) => section.cards);
  assert.ok(liveCards.some((card) => card.type === "power-sources-graph"));
  assert.ok(liveCards.some((card) => card.type === "power-sankey"));
  assert.equal(energyViews
    .flatMap((view) => view.sections.flatMap((section) => section.cards))
    .filter((card) => card.type === "power-sources-graph").length, 1);
  assert.ok(!liveCards.some((card) => card.type === "energy-date-selection"));
  assert.ok(liveCards.filter((card) => card.type.startsWith("power-")).every(
    (card) => card.collection_key === "energy_xt500_manager_live",
  ));
  assert.deepEqual(plain(liveView.badges), [
    {
      type: "power-total",
      collection_key: "energy_xt500_manager_live",
    },
    {
      type: "entity",
      entity: "sensor.xt500_soc",
      show_name: false,
      show_icon: true,
      show_state: true,
    },
  ]);
});

test("unterstützt kompakte und ausgeblendete Energieseiten", async () => {
  const compact = await Strategy.generate(
    { energy_views_mode: "compact" },
    createLayoutHass(),
  );
  assert.deepEqual(plain(compact.views.map((view) => view.path)), [
    "speicher",
    "energie",
    "einstellungen",
    "laden",
    "feinabstimmung",
  ]);
  assert.ok(compact.views[1].sections
    .flatMap((section) => section.cards)
    .some((card) => card.type === "power-sankey"));
  assert.equal(compact.views[1].badges[0].type, "power-total");
  assert.equal(compact.views[1].badges[1].entity, "sensor.xt500_soc");

  const hidden = await Strategy.generate(
    { energy_views_mode: "hidden" },
    createLayoutHass(),
  );
  assert.deepEqual(plain(hidden.views.map((view) => view.path)), [
    "speicher",
    "einstellungen",
    "laden",
    "feinabstimmung",
  ]);
});

test("zeigt Reserve und automatische Wiederfreigabe ohne eigene Hysterese", async () => {
  const hass = createLayoutHass();
  for (const key of ["reserve_enabled", "reserve_soc", "reserve_release_soc", "reserve_hold"]) {
    hass.states[`sensor.test_${key}`] = {state: "40", attributes: {
      integration: "xt500_energy_manager", xt500_manager_id: "manager-1", xt500_key: key,
    }};
  }
  const result = await Strategy.generate({}, hass);
  const serialized = JSON.stringify(result);
  for (const key of ["reserve_enabled", "reserve_soc", "reserve_release_soc", "reserve_hold"]) {
    assert.ok(serialized.includes(`sensor.test_${key}`));
  }
  assert.ok(!serialized.includes("reserve_hysteresis"));
});

test("verwendet die automatisch gewählte Dashboard-Adresse auch für Unterseiten", async () => {
  const result = await Strategy.generate({dashboard_path: "xt500-energiemanager-2"}, createLayoutHass());
  const settings = result.views.find(view => view.path === "einstellungen");
  const serialized = JSON.stringify(settings);
  assert.ok(serialized.includes("/xt500-energiemanager-2/laden"));
  assert.ok(serialized.includes("/xt500-energiemanager-2/feinabstimmung"));
  for (const path of ["laden", "feinabstimmung"]) {
    assert.equal(result.views.find(view => view.path === path).back_path, "/xt500-energiemanager-2/einstellungen");
  }
});
