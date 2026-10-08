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
  const pct = value => value == null ? "—" : fmt(100 * value) + "\u00a0%";
  const span = (pair, scale = 1, digits = 0) => pair ? fmt(scale * pair[0], digits) + " – " + fmt(scale * pair[1], digits) : "—";
  const hoursText = value => value == null ? "—" : fmt(value) + " h";
  // El color y el símbolo siguen al método en todas las vistas.
  const methods = [["load_ambient", "Condicionado por carga y ambiente", "a"], ["none", "Umbral fijo", "b"]];
  const methodNames = {load_ambient: "Condicionado por carga y ambiente", load: "Condicionado solo por carga", none: "Umbral fijo"};
  let data = null, active = "resumen", eventIndex = 0;
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
  const mini = (x, y, extra = {}) => layout(x, y, {margin: {l: 52, r: 12, t: 8, b: 44}, ...extra});
  // La clave HTML de cada gráfica sustituye a la leyenda de Plotly y conserva su activación de series.
  const shown = key => key.getAttribute("aria-pressed") === "true" ? true : "legendonly";
  async function plot(id, traces, settings, small = false) {
    drawings.set(id, {traces: structuredClone(traces), settings: structuredClone(settings), small});
    keys.filter(key => key.dataset.chart === id).forEach(key => traces.forEach(item => {if (item.name === key.dataset.series) item.visible = shown(key);}));
    await Plotly.react($(id), traces, settings, {...config, displayModeBar: !small});
    if ($(id).offsetWidth > 0) await Plotly.Plots.resize($(id));
  }
  function dateLabel(value) { return value.slice(0, 10).split("-").reverse().join("/"); }
  const stamp = value => dateLabel(value) + " " + value.slice(11, 16);
  function row(cells, numeric = []) {
    const tr = document.createElement("tr");
    cells.forEach((text, index) => {const cell = document.createElement(index ? "td" : "th"); if (!index) cell.scope = "row"; if (numeric.includes(index)) cell.className = "num"; cell.textContent = text; tr.append(cell);});
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
    const evaluation = data.evaluation, results = evaluation.evaluation, primary = results.load_ambient, fixed = results.none;
    const protocol = evaluation.protocol, point = evaluation.operating_point, years = protocol.evaluation_seeds.length;
    const detected = data.events.filter(event => event.detected).length;
    // Resumen: cada cifra visible sale del bloque de evaluación publicado.
    const per100 = value => fmt(100 * value);
    const bands = primary.by_severity, fixedBands = fixed.by_severity;
    $("result-detection").textContent = per100(primary.detection_rate) + " de cada 100";
    $("result-detection-note").textContent = "fallas avisadas antes del disparo. Con un umbral fijo, " + per100(fixed.detection_rate) + " de cada 100.";
    $("result-false").textContent = fmt(primary.false_alarms_per_1000h, 2) + " por 1000 h";
    $("result-false-note").textContent = "falsas alarmas en operación normal: unas " + fmt(primary.false_alarms_per_1000h * 8.76) + " al año.";
    $("result-lead").textContent = hoursText(primary.lead_hours_median) + " o más";
    $("result-lead-note").textContent = "de margen en la mitad de los avisos: tiempo para planear una parada.";
    $("result-basis").textContent = "Medido en " + fmt(years) + " años simulados que la regla nunca vio (" + fmt(primary.events) +
      " fallas). La regla se ajustó con otros " + fmt(protocol.calibration_seeds.length) + ".";
    $("findings-detail").textContent = "Comparar con horas parecidas avisa en " + per100(primary.detection_rate) + " de cada 100 fallas; un umbral fijo, en " +
      per100(fixed.detection_rate) + ". Pero el tamaño importa: se detectó el " + pct(bands[0].detection_rate) + " de las fallas más leves y el " +
      pct(bands.at(-1).detection_rate) + " de las más fuertes (con umbral fijo, " + pct(fixedBands[0].detection_rate) + " y " + pct(fixedBands.at(-1).detection_rate) + ").";
    const facts = [["Horas sin medición", data.summary.measurement_hours_missing, "No se interpolan; el hueco queda documentado."],
      ["Horas contradictorias", data.quality.multiple_hours, "Se conservan las dos alternativas; ninguna entra en la selección estadística."],
      ["Marcas de tiempo desplazadas", data.quality.shifted_rows, "Reciben una hora lógica derivada; la marca original no cambia."],
      ["Eventos de comunicación", data.incidents.communication.length, "Se conservan como eventos; no son mediciones ni rellenan huecos."],
      ["Horas de sensor congelado", data.summary.sensor_flat_hours, "La hora completa queda fuera de la comparación; la fila se conserva."]];
    $("quality-facts").replaceChildren(...facts.map(([label, value, treatment]) => row([label, fmt(value), treatment], [1])));
    $("tag-rows").replaceChildren(...data.tags.map(item => row([item.tag, item.description, item.unit])));

    $("alarm-lead").textContent = "El generador sortea cuándo empieza cada episodio de degradación y cuánto crece: el año demo tiene " +
      fmt(data.events.length) + ". La regla compara cada hora con horas de carga y ambiente parecidos del período de referencia; la alarma de prioridad alta detecta " +
      fmt(detected) + ".";
    $("event-buttons").replaceChildren(...data.events.map((event, index) => {
      const button = document.createElement("button");
      button.type = "button"; button.textContent = "Episodio " + event.id; button.setAttribute("aria-pressed", String(index === eventIndex));
      button.addEventListener("click", () => {eventIndex = index; alarms().catch(showError);});
      return button;
    }));
    $("event-rows").replaceChildren(...data.events.map(event => {
      const tr = row(["Episodio " + event.id, stamp(event.trip_time), fmt(event.severity, 2), fmt(event.winding_rise_delta_c, 1) + " °C",
        fmt(event.current_spread_delta_pct, 1) + " pp", event.detected ? "Detectado" : "No detectado",
        hoursText(event.lead_hours), hoursText(event.lead_hours_any_priority)], [2, 3, 4, 6, 7]);
      const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = "en la gráfica"; tr.children[0].append(" ", tag);
      return tr;
    }));
    const alarmsSummary = data.summary.alarms, settings = alarmsSummary.settings;
    const held = alarmsSummary.after_reference, plain = alarmsSummary.after_reference_without_deadband, normal = alarmsSummary.normal_operation;
    $("alarm-settings").textContent = "La alarma se anuncia tras " + fmt(settings.on_delay_hours) + " horas seguidas por encima del percentil " +
      fmt(settings.percentile) + " de su celda. Se repone cuando el indicador baja de umbral − " + fmt(settings.deadband.winding_rise_c, 1) +
      " °C (elevación térmica) o umbral − " + fmt(settings.deadband.current_spread_pct, 1) + " pp (dispersión): esa banda muerta evita que oscile alrededor del umbral.";
    $("alarm-caption").textContent = "Año demo desde el fin de la referencia · " + fmt(held.eligible_hours) + " horas elegibles";
    $("alarm-rows").replaceChildren(...held.points.map(item => row([item.tag, item.description, item.priority, fmt(item.activations),
      fmt(item.activations_per_1000h, 2), fmt(item.fleeting), fmt(item.stale), fmt(item.repeats)], [3, 4, 5, 6, 7])));
    $("deadband-effect").textContent = "Sin banda muerta estas alarmas se activan " + fmt(plain.activations) + " veces y se reactivan " +
      fmt(plain.repeats) + " veces en menos de 6 h; con banda muerta, " + fmt(held.activations) + " y " + fmt(held.repeats) +
      ". Fuera de los episodios hay " + fmt(normal.activations) + " activaciones, " + fmt(normal.activations_by_priority.alta) + " de prioridad alta.";

    $("eval-lead").textContent = "El percentil y el retardo se eligieron con " + fmt(protocol.calibration_seeds.length) +
      " años simulados y el desempeño se midió una vez con otros " + fmt(years) +
      ". El detector no recibe la lista de episodios: la comparación con la verdad se hace después.";
    const tiles = [["Episodios detectados", pct(primary.detection_rate), "IC 95 %: " + span(primary.ci95.detection_rate, 100) + " % · " + fmt(primary.detected) + " de " + fmt(primary.events)],
      ["Falsas alarmas por 1000 h", fmt(primary.false_alarms_per_1000h, 2), "IC 95 %: " + span(primary.ci95.false_alarms_per_1000h, 1, 2)],
      ["Anticipación mediana", hoursText(primary.lead_hours_median), "IC 95 %: " + span(primary.ci95.lead_hours_median) + " h"],
      ["Detección con umbral fijo", pct(fixed.detection_rate), "IC 95 %: " + span(fixed.ci95.detection_rate, 100) + " %"]];
    $("eval-tiles").replaceChildren(...tiles.map(([label, value, note]) => {
      const box = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"), small = document.createElement("small");
      box.className = "tile"; dt.textContent = label; dd.textContent = value; small.textContent = note; dd.append(small); box.append(dt, dd);
      return box;
    }));
    $("method-rows").replaceChildren(...Object.entries(results).map(([key, item]) => row([methodNames[key], pct(item.detection_rate),
      span(item.ci95.detection_rate, 100) + " %", fmt(item.false_alarms_per_1000h, 2), span(item.ci95.false_alarms_per_1000h, 1, 2),
      hoursText(item.lead_hours_median), fmt(item.lead_hours_p10) + " – " + fmt(item.lead_hours_p90) + " h"], [1, 2, 3, 4, 5, 6])));
    const gap = evaluation.primary_minus_baseline, low = gap.ci95.detection_rate[0];
    $("eval-verdict").textContent = "Con los mismos años, condicionar el umbral detecta " + fmt(100 * gap.detection_rate) +
      " puntos más que un umbral fijo (IC 95 %: " + span(gap.ci95.detection_rate, 100) + "), con " + fmt(gap.false_alarms_per_1000h, 2) +
      " falsas alarmas más por 1000 h. " + (low > 0 ? "El intervalo excluye el cero. " : "El intervalo incluye el cero: no se distingue una ventaja. ") +
      "Condicionar solo por carga, sin el ambiente, detecta el " + pct(results.load.detection_rate) + " con " +
      fmt(results.load.false_alarms_per_1000h, 2) + " falsas alarmas por 1000 h.";
    const grid = evaluation.sensitivity, fixedGrid = grid.filter(item => item.method === "none");
    $("sensitivity-rows").replaceChildren(...grid.filter(item => item.method === "load_ambient").map(item => {
      const other = fixedGrid.find(base => base.percentile === item.percentile && base.on_delay_hours === item.on_delay_hours);
      const tr = row(["P" + fmt(item.percentile, item.percentile % 1 ? 1 : 0), fmt(item.on_delay_hours) + " h", pct(item.detection_rate),
        fmt(item.false_alarms_per_1000h, 2), hoursText(item.lead_hours_median), pct(other.detection_rate)], [1, 2, 3, 4, 5]);
      if (item.percentile === point.percentile && item.on_delay_hours === point.on_delay_hours) {
        tr.classList.add("is-active"); tr.setAttribute("aria-current", "true");
        const tag = document.createElement("span"); tag.className = "tag"; tag.textContent = "elegida"; tr.children[0].append(" ", tag);
      }
      return tr;
    }));
    $("severity-note").textContent = "En el tramo de menor severidad se detecta el " + pct(bands[0].detection_rate) +
      " de los episodios; en el de mayor, el " + pct(bands.at(-1).detection_rate) + ". En el 80 % central de los episodios detectados la alarma se adelanta entre " +
      fmt(primary.lead_hours_p10) + " y " + fmt(primary.lead_hours_p90) + " h.";
    const review = evaluation.alarm_review.with_deadband, bare = evaluation.alarm_review.without_deadband, any = evaluation.any_priority;
    $("review-caption").textContent = "Años de evaluación, desde el fin de la referencia · " + fmt(review.eligible_hours) + " horas elegibles";
    $("review-rows").replaceChildren(...review.points.map((item, index) => row([item.tag, item.priority, fmt(item.activations),
      fmt(1000 * item.activations / review.eligible_hours, 2), fmt(item.fleeting), fmt(item.stale), fmt(item.repeats), fmt(bare.points[index].repeats)], [2, 3, 4, 5, 6, 7])));
    $("review-note").textContent = "En total, " + fmt(review.activations_per_hour, 3) + " activaciones por hora para esta unidad; la referencia habitual de ISA-18.2 es de hasta unas 12 por hora por operador para toda la planta. El " +
      pct(review.high_priority_share) + " de las activaciones es de prioridad alta. Si la prioridad baja contara como detección se detectaría el " +
      pct(any.detection_rate) + " de los episodios, con " + fmt(any.false_alarms_per_1000h, 2) + " falsas alarmas por 1000 h.";
    $("eval-rule").textContent = "Con " + fmt(protocol.calibration_seeds.length) + " semillas de calibración se eligió la combinación con mayor detección y como máximo " +
      fmt(protocol.false_alarm_budget_per_1000h) + " falsa alarma por 1000 h: percentil " + fmt(point.percentile) + " y " + fmt(point.on_delay_hours) +
      " h de retardo. Esa configuración se aplicó después a " + fmt(years) + " semillas distintas.";
  }
  function severityTraces(size) {
    return methods.map(([key, name, slot]) => {
      const bands = data.evaluation.evaluation[key].by_severity;
      return trace(bands.map(item => fmt(item.severity_from, 2) + "–" + fmt(item.severity_to, 2)), bands.map(item => item.detection_rate == null ? null : 100 * item.detection_rate),
        name, colors[slot], {mode: "lines+markers", customdata: bands.map(item => item.events),
          marker: {size, symbol: shapes[slot], color: colors[slot], line: {width: 2, color: colors.panel}},
          hovertemplate: "Severidad %{x}<br>%{y:.0f} % de %{customdata} episodios<extra>%{fullData.name}</extra>"});
    });
  }
  async function overview() {
    const r = data.relationships.reference;
    // Un episodio de tamaño intermedio: el más cercano a la mediana de severidad del año demo.
    const sorted = [...data.events].sort((one, two) => one.severity - two.severity);
    const example = sorted[Math.floor((sorted.length - 1) / 2)], t = example.timeline.filter(item => item.eligible);
    $("overview-event-caption").textContent = "Una falla del año demo: la alarma alta se activó " + hoursText(example.lead_hours) + " antes del disparo";
    if (!example.detected) $("overview-event-caption").textContent = "Una falla del año demo que la alarma alta no detectó";
    const winding = item => (item.winding_temperature_a_c + item.winding_temperature_b_c + item.winding_temperature_c_c) / 3;
    const alarmed = t.filter(item => item.alarm_high);
    await Promise.all([
      plot("overview-thermal", [trace(r.map(item => item.active_power_kw), r.map(winding), "Temperatura del devanado", colors.series,
        {mode: "markers", marker: {size: 5, color: colors.series, opacity: .55}, hovertemplate: "%{x:.0f} kW · %{y:.1f} °C<extra></extra>"})], mini("Potencia activa (kW)", "Devanado (°C)"), true),
      plot("overview-event", [trace(t.map(item => item.hours_to_trip), t.map(item => item.winding_rise_c), "Elevación térmica", colors.series,
          {hovertemplate: "%{x} h · %{y:.1f} °C<extra>Elevación térmica</extra>"}),
        trace(t.map(item => item.hours_to_trip), t.map(item => item.winding_rise_c_threshold), "Umbral", colors.context,
          {line: {color: colors.context, dash: "dash", width: 1.5}, hovertemplate: "%{x} h · %{y:.1f} °C<extra>Umbral</extra>"}),
        trace(alarmed.map(item => item.hours_to_trip), alarmed.map(item => item.winding_rise_c), "Alarma alta", colors.alert,
          {mode: "markers", marker: {size: 7, symbol: "diamond", color: colors.alert}, hovertemplate: "%{x} h<extra>Alarma alta</extra>"})],
        mini("Horas antes del disparo", "Elevación (°C)"), true),
      plot("overview-eval", severityTraces(8), mini("Tamaño de la falla (severidad)", "Detectadas (%)", {yaxis: axis("Detectadas (%)", {range: [0, 100]})}), true)
    ]);
  }
  async function variables() {
    const key = $("relationship-period").value, rows = data.relationships[key];
    const selected = [...document.querySelectorAll("[data-phase]:checked")].map(input => input.dataset.phase);
    $("phase-empty").hidden = selected.length > 0;
    $("current-chart").hidden = selected.length === 0;
    $("relationship-range").textContent = rows.length ? dateLabel(rows[0].t) + " — " + dateLabel(rows.at(-1).t) + " · " + fmt(rows.length) + " horas elegibles" : "Sin observaciones elegibles en este período";
    const x = rows.map(item => item.active_power_kw);
    const custom = rows.map(item => [item.t.replace("T", " ").slice(0, 16), item.reactive_power_kvar, item.mean_voltage_v]);
    // Símbolos huecos: las fases que coinciden siguen viéndose una sobre otra.
    const open = (phase, size) => ({color: colors[phase], symbol: shapes[phase] + "-open", size, line: {width: 1.6, color: colors[phase]}});
    if (selected.length) await plot("current-chart", selected.map(phase => trace(x, rows.map(item => item["phase_current_" + phase]), "Fase " + phase.toUpperCase(), colors[phase],
      {mode: "markers", customdata: custom, marker: open(phase, 8),
        hovertemplate: "%{customdata[0]}<br>P: %{x:.1f} kW<br>I: %{y:.2f} A<br>Q: %{customdata[1]:.1f} kvar<br>Tensión media: %{customdata[2]:.0f} V<extra>%{fullData.name}</extra>"})), layout("Potencia activa · G1_P (kW)", "Corriente (A)"));
    const absolute = $("thermal-mode").value === "absolute";
    $("thermal-key").hidden = !absolute;
    const traces = absolute ? ["a", "b", "c"].map(phase => trace(x, rows.map(item => item["winding_temperature_" + phase + "_c"]), "Devanado " + phase.toUpperCase(), colors[phase],
      {mode: "markers", marker: open(phase, 7), customdata: custom,
        hovertemplate: "%{customdata[0]}<br>%{x:.1f} kW · %{y:.2f} °C<extra>%{fullData.name}</extra>"})) : [trace(x, rows.map(item => item.winding_rise_c), "Elevación media", colors.series,
      {mode: "markers", marker: {color: colors.series, size: 7, opacity: .7, line: {width: 1, color: colors.panel}}, customdata: custom, hovertemplate: "%{customdata[0]}<br>%{x:.1f} kW · %{y:.2f} °C<extra></extra>"})];
    if (absolute) traces.push(trace(x, rows.map(item => item.room_temperature_c), "Ambiente", colors.context, {mode: "markers", marker: {color: colors.context, symbol: "cross", size: 6}, hovertemplate: "%{x:.1f} kW · %{y:.2f} °C<extra>Ambiente</extra>"}));
    await plot("thermal-chart", traces, layout("Potencia activa · G1_P (kW)", absolute ? "Temperatura (°C)" : "Elevación sobre el ambiente (°C)"));
  }
  async function quality() {
    const c = data.coverage, x = c.map(item => item.t);
    await plot("coverage-chart", [["preserved", "Filas de medición conservadas", colors.series3, "dot"], ["selected", "Horas seleccionadas", colors.series2, "solid"], ["eligible", "Horas elegibles", colors.series, "dash"]].map(([key, name, color, dash]) =>
      trace(x, c.map(item => item[key]), name, color, {line: {color, width: 2, dash}, hovertemplate: "%{y} registros u horas<extra>%{fullData.name}</extra>"})), layout("2025", "Conteo diario", {hovermode: "x unified", xaxis: axis("2025", {hoverformat: "%d/%m/%Y"})}));
    const sensor = data.sensor.rows;
    await plot("sensor-chart", [["bearing_temperature_a_c", "Cojinete A", colors.a, "solid"], ["bearing_temperature_b_c", "Cojinete B", colors.b, "dash"], ["room_temperature_c", "Ambiente", colors.context, "dot"]].map(([key, name, color, dash]) =>
      trace(sensor.map(item => item.t), sensor.map(item => item[key]), name, color, {line: {color, width: 2, dash}, hovertemplate: "%{y:.2f} °C<extra>%{fullData.name}</extra>"})),
      layout("", "Temperatura (°C)", {hovermode: "x unified", margin: {l: 56, r: 16, t: 56, b: 52}, xaxis: axis("", {tickformat: "%H:%M<br>%-d %b", hoverformat: "%d/%m %H:%M"}),
        shapes: [{type: "rect", xref: "x", yref: "paper", x0: data.sensor.start, x1: data.sensor.end_exclusive, y0: 0, y1: 1, fillcolor: colors.context, opacity: .14, line: {width: 0}}],
        annotations: [{xref: "x", yref: "paper", x: data.sensor.start, y: 1, xanchor: "left", yanchor: "bottom", showarrow: false, font: {size: 12, color: colors.text},
          text: "Lectura congelada · " + fmt(data.summary.sensor_flat_hours) + " h"}]}));
  }
  async function alarms() {
    const event = data.events[eventIndex], rows = event.timeline;
    [...$("event-buttons").children].forEach((button, index) => button.setAttribute("aria-pressed", String(index === eventIndex)));
    [...$("event-rows").children].forEach((tr, index) => {const current = index === eventIndex; tr.classList.toggle("is-active", current); if (current) tr.setAttribute("aria-current", "true"); else tr.removeAttribute("aria-current");});
    $("event-range").textContent = "Rampa de " + fmt(event.ramp_hours) + " h desde el " + stamp(event.ramp_start) + " · disparo el " + stamp(event.trip_time);
    const narrow = $("alarm-chart").offsetWidth < 520;
    const metrics = [["winding_rise_c", "Elevación térmica (°C)"], ["current_spread_pct", "Dispersión de corriente (%)"], ["voltage_spread_pct", "Dispersión de tensión (%)"]];
    const traces = [], annotations = [], settings = layout("Horas respecto del disparo (0)", "", {margin: {l: 52, r: 16, t: 56, b: 56}, shapes: [], annotations});
    metrics.forEach(([key, title], index) => {
      const axisName = index ? "y" + (index + 1) : "y", axisKey = index ? "yaxis" + (index + 1) : "yaxis";
      const domain = [[.73, 1], [.365, .635], [0, .27]][index];
      settings[axisKey] = {domain, gridcolor: colors.grid, tickfont: {size: 12, color: colors.muted}, zeroline: false, automargin: true};
      annotations.push({xref: "paper", yref: "paper", x: 0, y: domain[1], xanchor: "left", yanchor: "bottom", text: "<b>" + title + "</b>", showarrow: false, font: {size: 12, color: colors.ink}});
      const x = rows.map(item => item.hours_to_trip), tooltip = "%{x} h · %{y:.2f}" + (index ? " %" : " °C") + "<extra>%{fullData.name}</extra>";
      traces.push(trace(x, rows.map(item => item.eligible ? item[key] : null), "Indicador", colors.series, {yaxis: axisName, hovertemplate: tooltip}));
      traces.push(trace(x, rows.map(item => item.eligible ? item[key + "_threshold"] : null), "Umbral", colors.context, {yaxis: axisName, line: {color: colors.context, dash: "dash", width: 1.5}, hovertemplate: tooltip}));
      const alerts = rows.filter(item => item.alarm_high);
      traces.push(trace(alerts.map(item => item.hours_to_trip), alerts.map(item => item[key]), "Alarma alta", colors.alert, {yaxis: axisName, mode: "markers", cliponaxis: false, marker: {size: narrow ? 7 : 9, symbol: "diamond", color: colors.alert, line: {width: narrow ? 1 : 1.5, color: colors.panel}}, hovertemplate: tooltip}));
    });
    settings.xaxis = {...settings.xaxis, anchor: "y3", range: [-(event.ramp_hours + 24), 1]};
    settings.shapes = [{type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: {color: colors.ink, width: 1.5}},
      {type: "line", xref: "x", yref: "paper", x0: -event.ramp_hours, x1: -event.ramp_hours, y0: 0, y1: 1, line: {color: colors.context, width: 1.5}}];
    annotations.push({xref: "x", yref: "paper", x: 0, y: 1, xanchor: "right", yanchor: "bottom", xshift: 4, text: "Disparo", showarrow: false, font: {size: 12, color: colors.ink}});
    await plot("alarm-chart", traces, settings);
  }
  async function evaluationView() {
    const evaluation = data.evaluation, point = evaluation.operating_point, budget = evaluation.protocol.false_alarm_budget_per_1000h;
    const label = "P" + fmt(point.percentile) + " · " + fmt(point.on_delay_hours) + " h";
    const operating = [];
    methods.forEach(([key, name, slot]) => {
      const rows = evaluation.sensitivity.filter(item => item.method === key), chosen = evaluation.evaluation[key];
      const marker = size => ({size, symbol: shapes[slot], color: colors[slot], line: {width: 2, color: colors.panel}});
      operating.push(trace(rows.map(item => item.false_alarms_per_1000h), rows.map(item => 100 * item.detection_rate), name, colors[slot],
        {mode: "markers", marker: marker(10), customdata: rows.map(item => [item.percentile, item.on_delay_hours, item.lead_hours_median]),
          hovertemplate: "P%{customdata[0]} · %{customdata[1]} h de retardo<br>Detección: %{y:.0f} %<br>Falsas alarmas: %{x:.2f} por 1000 h<br>Anticipación mediana: %{customdata[2]:.0f} h<extra>%{fullData.name}</extra>"}));
      operating.push(trace([chosen.false_alarms_per_1000h], [100 * chosen.detection_rate], name, colors[slot],
        {mode: "markers+text", text: [label], textposition: "middle right", textfont: {size: 12, color: colors.ink}, marker: marker(16), cliponaxis: false,
          error_y: {type: "data", symmetric: false, array: [100 * (chosen.ci95.detection_rate[1] - chosen.detection_rate)],
            arrayminus: [100 * (chosen.detection_rate - chosen.ci95.detection_rate[0])], color: colors[slot], thickness: 1.5, width: 5},
          hovertemplate: "Configuración elegida: " + label + "<br>Detección: %{y:.0f} %<br>Falsas alarmas: %{x:.2f} por 1000 h<extra>%{fullData.name}</extra>"}));
    });
    const furthest = Math.max(budget, ...evaluation.sensitivity.map(item => item.false_alarms_per_1000h));
    await plot("operating-chart", operating, layout("Falsas alarmas por 1000 h de operación normal", "Episodios detectados (%)", {
      xaxis: axis("Falsas alarmas por 1000 h de operación normal", {range: [-.04 * furthest, 1.12 * furthest]}),
      yaxis: axis("Episodios detectados (%)", {range: [0, 100]}),
      shapes: [{type: "line", xref: "x", yref: "paper", x0: budget, x1: budget, y0: 0, y1: 1, line: {color: colors.context, width: 1.5, dash: "dash"}}]}));
    await plot("severity-chart", severityTraces(10), layout("Severidad del episodio (1 = incremento máximo simulado)", "Episodios detectados (%)",
      {yaxis: axis("Episodios detectados (%)", {range: [0, 100]}), xaxis: axis("Severidad del episodio (1 = incremento máximo simulado)", {type: "category"})}));
    const median = evaluation.evaluation.load_ambient.lead_hours_median;
    await plot("lead-chart", [{type: "histogram", x: evaluation.lead_hours, name: "Episodios detectados", xbins: {start: 0, size: 12},
      marker: {color: colors.series, line: {color: colors.panel, width: 2}}, hovertemplate: "%{x} h<br>%{y} episodios<extra></extra>"}],
      layout("Horas de anticipación", "Episodios detectados", {bargap: 0,
        shapes: median == null ? [] : [{type: "line", xref: "x", yref: "paper", x0: median, x1: median, y0: 0, y1: 1, line: {color: colors.ink, width: 1.5}}],
        annotations: median == null ? [] : [{xref: "x", yref: "paper", x: median, y: 1, xanchor: "left", yanchor: "bottom", xshift: 4, showarrow: false,
          font: {size: 12, color: colors.ink}, text: "Mediana: " + fmt(median) + " h"}]}));
  }
  async function render() {
    if (active === "resumen") await overview();
    if (active === "variables") await variables();
    if (active === "calidad") await quality();
    if (active === "alarmas") await alarms();
    if (active === "evaluacion") await evaluationView();
  }
  async function load() {
    data = null; $("load-error").hidden = true; $("load-status").hidden = false; $("load-status").classList.remove("loaded");
    $("load-status").textContent = "Cargando datos…";
    try {
      if (!window.Plotly) throw new Error("No se pudo cargar la biblioteca local de gráficos.");
      Plotly.register({moduleType: "locale", name: "es-local", dictionary: {"Zoom": "Ampliar", "Pan": "Desplazar", "Reset axes": "Restablecer ejes"}, format: {days: ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"], shortDays: ["dom","lun","mar","mié","jue","vie","sáb"], months: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"], shortMonths: ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"], decimal: ",", thousands: ".", grouping: [3], date: "%d/%m/%Y"}});
      const response = await fetch("assets/dashboard-data.json", {cache: "no-cache"});
      if (!response.ok) throw new Error("No se pudo leer el archivo de datos. Sirve docs/ mediante HTTP y comprueba assets/dashboard-data.json.");
      const payload = await response.json();
      if (payload.schema_version !== 2 || payload.synthetic_only !== true || !Array.isArray(payload.events) || !Array.isArray(payload.coverage) || !payload.summary || !payload.relationships || !payload.evaluation) throw new Error("El archivo de datos no corresponde a esta versión del explorador.");
      data = payload; eventIndex = 0; populate(); await render();
      $("load-status").classList.add("loaded"); $("load-status").textContent = "Año demo 2025 · semilla " + data.seed;
    } catch (error) { showError(error); }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => go(tab.getAttribute("aria-controls")));
    tab.addEventListener("keydown", event => {let next = null; if (event.key === "ArrowRight") next = (index + 1) % tabs.length; if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length; if (event.key === "Home") next = 0; if (event.key === "End") next = tabs.length - 1; if (next !== null) {event.preventDefault(); go(tabs[next].getAttribute("aria-controls"), true);}});
  });
  document.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => {go(button.dataset.go, true); $("main").scrollIntoView({behavior: "auto"});}));
  document.querySelector(".brand").addEventListener("click", event => {event.preventDefault(); go("resumen");});
  [$("relationship-period"), $("thermal-mode"), ...document.querySelectorAll("[data-phase]")].forEach(control => control.addEventListener("change", () => {if (data) variables().catch(showError);}));
  keys.forEach(key => key.addEventListener("click", () => {
    key.setAttribute("aria-pressed", String(key.getAttribute("aria-pressed") !== "true"));
    const chart = $(key.dataset.chart), indices = (chart.data || []).flatMap((item, index) => item.name === key.dataset.series ? [index] : []);
    if (indices.length) Plotly.restyle(chart, {visible: shown(key)}, indices);
  }));
  document.querySelectorAll("[data-reset]").forEach(button => button.addEventListener("click", async () => {const id = button.dataset.reset, saved = drawings.get(id); if (saved) {await Plotly.purge($(id)); await plot(id, saved.traces, saved.settings, saved.small);}}));
  document.querySelectorAll("[data-zoom]").forEach(button => button.addEventListener("click", () => {const chart = $(button.dataset.zoom); if (!chart._fullLayout || chart.hidden) return; const changes = {}; for (const axis of ["xaxis", "yaxis"]) {const [lo, hi] = chart._fullLayout[axis].range; const mid = (lo + hi) / 2; changes[axis + ".range"] = [mid - (hi - lo) / 4, mid + (hi - lo) / 4];} Plotly.relayout(chart, changes);}));
  $("retry").addEventListener("click", load);
  window.addEventListener("hashchange", () => go(location.hash.slice(1)));
  go(location.hash.slice(1) || "resumen"); load();
})();
