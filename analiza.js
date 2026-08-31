/* Analiza podataka — Pokrivenost senkom.
 * Čita data/shade_canopy.json (shade_canopy.py): za svaku tačku svake od tri
 * staze (10 m) bitmask sunce/senka po satu, za 4 referentna dana. Renderuje
 * heat-mapu km × sat (canvas) i mapu sa stazom obojenom po stanju u satu.
 * Kilometraža je zajednička (projektovana na biciklističku osu), pa se staze
 * porede direktno.
 */
"use strict";

const DATA = "data/";

const COL_SUN_CELL = "#f0d684";   // heat-mapa: veće površine, mekši ton (kao strip na početnoj)
const COL_SHADE = "#2f6b46";
const COL_NIGHT = "#e7e4dc";
const COL_SUN_LINE = "#d8a93a";   // mapa: linija na svetloj podlozi traži jači ton

const STAZA_SHORT = {
  bici: "Biciklistička",
  pesacki_gornji: "Pešačka — gornji bedem",
  pesacki_donji: "Pešačka — donji bedem",
};

let D = null;                     // ceo dataset
let S = null;                     // izabrana staza
const state = { staza: "bici", date: "jun21", hour: 13, mode: "hour" };

function $(id) { return document.getElementById(id); }

function dateCfg(key) { return D.dates.find(d => d.key === key); }

function shortLabel(key) {
  return { mar21: "21. mart", jun21: "21. jun", sep21: "21. septembar", dec21: "21. decembar" }[key] || key;
}

/* Sunce u tački i (bit HOURS indeksa), null = van dnevne svetlosti. */
function sunState(dateKey, i, hour) {
  const cfg = dateCfg(dateKey);
  if (!cfg.daylight.includes(hour)) return null;
  const hi = D.hours.indexOf(hour);
  return (S.masks[dateKey][i] >> hi) & 1;
}

function sunHours(dateKey, i) {
  let m = S.masks[dateKey][i], n = 0;
  while (m) { n += m & 1; m >>= 1; }
  return n;
}

/* Indeks tačke najbliže kilometraži k. Niz je sortiran ali nije ekvidistantan
 * (pešačke staze imaju prekide), pa ne može prosto k / step. */
function nearestIndex(km, k) {
  let lo = 0, hi = km.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (km[mid] < k) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(km[lo - 1] - k) <= Math.abs(km[lo] - k)) return lo - 1;
  return lo;
}

/* ---------- stat kartice ---------- */

