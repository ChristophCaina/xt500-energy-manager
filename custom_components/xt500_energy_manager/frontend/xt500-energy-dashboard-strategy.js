const XT500_DISPLAY_NAMES = {
  status: "Status",
  recovery_status: "Fehlerwiederherstellung",
  selected_mode: "Ausgewählter Lademodus",
  active_mode: "Aktiver Lademodus",
  active_operation: "Aktiver Vorgang",
  mode_state: "Zustand des Lademodus",
  selected_coupling_mode: "Gewählte PV-Berücksichtigung",
  active_coupling_mode: "Aktuell nutzbare PV-Quelle",
  active_energy_source: "Tatsächliche Ladequelle",
  data_valid: "Eingangsdaten",
  control_ready: "Produktivregelung",
  discharge_hold: "Entladesperre aktiv",
  discharge_override_active: "Temporäre Entladefreigabe aktiv",
  charge_request: "Ladeanforderung",
  tariff_request: "Tarif-Ladeanforderung",
  tariff_expires_at: "Tarifanforderung gültig bis",
  recommended_grid_setpoint: "Netzanschluss-Sollwert",
  recommended_inverter_setpoint: "Wechselrichter-Obergrenze",
  desired_charge_limit: "System-Ladegrenze",
  estimated_home_load: "Hausverbrauch (geschätzt)",
  control_band: "Regelstufe",
  control_error: "Regelabweichung",
  control_interval: "Aktiver Regelabstand",
  control_max_step: "Aktive maximale Änderung",
  pv_release_active: "DC-PV-Freigabe",
  ac_pv_release_active: "AC-PV-Freigabe",
  ac_pv_input_valid: "AC-PV-Sensor",
  ac_pv_power: "Externe AC-PV-Erzeugung",
  available_ac_surplus: "AC-PV-Überschuss am Netzanschluss",
  active_target_soc: "Aktives Ladeziel",
  cycle_state: "Zyklusstatus",
  cycle_charge_active: "Zyklusladung aktiv",
  cycle_due: "Zyklus fällig",
  cycle_check_time: "Tägliche Prüfzeit",
  days_since_full: "Tage im aktuellen Zyklus",
  next_cycle_at: "Nächste Zyklusladung",
  battery_charge_power: "Batterie lädt",
  battery_discharge_power: "Batterie entlädt",
  pv_surplus_correction: "PV-Überschuss-Abregelung",
  full_charge_confirmation: "Bestätigung der Vollladung",
};

const XT500_DISPLAY_ICONS = {
  active_target_soc: "mdi:battery-charging",
  discharge_hold: "mdi:battery-lock",
  discharge_override_active: "mdi:battery-unlock",
};

const XT500_STRATEGY_TYPE = "custom:xt500-energy-manager";
const XT500_ENERGY_COLLECTION = "energy_xt500_manager";
const XT500_LIVE_ENERGY_COLLECTION = "energy_xt500_manager_live";
const XT500_ENERGY_VIEW_MODES = new Set(["detailed", "compact", "hidden"]);

const XT500_DASHBOARD_BLOCKS = {
  overview: [
    { key: "storage", label: "Speicherstand" },
    { key: "regulation_status", label: "Regelungsstatus" },
    { key: "quick_controls", label: "Schnellsteuerung" },
    { key: "flows", label: "Aktuelle Leistungsflüsse" },
    { key: "energy_today", label: "Energie heute" },
    { key: "cycle", label: "Zyklusladung" },
    { key: "setpoints", label: "Sollwerte und Berechnung" },
  ],
  settings: [
    { key: "guide", label: "Bedienung und Sicherheit" },
    { key: "main_control", label: "Hauptsteuerung" },
    { key: "target_charge", label: "Zielladung und Zyklusladung" },
    { key: "tariff_charge", label: "Dynamischer Stromtarif" },
    { key: "normal_limits", label: "Normalbetrieb und Grenzen" },
    { key: "advanced", label: "Feinabstimmung" },
  ],
};

const cloneConfig = (value) => JSON.parse(JSON.stringify(value));

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const sourceViewKey = (view, index) =>
  view.path ? `path:${view.path}` : `index:${index}`;

const blockConfigKey = (page, suffix) => `${page}_block_${suffix}`;

const normalizedBlockOrder = (config, page) => {
  const knownKeys = XT500_DASHBOARD_BLOCKS[page].map((block) => block.key);
  const configured = Array.isArray(config?.[blockConfigKey(page, "order")])
    ? config[blockConfigKey(page, "order")]
    : [];
  return [
    ...configured.filter(
      (key, index) => knownKeys.includes(key) && configured.indexOf(key) === index,
    ),
    ...knownKeys.filter((key) => !configured.includes(key)),
  ];
};

const normalizedHiddenBlocks = (config, page) => {
  const knownKeys = new Set(
    XT500_DASHBOARD_BLOCKS[page].map((block) => block.key),
  );
  const configured = Array.isArray(config?.[blockConfigKey(page, "hidden")])
    ? config[blockConfigKey(page, "hidden")]
    : [];
  return configured.filter(
    (key, index) => knownKeys.has(key) && configured.indexOf(key) === index,
  );
};

const orderedVisibleBlocks = (config, page, blocks) => {
  const hidden = new Set(normalizedHiddenBlocks(config, page));
  return normalizedBlockOrder(config, page)
    .filter((key) => !hidden.has(key) && blocks[key])
    .flatMap((key) => Array.isArray(blocks[key]) ? blocks[key] : [blocks[key]]);
};

const additionalViewPath = (entry, sourceView, usedPaths) => {
  const rawPath = [
    "zusatz",
    entry.source_dashboard,
    sourceView.path || entry.source_view,
  ]
    .join("-")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "zusatzansicht";
  let path = rawPath;
  let suffix = 2;
  while (usedPaths.has(path)) {
    path = `${rawPath}-${suffix}`;
    suffix += 1;
  }
  usedPaths.add(path);
  return path;
};

const loadAdditionalViews = async (config, hass, existingViews) => {
  const entries = Array.isArray(config.additional_views)
    ? config.additional_views
    : [];
  if (!entries.length || typeof hass.callWS !== "function") return [];

  const dashboardRequests = new Map();
  const usedSources = new Set();
  const usedPaths = new Set(existingViews.map((view) => view.path).filter(Boolean));
  const importedViews = [];

  for (const entry of entries) {
    if (!entry?.source_dashboard || !entry?.source_view) continue;
    const sourceId = `${entry.source_dashboard}|${entry.source_view}`;
    if (usedSources.has(sourceId)) continue;
    usedSources.add(sourceId);

    try {
      if (!dashboardRequests.has(entry.source_dashboard)) {
        dashboardRequests.set(
          entry.source_dashboard,
          hass.callWS({
            type: "lovelace/config",
            url_path: entry.source_dashboard,
          }),
        );
      }
      const sourceDashboard = await dashboardRequests.get(entry.source_dashboard);
      if (
        sourceDashboard?.strategy?.type === XT500_STRATEGY_TYPE ||
        !Array.isArray(sourceDashboard?.views)
      ) {
        continue;
      }
      const sourceIndex = sourceDashboard.views.findIndex(
        (view, index) => sourceViewKey(view, index) === entry.source_view,
      );
      if (sourceIndex < 0) continue;
      const sourceView = sourceDashboard.views[sourceIndex];
      if (sourceView?.strategy) continue;

      const importedView = cloneConfig(sourceView);
      importedView.title = entry.title?.trim() || sourceView.title || "Zusatzansicht";
      importedView.icon = entry.icon?.trim() || sourceView.icon || "mdi:view-dashboard-outline";
      importedView.path = additionalViewPath(entry, sourceView, usedPaths);
      importedView.subview = false;
      delete importedView.back_path;
      if (entry.visibility === "user" && entry.user_id) {
        importedView.visible = [{ user: entry.user_id }];
      }
      importedViews.push(importedView);
    } catch (_error) {
      // Eine nicht erreichbare Zusatzansicht darf die Energiemanager-Regelung
      // und ihre beiden eigenen Ansichten nicht unbenutzbar machen.
    }
  }
  return importedViews;
};

