"use strict";
(() => {
  const $ = id => document.getElementById(id);
  // Los colores proceden de los tokens de styles.css; el segundo valor solo cubre un fallo de carga del CSS.
  const tokens = getComputedStyle(document.documentElement);
  const token = (name, fallback) => tokens.getPropertyValue(name).trim() || fallback;
  const colors = {a: token("--phase-a", "#2a78d6"), b: token("--phase-b", "#eb6834"), c: token("--phase-c", "#4a3aa7"),
    series: token("--series", "#33375c"), series2: token("--series-2", "#6a71b5"), series3: token("--series-3", "#a3a8d0"),
    context: token("--context", "#7d8298"), alert: token("--alert", "#d03b3b"), grid: token("--grid", "#e6e7ef"),
    ink: token("--ink", "#1e2030"), text: token("--ink-2", "#474b60"), muted: token("--ink-3", "#676c84"),
    surface: token("--surface", "#ffffff"), panel: token("--panel", "#f8f8fb"), accent: token("--accent", "#5443b8")};
  const shapes = {a: "circle", b: "square", c: "diamond"};
  const family = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
  const fmt = (value, digits = 0) => new Intl.NumberFormat("es", {useGrouping: "always", maximumFractionDigits: digits, minimumFractionDigits: digits}).format(value);
  let data = null, active = "resumen", hours = 72;
  const drawings = new Map();
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const panels = [...document.querySelectorAll('[role="tabpanel"]')];
  const keys = [...document.querySelectorAll("button.key-item")];
  const config = {responsive: true, displaylogo: false, scrollZoom: false, displayModeBar: true,
    modeBarButtonsToRemove: ["toImage", "select2d", "lasso2d", "autoScale2d", "zoomIn2d", "zoomOut2d", "resetScale2d"],
    doubleClick: "reset", locale: "es-local"};
  function axis(title, extra = {}) {
    return {title: {text: title, standoff: 12, font: {size: 12, color: colors.text}}, tickfont: {size: 12, color: colors.muted},
      gridcolor: colors.grid, linecolor: colors.grid, zeroline: false, automargin: true, ...extra};
  }
  function layout(xTitle, yTitle, extra = {}) {
    return {paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: {family, color: colors.ink, size: 12},
      margin: {l: 56, r: 16, t: 36, b: 52}, hovermode: "closest", hoverdistance: 40,
      hoverlabel: {bgcolor: colors.surface, font: {family, size: 12, color: colors.ink}},
      modebar: {bgcolor: "rgba(0,0,0,0)", color: colors.muted, activecolor: colors.accent},
      xaxis: axis(xTitle), yaxis: axis(yTitle), showlegend: false, ...extra};
  }
  // La clave HTML de cada gráfica sustituye a la leyenda de Plotly y conserva su activación de series.
  const shown = key => key.getAttribute("aria-pressed") === "true" ? true : "legendonly";
  async function plot(id, traces, settings, mini = false) {
    drawings.set(id, {traces: structuredClone(traces), settings: structuredClone(settings), mini});
    keys.filter(key => key.dataset.chart === id).forEach(key => traces.forEach(item => {if (item.name === key.dataset.series) item.visible = shown(key);}));
    await Plotly.react($(id), traces, settings, {...config, displayModeBar: !mini});
    if ($(id).offsetWidth > 0) await Plotly.Plots.resize($(id));
  }
  function dateLabel(value) { return value.slice(0, 10).split("-").reverse().join("/"); }
  function row(cells) {
    const tr = document.createElement("tr");
    cells.forEach((text, index) => {const cell = document.createElement(index ? "td" : "th"); if (!index) cell.scope = "row"; cell.textContent = text; tr.append(cell);});
    return tr;
  }
  function go(id, focus = false) {
    if (!panels.some(panel => panel.id === id)) id = "resumen";
    active = id;
    tabs.forEach(tab => {const selected = tab.getAttribute("aria-controls") === id; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1;});
    panels.forEach(panel => {panel.hidden = panel.id !== id;});
    const list = $("tabs"), tab = $("tab-" + id);
    list.scrollLeft = tab.offsetLeft - (list.clientWidth - tab.offsetWidth) / 2;
    history.replaceState(null, "", "#" + id);
    if (focus) tab.focus();
    if (data) render().catch(showError);
  }
  function showError(error) {
    $("load-status").hidden = true; $("load-error").hidden = false;
    $("error-detail").textContent = error.message || "Los datos no están disponibles. Intenta nuevamente.";
  }
  function trace(x, y, name, color, extra = {}) {
    return {type: "scatter", x, y, name, mode: "lines", line: {color, width: 2}, connectgaps: false, hoverlabel: {bordercolor: color}, ...extra};
  }
  function populate() {
    $("record-count").textContent = fmt(data.summary.source_rows);
    $("signal-count").textContent = fmt(data.signal_count);
    $("selected-count").textContent = fmt(data.summary.selected_measurements);
    $("lead-hours").textContent = fmt(data.summary.lead_hours) + " horas";
    const facts = [["Horas sin medición", data.summary.measurement_hours_missing, "No se interpolan; el hueco queda documentado."],
      ["Horas contradictorias", data.quality.multiple_hours, "Se conservan las dos alternativas; ninguna entra en la selección estadística."],
      ["Timestamps desplazados", data.quality.shifted_rows, "Reciben una hora lógica derivada; el timestamp original no cambia."],
      ["Eventos de comunicación", data.incidents.communication.length, "Se conservan como eventos; no son mediciones ni rellenan huecos."],
      ["Horas de sensor congelado", data.summary.sensor_flat_hours, "La hora completa queda fuera de la comparación; la fila se conserva."]];
    $("quality-facts").replaceChildren(...facts.map(([label, value, treatment]) => {const tr = row([label, fmt(value), treatment]); tr.children[1].className = "num"; return tr;}));
    $("window-rows").replaceChildren(...[72, 24, 6].map(size => {
      const period = data.summary.periods.find(item => item.period === "pre_event_" + size + "h");
      const tr = row([size + " horas", fmt(period.eligible_hours) + " / " + fmt(period.calendar_hours), fmt(period.persistent_alert_hours),
        period.winding_rise_c_residual_median == null ? "Sin soporte" : fmt(period.winding_rise_c_residual_median, 2) + " °C"]);
      const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = "en la gráfica";
      tr.dataset.hours = size; tr.children[0].append(" ", tag); [1, 2, 3].forEach(index => {tr.children[index].className = "num";});
      return tr;
    }));
  }
  async function overview() {
    const r = data.relationships.reference, c = data.coverage, t = data.timeline.filter(row => row.hours_to_event >= -72 && row.hours_to_event < 0);
    const mini = (x, y) => layout(x, y, {margin: {l: 52, r: 12, t: 8, b: 44}});
    await Promise.all([
      plot("overview-load", [trace(r.map(row => row.active_power_kw), r.map(row => row.mean_current_a), "Corriente media", colors.series,
        {mode: "markers", marker: {size: 5, color: colors.series, opacity: .55}, hovertemplate: "%{x:.2f} kW · %{y:.2f} A<extra></extra>"})], mini("Potencia activa (kW)", "Corriente media (A)"), true),
      plot("overview-quality", [trace(c.map(row => row.t), c.map(row => row.selected), "Horas seleccionadas", colors.series,
        {hovertemplate: "%{x|%d/%m/2042} · %{y} horas<extra></extra>"})], mini("Año ficticio 2042", "Horas por día"), true),
      plot("overview-event", [trace(t.map(row => row.hours_to_event), t.map(row => row.eligible ? row.current_spread_pct : null), "Dispersión de corriente", colors.series,
        {hovertemplate: "%{x} h · %{y:.2f}%<extra></extra>"})], mini("Horas antes del evento", "Dispersión (%)"), true)
    ]);
  }
  async function variables() {
    const key = $("relationship-period").value, rows = data.relationships[key];
    const selected = [...document.querySelectorAll("[data-phase]:checked")].map(input => input.dataset.phase);
    $("phase-empty").hidden = selected.length > 0;
    $("current-chart").hidden = selected.length === 0;
    $("relationship-range").textContent = rows.length ? dateLabel(rows[0].t) + " — " + dateLabel(rows.at(-1).t) + " · " + fmt(rows.length) + " horas elegibles" : "Sin observaciones elegibles en este período";
    const x = rows.map(row => row.active_power_kw);
    const custom = rows.map(row => [row.t.replace("T", " ").slice(0,19), row.reactive_power_kvar, row.mean_voltage_v]);
    // Símbolos huecos: las fases que coinciden siguen viéndose una sobre otra.
    const open = (phase, size) => ({color: colors[phase], symbol: shapes[phase] + "-open", size, line: {width: 1.6, color: colors[phase]}});
    if (selected.length) await plot("current-chart", selected.map(phase => trace(x, rows.map(row => row["phase_current_" + phase]), "Fase " + phase.toUpperCase(), colors[phase],
      {mode: "markers", customdata: custom, marker: open(phase, 8),
        hovertemplate: "%{customdata[0]}<br>P: %{x:.4f} kW<br>I: %{y:.4f} A<br>Q: %{customdata[1]:.4f} kvar<br>Tensión media: %{customdata[2]:.4f} V<extra>%{fullData.name}</extra>"})), layout("Potencia activa (kW)", "Corriente (A)"));
    const absolute = $("thermal-mode").value === "absolute";
    $("thermal-key").hidden = !absolute;
    const traces = absolute ? ["a", "b", "c"].map(phase => trace(x, rows.map(row => row["winding_temperature_" + phase + "_c"]), "Devanado " + phase.toUpperCase(), colors[phase],
      {mode: "markers", marker: open(phase, 7), customdata: custom,
        hovertemplate: "%{customdata[0]}<br>%{x:.4f} kW · %{y:.4f} °C<extra>%{fullData.name}</extra>"})) : [trace(x, rows.map(row => row.winding_rise_c), "Elevación media", colors.series,
      {mode: "markers", marker: {color: colors.series, size: 7, opacity: .7, line: {width: 1, color: colors.panel}}, customdata: custom, hovertemplate: "%{customdata[0]}<br>%{x:.4f} kW · %{y:.4f} °C<extra></extra>"})];
    if (absolute) traces.push(trace(x, rows.map(row => row.room_temperature_c), "Ambiente", colors.context, {mode: "markers", marker: {color: colors.context, symbol: "cross", size: 6}, hovertemplate: "%{x:.4f} kW · %{y:.4f} °C<extra>Ambiente</extra>"}));
    await plot("thermal-chart", traces, layout("Potencia activa (kW)", absolute ? "Temperatura (°C)" : "Elevación sobre ambiente (°C)"));
  }
  async function quality() {
    const c = data.coverage, x = c.map(row => row.t);
    await plot("coverage-chart", [["preserved", "Filas de medición conservadas", colors.series3, "dot"], ["selected", "Horas seleccionadas", colors.series2, "solid"], ["eligible", "Horas elegibles", colors.series, "dash"]].map(([key, name, color, dash]) =>
      trace(x, c.map(row => row[key]), name, color, {line: {color, width: 2, dash}, hovertemplate: "%{x|%d/%m/2042}<br>%{y} registros u horas<extra>%{fullData.name}</extra>"})), layout("Año ficticio 2042", "Conteo diario", {hovermode: "x unified"}));
    const sensor = data.sensor.rows;
    await plot("sensor-chart", [["bearing_temperature_a_c", "Cojinete A", colors.a, "solid"], ["bearing_temperature_b_c", "Cojinete B", colors.b, "dash"], ["room_temperature_c", "Ambiente", colors.context, "dot"]].map(([key, name, color, dash]) =>
      trace(sensor.map(row => row.t), sensor.map(row => row[key]), name, color, {line: {color, width: 2, dash}, hovertemplate: "%{x|%d/%m %H:%M}<br>%{y:.4f} °C<extra>%{fullData.name}</extra>"})),
      layout("Junio de 2042 · reloj ficticio", "Temperatura (°C)", {hovermode: "x unified", margin: {l: 56, r: 16, t: 56, b: 52}, xaxis: axis("Junio de 2042 · reloj ficticio", {tickformat: "%H:%M<br>%-d %b"}),
        shapes: [{type: "rect", xref: "x", yref: "paper", x0: data.sensor.start, x1: data.sensor.end_exclusive, y0: 0, y1: 1, fillcolor: colors.context, opacity: .14, line: {width: 0}}],
        annotations: [{xref: "x", yref: "paper", x: data.sensor.start, y: 1, xanchor: "left", yanchor: "bottom", showarrow: false, font: {size: 12, color: colors.text},
          text: "Lectura congelada · " + fmt(data.summary.sensor_flat_hours) + " h"}]}));
  }
  async function anomalies() {
    const period = data.summary.periods.find(item => item.period === "pre_event_" + hours + "h");
    const rows = data.timeline.filter(row => row.hours_to_event >= -hours && row.hours_to_event < 0);
    document.querySelectorAll("#window-rows tr").forEach(tr => {const current = Number(tr.dataset.hours) === hours; tr.classList.toggle("is-active", current); if (current) tr.setAttribute("aria-current", "true"); else tr.removeAttribute("aria-current");});
    $("window-range").textContent = "Desde " + dateLabel(period.start_inclusive) + " " + period.start_inclusive.slice(11, 16) + " · evento excluido";
    const narrow = $("anomaly-chart").offsetWidth < 520;
    const metrics = [["winding_rise_c", "Elevación térmica (°C)"], ["current_spread_pct", "Dispersión de corriente (%)"], ["voltage_spread_pct", "Dispersión de tensión (%)"]];
    const traces = [], annotations = [], settings = layout("Horas respecto del evento artificial (0)", "", {height: undefined, margin: {l: 52, r: 16, t: 56, b: 56}, shapes: [], annotations});
    metrics.forEach(([key, title], index) => {
      const axisName = index ? "y" + (index + 1) : "y", axisKey = index ? "yaxis" + (index + 1) : "yaxis";
      const domain = [[.73, 1], [.365, .635], [0, .27]][index];
      settings[axisKey] = {domain, gridcolor: colors.grid, tickfont: {size: 12, color: colors.muted}, zeroline: false, automargin: true};
      annotations.push({xref: "paper", yref: "paper", x: 0, y: domain[1], xanchor: "left", yanchor: "bottom", text: "<b>" + title + "</b>", showarrow: false, font: {size: 12, color: colors.ink}});
      const x = rows.map(row => row.hours_to_event), tooltip = "%{x} h · %{y:.4f}" + (index ? "%" : " °C") + "<extra>%{fullData.name}</extra>";
      traces.push(trace(x, rows.map(row => row.eligible ? row[key] : null), "Indicador calculado", colors.series, {yaxis: axisName, hovertemplate: tooltip}));
      traces.push(trace(x, rows.map(row => row.eligible ? row[key + "_p99"] : null), "Umbral P99 histórico", colors.context, {yaxis: axisName, line: {color: colors.context, dash: "dash", width: 1.5}, hovertemplate: tooltip}));
      const alerts = rows.filter(row => row.persistent_alert);
      traces.push(trace(alerts.map(row => row.hours_to_event), alerts.map(row => row[key]), "Alerta persistente", colors.alert, {yaxis: axisName, mode: "markers", cliponaxis: false, marker: {size: narrow ? 7 : 9, symbol: "diamond", color: colors.alert, line: {width: narrow ? 1 : 1.5, color: colors.panel}}, hovertemplate: tooltip}));
    });
    settings.xaxis = {...settings.xaxis, anchor: "y3", range: [-hours, 1], tickvals: hours === 72 ? [-72, -48, -24, -6, 0] : hours === 24 ? [-24, -18, -12, -6, 0] : [-6, -5, -4, -3, -2, -1, 0]};
    settings.shapes = [{type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: {color: colors.ink, width: 1.5}}];
    annotations.push({xref: "x", yref: "paper", x: 0, y: 1, xanchor: "right", yanchor: "bottom", xshift: 4, text: "Evento artificial", showarrow: false, font: {size: 12, color: colors.ink}});
    await plot("anomaly-chart", traces, settings);
  }
  async function render() {
    if (active === "resumen") await overview();
    if (active === "variables") await variables();
    if (active === "calidad") await quality();
    if (active === "anomalias") await anomalies();
  }
  async function load() {
    data = null; $("load-error").hidden = true; $("load-status").hidden = false; $("load-status").classList.remove("loaded");
    $("load-status").textContent = "Cargando la demostración sintética…";
    try {
      if (!window.Plotly) throw new Error("No se pudo cargar la biblioteca local de gráficos.");
      Plotly.register({moduleType: "locale", name: "es-local", dictionary: {"Zoom": "Ampliar", "Pan": "Desplazar", "Reset axes": "Restablecer ejes"}, format: {days: ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"], shortDays: ["dom","lun","mar","mié","jue","vie","sáb"], months: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"], shortMonths: ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"], decimal: ",", thousands: ".", grouping: [3], date: "%d/%m/%Y"}});
      const response = await fetch("assets/dashboard-data.json", {cache: "no-cache"});
      if (!response.ok) throw new Error("No se pudo leer el archivo de datos. Sirve docs/ mediante HTTP y comprueba assets/dashboard-data.json.");
      const payload = await response.json();
      if (payload.schema_version !== 1 || payload.synthetic_only !== true || !Array.isArray(payload.timeline) || !Array.isArray(payload.coverage) || !payload.summary || !payload.relationships) throw new Error("El archivo no corresponde al esquema sintético del explorador.");
      data = payload; populate(); await render();
      $("load-status").classList.add("loaded"); $("load-status").textContent = "Datos disponibles · año ficticio 2042 · semilla " + data.seed;
    } catch (error) { showError(error); }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => go(tab.getAttribute("aria-controls")));
    tab.addEventListener("keydown", event => {let next = null; if (event.key === "ArrowRight") next = (index + 1) % tabs.length; if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length; if (event.key === "Home") next = 0; if (event.key === "End") next = tabs.length - 1; if (next !== null) {event.preventDefault(); go(tabs[next].getAttribute("aria-controls"), true);}});
  });
  document.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => {go(button.dataset.go, true); $("main").scrollIntoView({behavior: "auto"});}));
  document.querySelector(".brand").addEventListener("click", event => {event.preventDefault(); go("resumen");});
  [$("relationship-period"), $("thermal-mode"), ...document.querySelectorAll("[data-phase]")].forEach(control => control.addEventListener("change", () => {if (data) variables().catch(showError);}));
  document.querySelectorAll("[data-window]").forEach(button => button.addEventListener("click", () => {hours = Number(button.dataset.window); document.querySelectorAll("[data-window]").forEach(item => item.setAttribute("aria-pressed", String(item === button))); if (data) anomalies().catch(showError);}));
  keys.forEach(key => key.addEventListener("click", () => {
    key.setAttribute("aria-pressed", String(key.getAttribute("aria-pressed") !== "true"));
    const chart = $(key.dataset.chart), indices = (chart.data || []).flatMap((item, index) => item.name === key.dataset.series ? [index] : []);
    if (indices.length) Plotly.restyle(chart, {visible: shown(key)}, indices);
  }));
  document.querySelectorAll("[data-reset]").forEach(button => button.addEventListener("click", async () => {const id = button.dataset.reset, saved = drawings.get(id); if (saved) {await Plotly.purge($(id)); await plot(id, saved.traces, saved.settings, saved.mini);}}));
  document.querySelectorAll("[data-zoom]").forEach(button => button.addEventListener("click", () => {const chart = $(button.dataset.zoom); if (!chart._fullLayout || chart.hidden) return; const changes = {}; for (const axis of ["xaxis", "yaxis"]) {const [lo, hi] = chart._fullLayout[axis].range; const mid = (lo + hi) / 2; changes[axis + ".range"] = [mid - (hi - lo) / 4, mid + (hi - lo) / 4];} Plotly.relayout(chart, changes);}));
  $("retry").addEventListener("click", load);
  window.addEventListener("hashchange", () => go(location.hash.slice(1)));
  go(location.hash.slice(1) || "resumen"); load();
})();