function renderStats() {
  const t = S.totals;
  const tiles = [
    { val: t.canopy_pct, unit: "%", label: "Staze uz drvored",
      sub: "krošnja ≥ 3 m na najviše 10 m od staze" },
    { val: t.pct_shade.jun21, unit: "%", label: "U senci — 21. jun",
      sub: `prosek preko dana (${dateCfg("jun21").daylight[0]}–${dateCfg("jun21").daylight.at(-1)}h)` },
    { val: t.pct_shade.dec21, unit: "%", label: "U senci — 21. decembar",
      sub: "nisko sunce = najduže senke" },
    { val: t.canopy_avg_h, unit: "m", label: "Prosečna visina krošnje",
      sub: "tamo gde drveća ima" },
    { val: t.continuity.longest_gap_m, unit: " m", label: "Najduža rupa bez drvoreda",
      sub: "neprekinuta zona izloženosti suncu", warn: t.continuity.longest_gap_m >= 1000 },
    { val: t.continuity.longest_m, unit: " m", label: "Najduži deo uz drvored",
      sub: `${t.continuity.transitions} prelaza drvored ↔ otvoreno` },
  ];
  $("senka-stats").innerHTML = tiles.map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.val}<span class="unit">${x.unit}</span></div>
      <div class="shade-stat-label">${x.label}</div>
      <div class="shade-stat-sub">${x.sub}</div>
    </div>`).join("");
}

/* ---------- heat-mapa km × sat ---------- */

const HM = { padL: 44, padR: 10, padT: 26, padB: 24, cellH: 20 };

function heatmapGeometry(canvas) {
  const wrapW = canvas.parentElement.clientWidth;
  const rows = D.hours.length;
  return {
    w: wrapW,
    h: HM.padT + rows * HM.cellH + HM.padB,
    plotW: wrapW - HM.padL - HM.padR,
    rows,
  };
}

function drawHeatmap() {
  const canvas = $("senka-heatmap");
  const g = heatmapGeometry(canvas);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = g.w * dpr;
  canvas.height = g.h * dpr;
  canvas.style.width = g.w + "px";
  canvas.style.height = g.h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, g.w, g.h);

  // x-osa je uvek puna dužina referentne ose — inače se tri staze ne bi
  // poklapale po kilometraži, a rupe u pešačkim stazama bi se sakrile
  const km = S.points.km;
  const totalKm = D.osa_km;
  const xOf = k => HM.padL + (k / totalKm) * g.plotW;
  const colW = Math.max(1, (D.step_m / 1000 / totalKm) * g.plotW + 0.5);

  // ćelije
  for (let i = 0; i < km.length; i++) {
    const x = xOf(km[i]);
    for (let r = 0; r < g.rows; r++) {
      const hour = D.hours[r];
      const s = sunState(state.date, i, hour);
      ctx.fillStyle = s === null ? COL_NIGHT : (s ? COL_SUN_CELL : COL_SHADE);
      // red 0 = najkasniji sat gore
      const y = HM.padT + (g.rows - 1 - r) * HM.cellH;
      ctx.fillRect(x, y, colW, HM.cellH - 1);
    }
  }

  // ose: sati levo
  ctx.fillStyle = "#6b776f";
  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let r = 0; r < g.rows; r++) {
    const hour = D.hours[r];
    if (hour % 2 !== 0) continue;
    const y = HM.padT + (g.rows - 1 - r) * HM.cellH + HM.cellH / 2;
    ctx.fillText(`${String(hour).padStart(2, "0")}h`, HM.padL - 7, y);
  }

  // km osa dole
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const kmStep = totalKm > 12 ? 2 : 1;
  for (let k = 0; k <= Math.floor(totalKm); k += kmStep) {
    ctx.fillText(`${k}`, xOf(k), g.h - HM.padB + 7);
  }
  ctx.textAlign = "left";
  ctx.fillText("km", xOf(Math.floor(totalKm)) + 14, g.h - HM.padB + 7);

  // deonice: granice + imena gore
  ctx.textBaseline = "alphabetic";
  const dIdx = S.points.deonica;
  let start = 0;
  for (let i = 1; i <= km.length; i++) {
    if (i === km.length || dIdx[i] !== dIdx[start]) {
      const x0 = xOf(km[start]);
      const x1 = xOf(km[Math.min(i, km.length - 1)]);
      if (i < km.length) {
        ctx.strokeStyle = "rgba(26,31,27,.35)";
        ctx.beginPath();
        ctx.moveTo(x1, HM.padT - 4);
        ctx.lineTo(x1, HM.padT + g.rows * HM.cellH);
        ctx.stroke();
      }
      const name = D.deonice[dIdx[start]];
      ctx.fillStyle = "#3b4a40";
      ctx.font = "600 10px system-ui, sans-serif";
      ctx.textAlign = "center";
      if (ctx.measureText(name).width < x1 - x0 - 8) {
        ctx.fillText(name.toUpperCase(), (x0 + x1) / 2, HM.padT - 9);
      }
      start = i;
    }
  }
}

function bindHeatmapTooltip() {
  const canvas = $("senka-heatmap");
  const tip = $("heatmap-tooltip");
  const wrap = $("heatmap-wrap");

  function onMove(ev) {
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const g = heatmapGeometry(canvas);
    const km = S.points.km;
    const totalKm = D.osa_km;
    const r = g.rows - 1 - Math.floor((my - HM.padT) / HM.cellH);
    const k = ((mx - HM.padL) / g.plotW) * totalKm;
    if (r < 0 || r >= g.rows || k < 0 || k > totalKm) { tip.hidden = true; return; }
    const i = nearestIndex(km, k);
    // rupa u stazi (npr. donji bedem) — nema šta da se pokaže
    if (Math.abs(km[i] - k) > D.step_m / 1000) { tip.hidden = true; return; }
    const hour = D.hours[r];
    const s = sunState(state.date, i, hour);
    const dn = D.deonice[S.points.deonica[i]];
    const ch = S.points.canopy_h[i];
    tip.querySelector(".tt-state").textContent =
      s === null ? "pre izlaska / posle zalaska sunca"
                 : (s ? "☀ na suncu" : "🌳 u senci drveća");
    tip.querySelector(".tt-meta").textContent =
      `km ${km[i].toFixed(2)} · ${String(hour).padStart(2, "0")}:00 · ${dn}`
      + (ch >= 3 ? ` · krošnja ${ch.toFixed(0)} m` : "");
    tip.hidden = false;
    const tw = tip.offsetWidth;
    let left = mx + 14;
    if (left + tw > g.w - 4) left = mx - tw - 14;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(0, my - 44)}px`;
  }
  wrap.addEventListener("mousemove", onMove);
  wrap.addEventListener("mouseleave", () => { tip.hidden = true; });
}