const normalizedEnergyViewMode = (config) =>
  XT500_ENERGY_VIEW_MODES.has(config?.energy_views_mode)
    ? config.energy_views_mode
    : "detailed";

const energyCard = (type, options = {}, gridOptions = null) => ({
  type,
  collection_key: XT500_ENERGY_COLLECTION,
  ...options,
  ...(gridOptions ? { grid_options: gridOptions } : {}),
});

const energyHeading = (heading, icon) => ({
  type: "heading",
  heading,
  icon,
});

const energyDateSection = () => ({
  type: "grid",
  column_span: 3,
  cards: [
    energyHeading("Zeitraum und Vergleich", "mdi:calendar-range"),
    energyCard(
      "energy-date-selection",
      { opening_direction: "auto", vertical_opening_direction: "auto" },
      { columns: "full", rows: "auto" },
    ),
  ],
});

const detailedEnergyViews = (socEntities = []) => [
  {
    title: "Energie",
    path: "energie",
    icon: "mdi:lightning-bolt",
    type: "sections",
    max_columns: 3,
    sections: [
      energyDateSection(),
      {
        type: "grid",
        cards: [
          energyHeading("Energiefluss", "mdi:transmission-tower"),
          energyCard(
            "energy-distribution",
            { title: "Energieverteilung", link_dashboard: false },
            { columns: "full", rows: "auto" },
          ),
          energyCard(
            "energy-grid-balance",
            {},
            { columns: "full", rows: "auto" },
          ),
        ],
      },
      {
        type: "grid",
        cards: [
          energyHeading("Bilanz", "mdi:chart-donut"),
          energyCard(
            "energy-grid-neutrality-gauge",
            {},
            { columns: 6, rows: "auto" },
          ),
          energyCard(
            "energy-solar-consumed-gauge",
            {},
            { columns: 6, rows: "auto" },
          ),
          energyCard(
            "energy-self-sufficiency-gauge",
            {},
            { columns: 6, rows: "auto" },
          ),
        ],
      },
      {
        type: "grid",
        cards: [
          energyHeading("Quellen, Speicher und Kosten", "mdi:table-large"),
          energyCard(
            "energy-sources-table",
            {},
            { columns: "full", rows: "auto" },
          ),
        ],
      },
    ],
  },
  {
    title: "Verlauf",
    path: "energie-verlauf",
    icon: "mdi:chart-areaspline",
    type: "sections",
    max_columns: 3,
    sections: [
      energyDateSection(),
      {
        type: "grid",
        column_span: 2,
        cards: [
          energyHeading("Verbrauch und Herkunft", "mdi:home-lightning-bolt"),
          energyCard(
            "energy-usage-graph",
            { title: "Hausverbrauch", show_legend: true },
            { columns: "full", rows: 7 },
          ),
          energyCard(
            "energy-solar-graph",
            { title: "PV-Erzeugung" },
            { columns: "full", rows: 6 },
          ),
        ],
      },
    ],
  },
  {
    title: "Verbraucher",
    path: "energie-verbraucher",
    icon: "mdi:home-lightning-bolt-outline",
    type: "sections",
    max_columns: 3,
    sections: [
      energyDateSection(),
      {
        type: "grid",
        column_span: 2,
        cards: [
          energyHeading("Energiefluss zu den Verbrauchern", "mdi:sitemap"),
          energyCard(
            "energy-sankey",
            {
              title: "Energie-Sankey",
              layout: "auto",
              group_by_area: true,
              group_by_floor: true,
            },
            { columns: "full", rows: 8 },
          ),
        ],
      },
      {
        type: "grid",
        cards: [
          energyHeading("Größte Verbraucher", "mdi:sort-descending"),
          energyCard(
            "energy-devices-graph",
            { title: "Verbrauch nach Gerät", hide_compound_stats: false },
            { columns: "full", rows: 8 },
          ),
        ],
      },
      {
        type: "grid",
        column_span: 3,
        cards: [
          energyHeading("Verbraucher im Zeitverlauf", "mdi:chart-timeline-variant"),
          energyCard(
            "energy-devices-detail-graph",
            { title: "Detaillierter Geräteverbrauch" },
            { columns: "full", rows: 8 },
          ),
        ],
      },
    ],
  },
  {
    title: "Live",
    path: "energie-live",
    icon: "mdi:flash",
    type: "sections",
    max_columns: 3,
    badges: [
      {
        type: "power-total",
        collection_key: XT500_LIVE_ENERGY_COLLECTION,
      },
      ...socEntities.map((entity) => ({
        type: "entity",
        entity,
        show_name: false,
        show_icon: true,
        show_state: true,
      })),
    ],
    sections: [
      {
        type: "grid",
        cards: [
          energyHeading("Stromquellen", "mdi:chart-line"),
          energyCard(
            "power-sources-graph",
            {
              collection_key: XT500_LIVE_ENERGY_COLLECTION,
              title: "Leistung nach Quelle",
              show_legend: true,
            },
            { columns: "full", rows: 7 },
          ),
        ],
      },
      {
        type: "grid",
        column_span: 2,
        cards: [
          energyHeading("Aktueller Leistungsfluss", "mdi:transmission-tower"),
          energyCard(
            "power-sankey",
            {
              collection_key: XT500_LIVE_ENERGY_COLLECTION,
              title: "Aktueller Leistungsfluss",
              layout: "auto",
              group_by_area: true,
              group_by_floor: true,
            },
            { columns: "full", rows: 8 },
          ),
        ],
      },
    ],
  },
];

const compactEnergyView = (socEntities) => {
  const [overview, history, consumers, live] = detailedEnergyViews(socEntities);
  return {
    title: "Energie",
    path: "energie",
    icon: "mdi:lightning-bolt",
    type: "sections",
    max_columns: 3,
    badges: live.badges,
    sections: [
      energyDateSection(),
      ...overview.sections.slice(1),
      history.sections[1],
      consumers.sections[2],
      ...live.sections,
    ],
  };
};

const energyViews = (config, socEntities = []) => {
  const mode = normalizedEnergyViewMode(config);
  if (mode === "hidden") return [];
  return mode === "compact"
    ? [compactEnergyView(socEntities)]
    : detailedEnergyViews(socEntities);
};

class XT500EnergyManagerStrategyEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._dashboards = [];
    this._viewsByDashboard = new Map();
    this._loadingDashboards = false;
    this._dashboardError = "";
  }

  set hass(hass) {
    const firstConnection = !this._hass;
    this._hass = hass;
    if (firstConnection) this._loadDashboards();
  }

  setConfig(config) {
    this._config = cloneConfig(config || {});
    this._config.energy_views_mode = normalizedEnergyViewMode(this._config);
    if (!Array.isArray(this._config.additional_views)) {
      this._config.additional_views = [];
    }
    for (const page of Object.keys(XT500_DASHBOARD_BLOCKS)) {
      this._config[blockConfigKey(page, "order")] =
        normalizedBlockOrder(this._config, page);
      this._config[blockConfigKey(page, "hidden")] =
        normalizedHiddenBlocks(this._config, page);
    }
    this._render();
    for (const entry of this._config.additional_views) {
      if (entry.source_dashboard) this._loadViews(entry.source_dashboard);
    }
  }

  async _loadDashboards() {
    if (!this._hass || this._loadingDashboards) return;
    this._loadingDashboards = true;
    this._dashboardError = "";
    this._render();
    try {
      const dashboards = await this._hass.callWS({
        type: "lovelace/dashboards/list",
      });
      this._dashboards = (Array.isArray(dashboards) ? dashboards : [])
        .filter((dashboard) =>
          dashboard.mode === "storage" && dashboard.url_path,
        )
        .sort((left, right) =>
          (left.title || left.url_path).localeCompare(
            right.title || right.url_path,
            "de",
          ),
        );
    } catch (_error) {
      this._dashboardError = "Dashboards konnten nicht geladen werden.";
    } finally {
      this._loadingDashboards = false;
      this._render();
      for (const entry of this._config.additional_views) {
        if (entry.source_dashboard) this._loadViews(entry.source_dashboard);
      }
    }
  }

  async _loadViews(dashboardPath) {
    if (
      !this._hass ||
      !dashboardPath ||
      this._viewsByDashboard.has(dashboardPath)
    ) {
      return;
    }
    this._viewsByDashboard.set(dashboardPath, { loading: true, views: [] });
    this._render();
    try {
      const dashboard = await this._hass.callWS({
        type: "lovelace/config",
        url_path: dashboardPath,
      });
      if (dashboard?.strategy?.type === XT500_STRATEGY_TYPE) {
        this._viewsByDashboard.set(dashboardPath, {
          loading: false,
          views: [],
          error: "Ein Energiemanager-Strategie-Dashboard kann nicht selbst eingebunden werden.",
        });
      } else {
        const views = (Array.isArray(dashboard?.views) ? dashboard.views : [])
          .map((view, index) => ({
            key: sourceViewKey(view, index),
            title: view.title || view.path || `Ansicht ${index + 1}`,
            importable: !view.strategy,
          }))
          .filter((view) => view.importable);
        this._viewsByDashboard.set(dashboardPath, {
          loading: false,
          views,
          error: views.length ? "" : "Dieses Dashboard enthält keine direkt einbindbare Ansicht.",
        });
      }
    } catch (_error) {
      this._viewsByDashboard.set(dashboardPath, {
        loading: false,
        views: [],
        error: "Ansichten konnten nicht geladen werden.",
      });
    }
    this._render();
  }

  _changed() {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: cloneConfig(this._config) },
      bubbles: true,
      composed: true,
    }));
  }

  _addView() {
    this._config.additional_views.push({
      source_dashboard: "",
      source_view: "",
      title: "",
      icon: "",
      visibility: "all",
    });
    this._changed();
    this._render();
  }

  _removeView(index) {
    this._config.additional_views.splice(index, 1);
    this._changed();
    this._render();
  }

  _setValue(index, field, value) {
    const entry = this._config.additional_views[index];
    if (!entry) return;
    entry[field] = value;
    if (field === "source_dashboard") {
      entry.source_view = "";
      this._loadViews(value);
    }
    if (field === "visibility") {
      if (value === "user" && this._hass?.user?.id) {
        entry.user_id = this._hass.user.id;
      } else {
        delete entry.user_id;
      }
    }
    this._changed();
    this._render();
  }

  _setEnergyViewMode(value) {
    this._config.energy_views_mode = XT500_ENERGY_VIEW_MODES.has(value)
      ? value
      : "detailed";
    this._changed();
    this._render();
  }

  _moveBlock(page, key, direction) {
    const orderKey = blockConfigKey(page, "order");
    const order = normalizedBlockOrder(this._config, page);
    const currentIndex = order.indexOf(key);
    const targetIndex = currentIndex + direction;
    if (
      currentIndex < 0 ||
      targetIndex < 0 ||
      targetIndex >= order.length
    ) {
      return;
    }
    [order[currentIndex], order[targetIndex]] =
      [order[targetIndex], order[currentIndex]];
    this._config[orderKey] = order;
    this._changed();
    this._render();
  }

  _setBlockVisible(page, key, visible) {
    const hiddenKey = blockConfigKey(page, "hidden");
    const hidden = new Set(normalizedHiddenBlocks(this._config, page));
    if (visible) {
      hidden.delete(key);
    } else {
      hidden.add(key);
    }
    this._config[hiddenKey] = [...hidden];
    this._changed();
    this._render();
  }

  _resetBlockLayout(page) {
    this._config[blockConfigKey(page, "order")] =
      XT500_DASHBOARD_BLOCKS[page].map((block) => block.key);
    this._config[blockConfigKey(page, "hidden")] = [];
    this._changed();
    this._render();
  }

  _blockEditor(page, title) {
    const order = normalizedBlockOrder(this._config, page);
    const hidden = new Set(normalizedHiddenBlocks(this._config, page));
    const labels = new Map(
      XT500_DASHBOARD_BLOCKS[page].map((block) => [block.key, block.label]),
    );
    const rows = order.map((key, index) => `
      <div class="block-row">
        <label class="block-visible">
          <input
            type="checkbox"
            data-block-visible="${escapeHtml(key)}"
            data-block-page="${escapeHtml(page)}"
            ${hidden.has(key) ? "" : "checked"}
          >
          <span>${escapeHtml(labels.get(key) || key)}</span>
        </label>
        <div class="block-actions">
          <button
            type="button"
            class="move"
            data-block-move="-1"
            data-block-key="${escapeHtml(key)}"
            data-block-page="${escapeHtml(page)}"
            aria-label="${escapeHtml(labels.get(key) || key)} nach oben"
            ${index === 0 ? "disabled" : ""}
          >↑</button>
          <button
            type="button"
            class="move"
            data-block-move="1"
            data-block-key="${escapeHtml(key)}"
            data-block-page="${escapeHtml(page)}"
            aria-label="${escapeHtml(labels.get(key) || key)} nach unten"
            ${index === order.length - 1 ? "disabled" : ""}
          >↓</button>
        </div>
      </div>
    `).join("");
    return `
      <section class="entry block-editor">
        <div class="entry-heading">
          <strong>${escapeHtml(title)}</strong>
          <button
            type="button"
            class="reset"
            data-block-reset="${escapeHtml(page)}"
          >Standard wiederherstellen</button>
        </div>
        <p class="hint">Haken entfernt einen Block aus der Ansicht. Mit den Pfeilen änderst du seine Position.</p>
        ${rows}
      </section>
    `;
  }

  _dashboardOptions(selected) {
    const options = [
      '<option value="">Dashboard auswählen</option>',
      ...this._dashboards.map((dashboard) => {
        const value = escapeHtml(dashboard.url_path);
        const label = escapeHtml(dashboard.title || dashboard.url_path);
        return `<option value="${value}"${dashboard.url_path === selected ? " selected" : ""}>${label}</option>`;
      }),
    ];
    return options.join("");
  }

  _viewOptions(entry) {
    const state = this._viewsByDashboard.get(entry.source_dashboard);
    const placeholder = state?.loading
      ? "Ansichten werden geladen …"
      : "Ansicht auswählen";
    const options = [
      `<option value="">${placeholder}</option>`,
      ...(state?.views || []).map((view) =>
        `<option value="${escapeHtml(view.key)}"${view.key === entry.source_view ? " selected" : ""}>${escapeHtml(view.title)}</option>`,
      ),
    ];
    return options.join("");
  }

  _render() {
    if (!this.shadowRoot) return;
    const entries = this._config.additional_views || [];
    const cards = entries.map((entry, index) => {
      const viewState = this._viewsByDashboard.get(entry.source_dashboard);
      return `
        <section class="entry">
          <div class="entry-heading">
            <strong>Zusätzliche Ansicht ${index + 1}</strong>
            <button class="remove" data-remove="${index}" type="button" aria-label="Zusätzliche Ansicht entfernen">
              Entfernen
            </button>
          </div>
          <label>
            Quell-Dashboard
            <select data-index="${index}" data-field="source_dashboard">
              ${this._dashboardOptions(entry.source_dashboard)}
            </select>
          </label>
          <label>
            Quell-Ansicht
            <select data-index="${index}" data-field="source_view"${!entry.source_dashboard || viewState?.loading ? " disabled" : ""}>
              ${this._viewOptions(entry)}
            </select>
          </label>
          ${viewState?.error ? `<p class="error">${escapeHtml(viewState.error)}</p>` : ""}
          <div class="two-columns">
            <label>
              Titel im Energiemanager
              <input data-index="${index}" data-field="title" value="${escapeHtml(entry.title)}" placeholder="Titel der Quellansicht">
            </label>
            <label>
              Symbol
              <input data-index="${index}" data-field="icon" value="${escapeHtml(entry.icon)}" placeholder="z. B. mdi:solar-power">
            </label>
          </div>
          <label>
            Sichtbarkeit
            <select data-index="${index}" data-field="visibility">
              <option value="all"${entry.visibility !== "user" ? " selected" : ""}>Für alle berechtigten Benutzer</option>
              <option value="user"${entry.visibility === "user" ? " selected" : ""}>Nur für mich</option>
            </select>
          </label>
          <p class="hint">Vorhandene Benutzerbeschränkungen der Quellansicht bleiben erhalten. „Nur für mich“ schränkt sie zusätzlich auf dein Benutzerkonto ein.</p>
        </section>
      `;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          color: var(--primary-text-color);
        }
        .intro, .hint, .empty {
          color: var(--secondary-text-color);
          line-height: 1.45;
        }
        .entry {
          margin: 16px 0;
          padding: 16px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          background: var(--card-background-color);
        }
        .entry-heading {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 14px;
        }
        label {
          display: grid;
          gap: 6px;
          margin: 12px 0;
          font-size: 14px;
        }
        select, input:not([type="checkbox"]), button {
          box-sizing: border-box;
          min-height: 44px;
          padding: 10px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          color: var(--primary-text-color);
          background: var(--card-background-color);
          font: inherit;
        }
        select, input:not([type="checkbox"]) {
          width: 100%;
        }
        button {
          cursor: pointer;
        }
        .add {
          color: var(--primary-color);
          border-color: var(--primary-color);
          background: transparent;
          font-weight: 600;
        }
        .remove {
          min-height: 36px;
          padding: 6px 10px;
          color: var(--error-color);
          background: transparent;
        }
        .reset {
          min-height: 36px;
          padding: 6px 10px;
          color: var(--primary-color);
          background: transparent;
        }
        .block-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-height: 52px;
          border-top: 1px solid var(--divider-color);
        }
        .block-visible {
          display: flex;
          align-items: center;
          gap: 10px;
          flex: 1;
          margin: 0;
          cursor: pointer;
        }
        .block-visible input {
          width: 20px;
          height: 20px;
          accent-color: var(--primary-color);
        }
        .block-actions {
          display: flex;
          gap: 6px;
        }
        .move {
          min-width: 42px;
          min-height: 36px;
          padding: 6px 10px;
          font-size: 18px;
          background: transparent;
        }
        .move:disabled {
          opacity: 0.35;
          cursor: default;
        }
        .two-columns {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .hint {
          margin: 8px 0 0;
          font-size: 13px;
        }
        .error {
          color: var(--error-color);
        }
        @media (max-width: 600px) {
          .two-columns {
            grid-template-columns: 1fr;
            gap: 0;
          }
        }
      </style>
      <h3>Aufbau der Energiemanager-Seiten</h3>
      <p class="intro">Lege fest, in welcher Reihenfolge die einzelnen Blöcke erscheinen. Die Anordnung wird auf schmalen Bildschirmen von oben nach unten und auf breiten Bildschirmen im Home-Assistant-Raster verwendet.</p>
      ${this._blockEditor("overview", "Seite „Speicher“")}
      ${this._blockEditor("settings", "Seite „Einstellungen“")}
      <h3>Energie-Dashboard</h3>
      <p class="intro">Die originalen Home-Assistant-Energiekarten verwenden direkt die unter „Energie“ eingerichteten Quellen. Datum und Vergleichszeitraum bleiben über alle erzeugten Energiereiter synchron.</p>
      <section class="entry">
        <label>
          Energieseiten anzeigen
          <select data-energy-view-mode>
            <option value="detailed"${normalizedEnergyViewMode(this._config) === "detailed" ? " selected" : ""}>Ausführlich – vier Reiter</option>
            <option value="compact"${normalizedEnergyViewMode(this._config) === "compact" ? " selected" : ""}>Kompakt – ein Reiter</option>
            <option value="hidden"${normalizedEnergyViewMode(this._config) === "hidden" ? " selected" : ""}>Nicht anzeigen</option>
          </select>
        </label>
        <p class="hint">Ausführlich erzeugt „Energie“, „Verlauf“, „Verbraucher“ und „Live“. Nicht konfigurierte Energie- oder Leistungsquellen bleiben in den Home-Assistant-Karten leer.</p>
      </section>
      <h3>Zusätzliche Dashboard-Ansichten</h3>
      <p class="intro">Binde einzelne Seiten aus anderen, in Home Assistant gespeicherten Dashboards als echte Reiter ein. Änderungen an der Quellseite werden nach einem Neuladen automatisch übernommen.</p>
      ${this._loadingDashboards ? '<p class="empty">Dashboards werden geladen …</p>' : ""}
      ${this._dashboardError ? `<p class="error">${escapeHtml(this._dashboardError)}</p>` : ""}
      ${cards || '<p class="empty">Noch keine zusätzliche Ansicht eingerichtet.</p>'}
      <button class="add" type="button">Ansicht hinzufügen</button>
    `;

    this.shadowRoot.querySelector(".add")?.addEventListener(
      "click",
      () => this._addView(),
    );
    this.shadowRoot.querySelector("[data-energy-view-mode]")?.addEventListener(
      "change",
      (event) => this._setEnergyViewMode(event.target.value),
    );
    for (const button of this.shadowRoot.querySelectorAll("[data-remove]")) {
      button.addEventListener("click", () =>
        this._removeView(Number(button.dataset.remove)),
      );
    }
    for (const input of this.shadowRoot.querySelectorAll("[data-field]")) {
      input.addEventListener("change", () =>
        this._setValue(
          Number(input.dataset.index),
          input.dataset.field,
          input.value,
        ),
      );
    }
    for (const button of this.shadowRoot.querySelectorAll("[data-block-move]")) {
      button.addEventListener("click", () =>
        this._moveBlock(
          button.dataset.blockPage,
          button.dataset.blockKey,
          Number(button.dataset.blockMove),
        ),
      );
    }
    for (const input of this.shadowRoot.querySelectorAll("[data-block-visible]")) {
      input.addEventListener("change", () =>
        this._setBlockVisible(
          input.dataset.blockPage,
          input.dataset.blockVisible,
          input.checked,
        ),
      );
    }
    for (const button of this.shadowRoot.querySelectorAll("[data-block-reset]")) {
      button.addEventListener("click", () =>
        this._resetBlockLayout(button.dataset.blockReset),
      );
    }
  }
}

class XT500EnergyManagerDashboardStrategy extends HTMLElement {
  static getCreateSuggestions(_hass) {
    return { title: "XT500 Energiemanager", icon: "mdi:home-battery" };
  }

  static getConfigElement() {
    return document.createElement("xt500-energy-manager-strategy-editor");
  }

  static async generate(config, hass) {
    const dashboardPath = config.dashboard_path || "xt500-energiemanager";
    const managers = new Map();
    for (const [entityId, state] of Object.entries(hass.states)) {
      if (state.attributes.integration !== "xt500_energy_manager") continue;
      const managerId = state.attributes.xt500_manager_id || "default";
      if (!managers.has(managerId)) managers.set(managerId, {});
      managers.get(managerId)[state.attributes.xt500_key] = entityId;
    }

    if (managers.size === 0) {
      return {
        title: config.title || "XT500 Energiemanager",
        views: [{
          title: "Einrichtung",
          path: "setup",
          icon: "mdi:home-battery",
          cards: [{
            type: "markdown",
            title: "Noch kein XT500 eingerichtet",
            content: "Richte zuerst **XT500 Energy Manager** unter Einstellungen → Geräte & Dienste ein. Das Dashboard aktualisiert sich danach automatisch.",
          }],
        }],
      };
    }

    const views = [];
    const settingsViews = [];
    const socEntities = [];
    let index = 0;
    for (const entities of managers.values()) {
      index += 1;
      const sourceAttributes = hass.states[entities.status]?.attributes || {};
      const socEntity = sourceAttributes.source_soc_entity;
      if (
        socEntity &&
        hass.states[socEntity] &&
        !socEntities.includes(socEntity)
      ) {
        socEntities.push(socEntity);
      }
      const actualGridSetpoint = sourceAttributes.source_grid_setpoint_entity;
      const actualChargeLimit = sourceAttributes.source_max_charge_soc_entity;
      const actualLoadDischargeLimit =
        sourceAttributes.source_load_discharge_limit_entity;
      const existing = (keys) => keys.map((key) => entities[key]).filter(Boolean);
      const namedExisting = (keys) => keys
        .filter((key) => entities[key])
        .map((key) => ({
          entity: entities[key],
          name: XT500_DISPLAY_NAMES[key] || key,
          ...(XT500_DISPLAY_ICONS[key] ? { icon: XT500_DISPLAY_ICONS[key] } : {}),
          ...(key === "next_cycle_at" ? { format: "datetime" } : {}),
        }));
      const heading = (text, icon) => ({ type: "heading", heading: text, icon });
      const tile = (key, name, features = []) => entities[key] ? {
        type: "tile",
        entity: entities[key],
        name,
        features,
        grid_options: { columns: "full", rows: "auto" },
      } : null;
      const compact = (cards) => cards.filter(Boolean);
      const settingRows = (items) => items
        .map(([keyOrEntity, name, icon]) => {
          const entityId = entities[keyOrEntity] || keyOrEntity;
          return entityId && hass.states[entityId] ? {
            entity: entityId,
            name,
            ...(icon ? { icon } : {}),
          } : null;
        })
        .filter(Boolean);
      const compactSettingGroup = (title, icon, items, extraCards = []) => {
        const rows = settingRows(items);
        return compact([
          heading(title, icon),
          rows.length ? {
            type: "entities",
            show_header_toggle: false,
            entities: rows,
          } : null,
          ...extraCards,
        ]);
      };
      const compactOverviewTile = (entityId, name, icon) =>
        entityId && hass.states[entityId] ? {
          type: "tile",
          entity: entityId,
          name,
          ...(icon ? { icon } : {}),
          grid_options: { columns: 6, rows: "auto" },
        } : null;

      const regulationStatusEntities = namedExisting([
        "status", "active_operation", "selected_mode", "active_mode", "mode_state",
        "selected_coupling_mode", "active_coupling_mode", "active_energy_source",
        "active_target_soc", "discharge_hold", "discharge_override_active",
        "control_ready", "recovery_status", "data_valid",
      ]);
      const setpointEntities = namedExisting(["desired_charge_limit"]);
      if (actualGridSetpoint && hass.states[actualGridSetpoint]) {
        setpointEntities.push({ entity: actualGridSetpoint, name: "Netz-Sollwert am Gerät" });
      }
      if (actualChargeLimit && hass.states[actualChargeLimit]) {
        setpointEntities.push({ entity: actualChargeLimit, name: "System-Ladegrenze am Gerät" });
      }
      setpointEntities.push(...namedExisting([
        "recommended_grid_setpoint",
        "recommended_inverter_setpoint",
        "pv_surplus_correction",
        "estimated_home_load",
      ]));
      const cycleEntities = namedExisting([
        "cycle_state",
        "full_charge_confirmation",
        "days_since_full",
        "next_cycle_at",
      ]);
      const selectedCouplingMode = entities.coupling_mode
        ? hass.states[entities.coupling_mode]?.state
        : undefined;
      const acPvIsSelected = selectedCouplingMode !== "dc";

      const flowEntities = [
        [entities.battery_charge_power, "Akku lädt"],
        [entities.battery_discharge_power, "Akku entlädt"],
        [sourceAttributes.source_pv_power_entity, "XT500-PV-Erzeugung (DC)"],
        [acPvIsSelected && sourceAttributes.source_ac_pv_power_entity ? entities.ac_pv_power : null, "Externe AC-PV-Erzeugung"],
        [acPvIsSelected ? entities.available_ac_surplus : null, "AC-PV-Überschuss am Netzanschluss"],
        [sourceAttributes.source_public_grid_power_entity, "Netzleistung"],
        [sourceAttributes.source_grid_port_power_entity, "XT500 Netz"],
        [sourceAttributes.source_load_port_power_entity, "XT500 Last"],
      ]
        .filter(([entityId]) => entityId && hass.states[entityId])
        .map(([entityId, name]) => ({ entity: entityId, name }));
      const flowTiles = flowEntities.map(({ entity, name }) =>
        compactOverviewTile(entity, name)
      );
      const dailyEnergyTiles = compact([
        compactOverviewTile(
          sourceAttributes.source_pv_daily_energy_entity,
          "XT500-PV heute",
          "mdi:solar-power",
        ),
        compactOverviewTile(
          sourceAttributes.source_grid_charge_daily_energy_entity,
          "Netzladung",
          "mdi:battery-charging",
        ),
        compactOverviewTile(
          sourceAttributes.source_grid_export_daily_energy_entity,
          "Einspeisung",
          "mdi:transmission-tower-export",
        ),
        compactOverviewTile(
          sourceAttributes.source_offgrid_daily_energy_entity,
          "Off-Grid",
          "mdi:power-plug-battery-outline",
        ),
      ]);

      const mainControlCards = compactSettingGroup("Hauptsteuerung", "mdi:power", [
        ["regulation_enabled", "Regelung aktiv"],
        ["automatic_recovery_enabled", "Fehler automatisch beheben"],
      ]);
      const manualChargeCards = compactSettingGroup("Manuelle Zielladung", "mdi:battery-arrow-up", [
        ["manual_active", "Zielladung starten"],
        ["manual_mode", "Lademodus"],
        ["target_soc", "Ladeziel"],
        ["charge_power", "Gewünschte Ladeleistung"],
      ]);
      const cycleChargeCards = compactSettingGroup("Zyklusladung", "mdi:battery-sync", [
        ["automatic_enabled", "Automatische Zyklusüberwachung"],
        ["cycle_check_time", "Tägliche Prüfzeit", "mdi:clock-check-outline"],
        ["automatic_mode", "Lademodus der Zyklusladung"],
        ["automatic_target_soc", "Vollladeziel"],
        ["cycle_interval_days", "Intervall in Tagen"],
      ], compact([
        tile("cycle_start", "Jetzt manuell starten", [{ type: "button" }]),
        tile("cycle_reset", "Zyklustage auf 0 setzen", [{ type: "button" }]),
      ]));
      const normalOperationCards = compactSettingGroup("Betriebsart und Netzziel", "mdi:tune-variant", [
        ["coupling_mode", "PV für Regelung berücksichtigen"],
        ["base_mode", "Grundmodus"],
        ["normal_charge_limit", "Ladelimit Normalbetrieb"],
        ["full_battery_pv_export", "PV-Überschuss bei vollem Akku einspeisen"],
        ["pv_surplus_deadband", "Netzeinspeisungs-Totzone"],
        ["pv_surplus_charge_reserve", "Bevorzugte Akku-Ladeleistung im PV-Überschussmodus"],
        ["target_grid_power", "Netzziel"],
        ["maximum_grid_output", "Hausnetz-Limit"],
      ]);
      const batteryProtectionCards = compactSettingGroup("Batteriegrenzen und Schutz", "mdi:battery-lock", [
        ["reserve_enabled", "Reserve für Stromausfall behalten"],
        ["reserve_soc", "Reserve im Netzbetrieb (%)"],
        ["reserve_release_soc", "Entladen wieder möglich ab (%)"],
        ["reserve_hold", "Entladen für Reserve gesperrt"],
        [actualLoadDischargeLimit, "Lastanschluss-Entladegrenze"],
        ["minimum_soc", "Entladegrenze"],
        ["soc_hysteresis", "Entlade-Hysterese (SI1)"],
        ["charge_soc_hysteresis", "Lade-Hysterese (SA1)"],
      ], compact([
        tile("discharge_release", "Entladesperre einmalig freigeben", [{ type: "button" }]),
      ]));
      const tariffControlCards = compactSettingGroup("Dynamischer Stromtarif", "mdi:currency-eur", [
        ["tariff_active", "Tarifladung anfordern"],
        ["tariff_target_soc", "Ladeziel"],
        ["tariff_charge_power", "Netz-Ladeleistung"],
        ["tariff_request_duration", "Gültigkeit je Anforderung"],
        ["tariff_expires_at", "Tarifanforderung gültig bis"],
      ]);
      const adaptiveThresholdCards = compact([
        heading("Regelstatus und Abweichungen", "mdi:speedometer"),
        existing(["control_band", "control_error", "control_interval", "control_max_step"]).length ? {
          type: "entities",
          show_header_toggle: false,
          entities: namedExisting(["control_band", "control_error", "control_interval", "control_max_step"]),
        } : null,
        heading("Fehlergrenzen", "mdi:approximately-equal"),
        ...compactSettingGroup("Fehlergrenzen", "mdi:approximately-equal", [
          ["control_small_error", "Fein → Mittel"],
          ["control_large_error", "Mittel → Schnell"],
        ]).slice(1),
      ]);
      const adaptiveResponseCards = compactSettingGroup("Leistungsschritte und Reaktionszeiten", "mdi:delta", [
        ["control_small_max_step", "Schritt bei kleiner Abweichung"],
        ["control_medium_max_step", "Schritt bei mittlerer Abweichung"],
        ["control_large_max_step", "Schritt bei großer Abweichung"],
        ["control_slow_interval", "Abstand bei kleiner Abweichung"],
        ["control_medium_interval", "Abstand bei mittlerer Abweichung"],
        ["control_fast_interval", "Abstand bei großer Abweichung"],
        ["feedback_settle_time", "Wartezeit auf Messwerte"],
      ]);
      const pvRecoveryCards = compactSettingGroup("Automatische Fehlerwiederherstellung", "mdi:shield-refresh", [
        ["recovery_stability_time", "Stabile Rückmeldungen abwarten"],
        ["pv_stop_power", "PV: unterhalb sofort auf 0 W"],
        ["pv_start_power", "PV: erneut freigeben oberhalb"],
        ["pv_start_delay", "PV: Startleistung muss anliegen"],
      ]);
      const fullChargeConfirmationCards = compactSettingGroup("Bestätigung der 100-%-Vollladung", "mdi:battery-check-outline", [
        ["full_charge_min_hold_minutes", "Mindesthaltezeit bei 100 %"],
        ["full_charge_taper_power", "Ladeende-Schwelle"],
        ["full_charge_taper_minutes", "Dauer unter Ladeende-Schwelle"],
        ["full_charge_timeout_minutes", "Maximale Bestätigungszeit"],
        ["full_charge_top_off_power", "Nachladeleistung bei 100 %"],
      ]);

      let storageGauge = null;
      if (socEntity && hass.states[socEntity]) {
        storageGauge = {
          type: "gauge",
          entity: socEntity,
          name: "Speicherstand",
          min: 0,
          max: 100,
          severity: { red: 0, yellow: 20, green: 60 },
          grid_options: { columns: "full", rows: 3 },
        };
      }

      const guideCard = {
        type: "markdown",
        title: "Bedienung und Sicherheit",
        content:
          "<details><summary><b>Anleitung und Beispiele anzeigen</b></summary>\n\n" +
          "**Produktivbetrieb:** Ist **Regelung aktiv** eingeschaltet, prüft die Integration nach jedem Home-Assistant-Start zunächst fünf Sekunden lang alle Eingangsdaten. Danach schreibt sie die Netz-, Wechselrichter- und Ladegrenzen direkt auf das Gerät. Andere Automationen dürfen dieselben Sollwerte nicht gleichzeitig verändern.\n\n" +
          "**Normalbetrieb und Ladelimit**\n\n" +
          "- **PV für Regelung berücksichtigen:** Hybrid ist die empfohlene Einstellung und berücksichtigt XT500-PV sowie externe AC-PV gemeinsam. Alternativ kann die Regelung auf eine der beiden PV-Arten begrenzt werden. Der öffentliche Stromzähler bleibt in allen Fällen die Sicherheitsinstanz.\n" +
          "- **Normalbetrieb:** Der Speicher gleicht den Hausverbrauch aus und hält das eingestellte Netzziel ein. Oberhalb der Entladegrenze darf er Energie ins Haus abgeben.\n" +
          "- **PV-Überschuss als Grundmodus:** Nur aktuell verfügbare PV-Leistung wird bis zum Hausbedarf freigegeben. Nicht benötigte PV-Leistung bleibt zum Laden im Akku; zusätzliche Batterieentladung wird vermieden.\n" +
          "- **PV-Überschuss bei vollem Akku einspeisen:** Standardmäßig aus. Bei erreichter System-Ladegrenze, ausreichender PV zur Verbrauchsdeckung und ohne laufende Zielladung setzt der XT500 für direkt angeschlossene PV den Netzanschluss-Sollwert auf 0 W und gibt die Wechselrichterleistung bis zu den eingestellten Grenzen frei. So kann PV nach Hausverbrauch ins Netz fließen. Reicht PV nicht aus, kehrt der gewählte Grundmodus zurück; im Normalbetrieb unterstützt der Akku den Hausverbrauch innerhalb seiner Entladegrenzen. Die tatsächliche Ausgabe, Netzleistung und Akkuunterstützung prüfen die Verbrauchsdeckung. Der Einstieg benötigt 30 Sekunden stabile Freigabe mit höchstens 10 W Akkuentladung und 10 W Netzbezug gegenüber dem Netzziel. Im aktiven Bypass bleiben 30 W Rückmeldungstoleranz erlaubt; eine Versorgungslücke beendet ihn sofort. Vor erneutem Einstieg beginnt die Prüfung von vorn. Das 1-%-SOC-Band hält die Vollakku-Erkennung stabil; neue Ladeaufträge und fehlende DC-PV-Freigabe beenden den Bypass. Gemessene Akkuentladung reduziert die Freigabe. Der Status „Akku voll – PV-Einspeisung“ zeigt die aktive Regelung, die tatsächliche Einspeisung zeigt der Netzzähler.\n" +
          "- **Bevorzugte Akku-Ladeleistung im PV-Überschussmodus:** Dieser Wert ist ausschließlich im PV-Überschussmodus wirksam und bezeichnet die gewünschte gemessene Netto-Ladeleistung des Akkus – nicht eine feste Ladeanforderung aus dem Netz. Entlädt der Akku, wird die XT500-Ausgangsleistung um die vollständige Entladeleistung plus den fehlenden Ladeanteil reduziert. Ist der Zielbereich erreicht, hält die Regelung den aktuellen Sollwert und gibt ihn erst mit zusätzlicher Ladereserve wieder nach oben frei. Dadurch wird Laden gegenüber Entladen bevorzugt und ein Pendeln an der 0-W-Grenze vermieden.\n" +
          "- **Netzeinspeisungs-Totzone im PV-Überschussmodus:** Die Totzone beruhigt nur die Rückführung der öffentlichen Netzeinspeisung. Für gemessene Akkuentladung gilt keine Totzone; sie wird vollständig gegengeregelt.\n" +
          "- **Ladelimit Normalbetrieb:** Dieser Wert wird als echte System-Ladegrenze an den Speicher geschrieben. Der auswählbare Bereich folgt dem Gerät; beim hier verwendeten System sind das 70 bis 100 %.\n" +
          "- **Lastanschluss-Entladegrenze:** Das ist die originale Geräte-Einstellung für den gesonderten XT500-Lastanschluss. Sie wird direkt am Speicher geändert und ist von der Entladegrenze der Energiemanager-Regelung getrennt.\n" +
          "- **Entladegrenze:** Das ist die originale System-Entladegrenze des XT500. Änderungen im Energiemanager oder in SunEnergyXT wirken auf denselben Gerätewert. Unterhalb dieses SOC stoppt die Batterieabgabe; die Energiemanager-Regelung wird erst oberhalb der zusätzlich eingestellten Hysterese wieder freigegeben.\n" +
          "- **Entladesperre einmalig freigeben:** Ist der Speicher nach Erreichen der Entladegrenze noch bis zur regulären Wiederfreigabe gesperrt, kann er innerhalb dieses Bereichs einmalig wieder entladen. Die Integration senkt dafür die Geräte-Entladegrenze vorübergehend ab. Sobald die eingestellte Entladegrenze erneut erreicht wird, bei Abschalten der Regelung oder nach einem Neustart wird der originale Wert automatisch zurückgestellt.\n" +
          "- Startet eine manuelle oder automatische Zielladung oberhalb des normalen Limits, hebt die Integration die System-Ladegrenze vorübergehend auf das benötigte Ziel an. Nach Zielerreichung stellt sie automatisch das normale Ladelimit wieder her.\n\n" +
          "**Lademodi für manuelle und automatische Ladung**\n\n" +
          "- **Netzladung:** Die eingestellte Leistung ist der gewünschte Anteil aus dem öffentlichen Netz. AC-PV kann zusätzlich laden. Beispiel: 1.200 W Netzanteil plus 600 W AC-PV ergeben bis zu 1.800 W Batterieladung, sofern das Gerät dies erlaubt.\n" +
          "- **PV-Überschuss:** Nutzt DC- und AC-PV-Überschuss ohne absichtlich Netzstrom zu beziehen. Das Ziel kann bei schlechtem Wetter mehrere Tage aktiv bleiben.\n" +
          "- **PV-Vorrang:** Hält direkt angeschlossene PV bevorzugt für den Akku zurück, nimmt AC-PV-Überschuss auf und verhindert eine Batterieentladung. Es wird kein absichtlicher Netzbezug erzeugt.\n" +
          "- **PV + Netz:** Die eingestellte Leistung ist das Ziel der gesamten Batterieladung. DC- und AC-PV tragen dazu bei; nur der fehlende Anteil kommt aus dem Netz. Beispiel: 1.200 W Ziel bei 600 W AC-PV führen ungefähr zu 600 W Netzbezug.\n\n" +
          "**Status richtig lesen**\n\n" +
          "- **Aktiver Vorgang** nennt den eindeutigen Besitzer der Sollwerte: Normalbetrieb, manuelle Zielladung, Zyklusladung oder Tarifladung. Nur dieser Vorgang darf regeln.\n" +
          "- **Ausgewählter Lademodus** zeigt die Einstellung, **Aktiver Lademodus** die gerade wirksame Regelstrategie und **Zustand des Lademodus** beispielsweise Lädt oder Wartet auf ausreichend PV.\n" +
          "- **Gewählte PV-Berücksichtigung** zeigt, welche PV-Anlagen die Regelung verwenden darf. **Aktuell nutzbare PV-Quelle** zeigt, ob XT500-PV, externer AC-PV-Überschuss, beide oder keine davon verfügbar sind. **Tatsächliche Ladequelle** zeigt ausschließlich, womit der Akku gerade wirklich geladen wird.\n" +
          "- **Externe AC-PV-Erzeugung** ist die gesamte momentane Leistung des separaten Wechselrichters und bedeutet noch keine Akkuladung. Erst **AC-PV-Überschuss am Netzanschluss** zeigt den Anteil, der nach dem Hausverbrauch für den Akku verfügbar wäre. Die wirkliche Nettoladung steht unter **Akku lädt**.\n\n" +
          "**Dynamischer Stromtarif**\n\n" +
          "- Eine externe Preisautomation oder der mitgelieferte Tarif-Blueprint darf eine eigene **Tarifladung** anfordern. Diese verwendet ausschließlich Netzladung mit dem separaten Tarif-Ladeziel und der separaten Netz-Ladeleistung.\n" +
          "- Manuelle Zielladung und Zyklusladung haben Vorrang. Die Tarifanforderung bleibt währenddessen nur bis zu ihrem angezeigten Ablaufzeitpunkt vorgemerkt.\n" +
          "- Jede erneute Anforderung verlängert die Gültigkeit. Bleibt die Preisautomation aus oder wird der Preissensor ungültig, endet die Tarifladung spätestens nach der eingestellten Dauer automatisch und der Grundmodus übernimmt wieder.\n" +
          "- Bei hohem Preis ist kein eigener Entlademodus nötig: Nach Ende der Tarifladung versorgt der Normalbetrieb das Haus bereits aus dem Akku, solange die Entladegrenze nicht erreicht ist. Eine Einspeisung aus dem Akku ins öffentliche Netz wird dadurch nicht angefordert.\n\n" +
          "**Zyklusladung: Überwachung, Start und Rücksetzen**\n\n" +
          "- **Automatische Zyklusüberwachung** beobachtet nur den Zeitabstand. Sie bedeutet nicht, dass gerade geladen wird.\n" +
          "- Ist das Intervall abgelaufen, zeigt der Zyklusstatus **Fällig – wartet auf tägliche Prüfzeit**. Erst zur eingestellten **täglichen Prüfzeit** startet die Integration die Ladung im gewählten Zyklus-Lademodus.\n" +
          "- **Jetzt manuell starten** beginnt die Zyklusladung sofort – unabhängig davon, ob sie bereits fällig ist. Dafür werden ebenfalls der Zyklus-Lademodus und das Vollladeziel verwendet. Die automatische Überwachung bleibt unverändert ein- oder ausgeschaltet.\n" +
          "- Der **Zyklusstatus** unterscheidet eindeutig zwischen Überwachung, fälligem Zyklus, manueller Zyklusladung, automatischer Zyklusladung und einer angehaltenen Ladung.\n" +
          "- **Nächste Zyklusladung** zeigt den aktuell berechneten Termin aus letzter Vollladung bzw. Rücksetzzeitpunkt, Intervall und täglicher Prüfzeit.\n" +
          "- **Zyklustage auf 0 setzen** beginnt das Intervall ab jetzt neu und beendet eine eventuell laufende Zyklusladung. Es wird dabei keine künstliche Vollladung eingetragen.\n\n" +
          "**Ziel erreicht**\n\n" +
          "- Beim manuellen Ziel wird die manuelle Zielladung ausgeschaltet und der Grundmodus wieder aktiv.\n" +
          "- Erreicht eine manuell oder automatisch gestartete Zyklusladung das Vollladeziel, wird sie beendet, der Zeitpunkt gespeichert und der Grundmodus wieder aktiv.\n" +
          "- Die nächste automatische Zyklusladung wird erst nach dem Intervall und anschließend zur täglichen Prüfzeit gestartet.\n" +
          "- Erreicht der Speicher das automatische Vollladeziel ganz normal durch PV, zählt dies ebenfalls als erfolgreiche Vollladung – auch ohne laufende Zyklusladung.\n" +
          "- Die System-Ladegrenze kehrt danach immer zum **Ladelimit Normalbetrieb** zurück.\n\n" +
          "**Regelruhe und Sicherheit:** Kleine Abweichungen werden fein, mittlere stärker und große Lastsprünge schnell korrigiert. Nach einem Sollwertschreiben wartet die Integration auf neue Messwerte. Im PV-Überschussbetrieb setzt die Niedrig-PV-Sperre beide Sollwerte unterhalb der Abschaltschwelle sofort auf 0 W und gibt sie erst nach der eingestellten Zeit oberhalb der Startleistung wieder frei.\n\n" +
          "**Leistungsflüsse:** Batterie lädt und Batterie entlädt sind Nettowerte aus den originalen XT500-Gesamteingangs- und Gesamtausgangsleistungen. Beispiel: 200 W Eingang und 300 W Ausgang werden als 0 W Laden und 100 W tatsächliches Entladen angezeigt.\n\n" +
          "**Kommunikationspause und Fehlerwiederherstellung:** Ein kurzzeitig nicht lesbarer XT500-Sollwert oder Verbindungsabbruch pausiert die Regelung zunächst, ohne sie sofort zu verriegeln. Erst nach 15 Sekunden stabilen, frischen Messrückmeldungen wird automatisch weitergeregelt. Bleibt die Verbindung 90 Sekunden lang instabil oder schlagen drei echte Schreibversuche trotz lesbarer Sollwerte fehl, wird die Regelung sicher verriegelt. Ist **Fehler automatisch beheben** aktiv, startet danach die geschützte Wiederherstellung mit stabilem Feedback und einem wirkungslosen Schreibtest. Nach höchstens drei erfolglosen Wiederherstellungsversuchen ist ein manueller Aus-/Ein-Reset von **Regelung aktiv** erforderlich.\n\n" +
          "**Leistungsgrenzen:** **Maximale Leistung ins Hausnetz** begrenzt nur die positive Abgabe des Speichers; für einen XT500 sind hier üblicherweise 800 W einzustellen. Diese Grenze reduziert nicht die Netzladung. Bei **Netzladung** richtet sich deren negativer Sollwert nach **Gewünschte Ladeleistung**. Bei **PV + Netz** wird nur die nach Anrechnung des PV-Anteils fehlende Leistung aus dem Netz bezogen. Der echte Gerätebereich bleibt die technische Obergrenze – beim XT500 Pro sind bis zu 2.400 W Netzladung möglich. Die Wechselrichter-Obergrenze ist ein technischer Sollwert, kein gemessener Leistungsfluss.\n\n" +
          "</details>",
      };

      const quickControlCards = compact([
        heading("Schnellsteuerung", "mdi:shield-home"),
        entities.regulation_enabled ? {
          ...tile("regulation_enabled", "Regelung", [{ type: "toggle" }]),
          grid_options: { columns: 6, rows: "auto" },
        } : null,
        entities.manual_active ? {
          ...tile("manual_active", "Zielladung", [{ type: "toggle" }]),
          grid_options: { columns: 6, rows: "auto" },
        } : null,
        entities.automatic_enabled ? {
          ...tile("automatic_enabled", "Automatik", [{ type: "toggle" }]),
          grid_options: { columns: 6, rows: "auto" },
        } : null,
        entities.cycle_start ? {
          ...tile("cycle_start", "Zyklusstart", [{ type: "button" }]),
          grid_options: { columns: 6, rows: "auto" },
        } : null,
      ]);
      const overviewBlocks = {
        storage: storageGauge ? {
          type: "grid",
          cards: [
            heading("Speicherstand", "mdi:home-battery"),
            storageGauge,
          ],
        } : null,
        regulation_status: regulationStatusEntities.length ? {
          type: "grid",
          cards: [
            heading("Regelungsstatus", "mdi:shield-check"),
            {
              type: "entities",
              show_header_toggle: false,
              entities: regulationStatusEntities,
            },
          ],
        } : null,
        setpoints: setpointEntities.length ? {
          type: "grid",
          cards: [
            heading("Sollwerte und Berechnung", "mdi:tune-vertical"),
            {
              type: "entities",
              show_header_toggle: false,
              entities: setpointEntities,
            },
          ],
        } : null,
        cycle: cycleEntities.length ? {
          type: "grid",
          cards: [
            heading("Zyklusladung", "mdi:battery-sync"),
            {
              type: "entities",
              show_header_toggle: false,
              entities: cycleEntities,
            },
          ],
        } : null,
        flows: flowEntities.length ? {
          type: "grid",
          cards: [
            heading("Aktuelle Leistungsflüsse", "mdi:transmission-tower"),
            ...flowTiles,
          ],
        } : null,
        energy_today: dailyEnergyTiles.length ? {
          type: "grid",
          cards: [
            heading("Energie heute", "mdi:chart-donut"),
            ...dailyEnergyTiles,
          ],
        } : null,
        quick_controls: quickControlCards.length > 1 ? {
          type: "grid",
          cards: quickControlCards,
        } : null,
      };
      const settingsBlocks = {
        guide: {
          type: "grid",
          column_span: 3,
          cards: [guideCard],
        },
        main_control: mainControlCards.length > 1 ? {
          type: "grid",
          cards: mainControlCards,
        } : null,
        target_charge: [manualChargeCards, cycleChargeCards]
          .filter((cards) => cards.length > 1)
          .map((cards) => ({ type: "grid", cards })),
        tariff_charge: tariffControlCards.length > 1 ? {
          type: "grid",
          cards: tariffControlCards,
        } : null,
        normal_limits: [normalOperationCards, batteryProtectionCards]
          .filter((cards) => cards.length > 1)
          .map((cards) => ({ type: "grid", cards })),
        advanced: [adaptiveThresholdCards, adaptiveResponseCards, pvRecoveryCards]
          .filter((cards) => cards.length > 1)
          .map((cards) => ({ type: "grid", cards })),
      };

      views.push({
        title: managers.size > 1 ? `XT500 ${index}` : "Speicher",
        path: managers.size > 1 ? `speicher-${index}` : "speicher",
        icon: "mdi:home-battery",
        type: "sections",
        max_columns: 3,
        sections: orderedVisibleBlocks(config, "overview", overviewBlocks),
      });

      const settingsSuffix = managers.size > 1 ? `-${index}` : "";
      const settingsNavigation = {
        type: "grid",
        cards: [
          heading("Weitere Einstellungen", "mdi:view-dashboard-outline"),
          {
            type: "button",
            name: "Laden und Zyklus",
            icon: "mdi:battery-charging-high",
            tap_action: {
              action: "navigate",
              navigation_path: `/${dashboardPath}/laden${settingsSuffix}`,
            },
            grid_options: { columns: 6, rows: 1 },
          },
          {
            type: "button",
            name: "Feinabstimmung",
            icon: "mdi:tune-vertical",
            tap_action: {
              action: "navigate",
              navigation_path: `/${dashboardPath}/feinabstimmung${settingsSuffix}`,
            },
            grid_options: { columns: 6, rows: 1 },
          },
        ],
      };
      settingsViews.push({
        title: managers.size > 1 ? `Einstellungen ${index}` : "Einstellungen",
        path: `einstellungen${settingsSuffix}`,
        icon: "mdi:cog-outline",
        type: "sections",
        max_columns: 2,
        sections: orderedVisibleBlocks(config, "settings", {
          guide: settingsBlocks.guide ? {
            ...settingsBlocks.guide,
            column_span: 2,
          } : null,
          main_control: settingsBlocks.main_control,
          normal_limits: settingsBlocks.normal_limits,
        }).flatMap((section, sectionIndex) =>
          sectionIndex === 1 ? [settingsNavigation, section] : [section]
        ),
      });
      settingsViews.push({
        title: managers.size > 1 ? `Laden ${index}` : "Laden",
        path: `laden${settingsSuffix}`,
        icon: "mdi:battery-charging-high",
        subview: true,
        back_path: `/${dashboardPath}/einstellungen${settingsSuffix}`,
        type: "sections",
        max_columns: 2,
        sections: [
          ...orderedVisibleBlocks(config, "settings", {
            target_charge: settingsBlocks.target_charge,
            tariff_charge: settingsBlocks.tariff_charge,
          }),
          ...(fullChargeConfirmationCards.length > 1 ? [{
            type: "grid",
            cards: fullChargeConfirmationCards,
          }] : []),
        ],
      });
      settingsViews.push({
        title: managers.size > 1 ? `Feinabstimmung ${index}` : "Feinabstimmung",
        path: `feinabstimmung${settingsSuffix}`,
        icon: "mdi:tune-vertical",
        subview: true,
        back_path: `/${dashboardPath}/einstellungen${settingsSuffix}`,
        type: "sections",
        max_columns: 2,
        sections: orderedVisibleBlocks(config, "settings", {
          advanced: settingsBlocks.advanced,
        }),
      });
    }

    views.push(...await loadAdditionalViews(config, hass, views));
    views.push(...energyViews(config, socEntities));
    views.push(...settingsViews);
    return { title: config.title || "XT500 Energiemanager", views };
  }
}

if (!customElements.get("xt500-energy-manager-strategy-editor")) {
  customElements.define(
    "xt500-energy-manager-strategy-editor",
    XT500EnergyManagerStrategyEditor,
  );
}

if (!customElements.get("ll-strategy-dashboard-xt500-energy-manager")) {
  customElements.define(
    "ll-strategy-dashboard-xt500-energy-manager",
    XT500EnergyManagerDashboardStrategy,
  );
}

window.customStrategies = window.customStrategies || [];
if (!window.customStrategies.some((strategy) => strategy.type === "xt500-energy-manager")) {
  window.customStrategies.push({
    type: "xt500-energy-manager",
    strategyType: "dashboard",
    name: "XT500 Energiemanager",
    description: "Automatisch erzeugte Bedien- und Diagnoseoberfläche für den XT500 Energiemanager.",
    documentationURL: "https://github.com/achim1985/xt500-energy-manager#4-dashboard-einrichten",
  });
}