function buildTabs() {
  const el = $("senka-tabs");
  el.innerHTML = D.dates.map(d =>
    `<button type="button" class="chip${d.key === state.date ? " active" : ""}" data-date="${d.key}">${shortLabel(d.key)}</button>`
  ).join("");
  el.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-date]");
    if (!btn) return;
    state.date = btn.dataset.date;
    el.querySelectorAll(".chip").forEach(c =>
      c.classList.toggle("active", c.dataset.date === state.date));
    syncMapPills();
    clampHourToDaylight();
    drawHeatmap();
    shadeLayer && shadeLayer.redraw();
  });
}

/* ---------- mapa ---------- */

let map = null;
let shadeLayer = null;

const ShadeCanvasLayer = L.Layer.extend({
  onAdd(m) {
    this._map = m;
    this._canvas = document.createElement("canvas");
    this._canvas.style.position = "absolute";
    this._canvas.style.pointerEvents = "none";
    m.getPane("overlayPane").appendChild(this._canvas);
    m.on("move zoomend viewreset resize", this.redraw, this);
    this.redraw();
  },
  onRemove(m) {
    m.off("move zoomend viewreset resize", this.redraw, this);
    this._canvas.remove();
  },
  redraw() {
    if (!this._map) return;
    const m = this._map;
    const size = m.getSize();
    const dpr = window.devicePixelRatio || 1;
    this._canvas.width = size.x * dpr;
    this._canvas.height = size.y * dpr;
    this._canvas.style.width = size.x + "px";
    this._canvas.style.height = size.y + "px";
    L.DomUtil.setPosition(this._canvas, m.containerPointToLayerPoint([0, 0]));
    const ctx = this._canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    ctx.lineWidth = 5;
    ctx.lineCap = "round";

    const { lat, lon, km, chain } = S.points;
    const stepKm = D.step_m / 1000;
    const pts = new Array(km.length);
    for (let i = 0; i < km.length; i++) {
      pts[i] = m.latLngToContainerPoint([lat[i], lon[i]]);
    }
    // tačke su sortirane po zajedničkoj km-osi, pa susedi u nizu mogu biti sa
    // različitih lanaca — crtaj lanac po lanac da se ne spoje udaljene staze
    const byChain = new Map();
    for (let i = 0; i < km.length; i++) {
      if (!byChain.has(chain[i])) byChain.set(chain[i], []);
      byChain.get(chain[i]).push(i);
    }
    for (const idx of byChain.values()) {
      for (let j = 0; j < idx.length - 1; j++) {
        const a = idx[j], b = idx[j + 1];
        if (km[b] - km[a] > stepKm * 1.5) continue;   // prekid u lancu
        ctx.strokeStyle = this._colorFor(a);
        ctx.beginPath();
        ctx.moveTo(pts[a].x, pts[a].y);
        ctx.lineTo(pts[b].x, pts[b].y);
        ctx.stroke();
      }
    }
  },
  _colorFor(i) {
    if (state.mode === "day") {
      const n = dateCfg(state.date).daylight.length;
      const t = sunHours(state.date, i) / n;
      return lerpColor(COL_SHADE, COL_SUN_LINE, t);
    }
    const s = sunState(state.date, i, state.hour);
    if (s === null) return "rgba(107,119,111,.45)";
    return s ? COL_SUN_LINE : COL_SHADE;
  },
});

function lerpColor(a, b, t) {
  const pa = [1, 3, 5].map(o => parseInt(a.slice(o, o + 2), 16));
  const pb = [1, 3, 5].map(o => parseInt(b.slice(o, o + 2), 16));
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function buildMap() {
  // okvir preko svih staza — pogled ne sme da skače pri prebacivanju
  const bounds = L.latLngBounds([]);
  D.staze.forEach(s => s.points.lat.forEach(
    (la, i) => bounds.extend([la, s.points.lon[i]])));
  map = L.map("shade-map", { scrollWheelZoom: false });
  map.fitBounds(bounds, { padding: [18, 18] });
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> · © <a href='https://carto.com/attributions'>CARTO</a>",
    maxZoom: 19,
  }).addTo(map);
  shadeLayer = new ShadeCanvasLayer();
  shadeLayer.addTo(map);
}

/* ---------- kontrole mape ---------- */

function clampHourToDaylight() {
  const dl = dateCfg(state.date).daylight;
  const slider = $("hour-slider");
  slider.min = dl[0];
  slider.max = dl[dl.length - 1];
  if (state.hour < dl[0]) state.hour = dl[0];
  if (state.hour > dl[dl.length - 1]) state.hour = dl[dl.length - 1];
  slider.value = state.hour;
  $("hour-label").textContent = `${String(state.hour).padStart(2, "0")}:00`;
}

function syncMapPills() {
  document.querySelectorAll("#map-date-pills .chip").forEach(c =>
    c.classList.toggle("active", c.dataset.date === state.date));
}

function buildMapControls() {
  const pills = $("map-date-pills");
  pills.innerHTML = D.dates.map(d =>
    `<button type="button" class="chip${d.key === state.date ? " active" : ""}" data-date="${d.key}">${shortLabel(d.key)}</button>`
  ).join("");
  pills.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-date]");
    if (!btn) return;
    state.date = btn.dataset.date;
    syncMapPills();
    document.querySelectorAll("#senka-tabs .chip").forEach(c =>
      c.classList.toggle("active", c.dataset.date === state.date));
    clampHourToDaylight();
    drawHeatmap();
    shadeLayer.redraw();
  });

  const modes = $("map-mode-pills");
  modes.innerHTML = `
    <button type="button" class="chip active" data-mode="hour">Po satu</button>
    <button type="button" class="chip" data-mode="day">Ceo dan</button>`;
  modes.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-mode]");
    if (!btn) return;
    state.mode = btn.dataset.mode;
    modes.querySelectorAll(".chip").forEach(c =>
      c.classList.toggle("active", c.dataset.mode === state.mode));
    $("hour-slider-row").hidden = state.mode === "day";
    const gl = $("gradient-legend");
    gl.hidden = state.mode !== "day";
    if (state.mode === "day") {
      $("gradient-max").textContent = `${dateCfg(state.date).daylight.length} h sunca`;
    }
    shadeLayer.redraw();
  });

  $("hour-slider").addEventListener("input", ev => {
    state.hour = parseInt(ev.target.value, 10);
    $("hour-label").textContent = `${String(state.hour).padStart(2, "0")}:00`;
    shadeLayer.redraw();
  });
  clampHourToDaylight();
}

/* ---------- tabela po deonicama ---------- */

function renderTable() {
  const t = $("senka-table");
  const head = `
    <thead><tr>
      <th>Deonica</th><th>km</th><th>Uz drvored</th><th>Visina krošnje</th>
      <th>Najduža rupa</th>
      ${D.dates.map(d => `<th>${shortLabel(d.key)}</th>`).join("")}
    </tr></thead>`;
  const row = (name, s) => `
    <tr>
      <td>${name}</td>
      <td class="num">${s.km_start !== undefined ? `${s.km_start.toFixed(1)}–${s.km_end.toFixed(1)}` : "0–" + D.osa_km.toFixed(1)}</td>
      <td class="num">${s.canopy_pct}%</td>
      <td class="num">${s.canopy_avg_h ? s.canopy_avg_h + " m" : "—"}</td>
      <td class="num">${s.continuity.longest_gap_m} m</td>
      ${D.dates.map(d => `<td class="num">${s.pct_shade[d.key]}%</td>`).join("")}
    </tr>`;
  // staza ne mora da prolazi kroz svaku deonicu (donji bedem ima prekide)
  const body = D.deonice.filter(dn => S.by_deonica[dn])
    .map(dn => row(dn, S.by_deonica[dn])).join("")
    + row(`<strong>Cela staza</strong>`, S.totals);
  t.innerHTML = head +
    `<tbody>${body}</tbody>` +
    `<tfoot><tr><td colspan="${5 + D.dates.length}" class="muted">„Najduža rupa" je najduži neprekidan deo bez drvoreda uz stazu. Kolone sa datumima: % vremena u senci, prosek preko svih tačaka deonice i sati dnevne svetlosti.</td></tr></tfoot>`;
}

/* ---------- prekidač staza ---------- */

function buildStazaPills() {
  const el = $("staza-pills");
  el.innerHTML = D.staze.map(s =>
    `<button type="button" class="chip${s.tip === state.staza ? " active" : ""}" data-staza="${s.tip}">${STAZA_SHORT[s.tip] || s.label}</button>`
  ).join("");
  el.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-staza]");
    if (!btn) return;
    state.staza = btn.dataset.staza;
    S = D.staze.find(s => s.tip === state.staza);
    el.querySelectorAll(".chip").forEach(c =>
      c.classList.toggle("active", c.dataset.staza === state.staza));
    renderStats();
    drawHeatmap();
    renderTable();
    shadeLayer && shadeLayer.redraw();
  });
}

/* ---------- init ---------- */

async function init() {
  try {
    const r = await fetch(DATA + "shade_canopy.json");
    D = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam shade_canopy.json:", e);
    return;
  }
  S = D.staze.find(s => s.tip === state.staza) || D.staze[0];
  state.staza = S.tip;
  buildStazaPills();
  renderStats();
  buildTabs();
  drawHeatmap();
  bindHeatmapTooltip();
  buildMap();
  buildMapControls();
  renderTable();
  let rt = null;
  window.addEventListener("resize", () => {
    clearTimeout(rt);
    rt = setTimeout(drawHeatmap, 150);
  });
}

document.addEventListener("DOMContentLoaded", init);
