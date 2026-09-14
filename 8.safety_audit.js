/* Analiza 8 — Bezbednosni audit.
 * Čita data/safety.json (safety.py): tamne zone, stanja infrastrukture,
 * saobraćajni konflikti i stepenice po deonici.
 */
"use strict";

const DATA = "data/";

let D = null;

function $(id) { return document.getElementById(id); }

/* ── ključni nalazi ──────────────────────────────────────────── */

function renderNalazi() {
  const t = D.tamne_zone;
  const k = D.konflikti;
  const s = D.stanja;
  const stepMax = Object.entries(D.stepenice_po_deonici.po_deonici)
    .sort((a, b) => b[1] - a[1])[0];

  const tiles = [
    {
      v: t.tamno_pct + " %",
      tekst: "trase nema adekvatno osvetljenje noću — "
        + `najduža tamna zona je <strong>${(t.najduza_zona_m / 1000).toFixed(1)} km</strong>`,
      warn: true,
    },
    {
      v: k.ukupno_parking,
      tekst: "mesta gde vozila parkiraju na stazi ili direktno ometaju kretanje",
      warn: k.ukupno_parking >= 4,
    },
    {
      v: stepMax ? stepMax[1] : "—",
      tekst: stepMax
        ? `stepenica samo u deonici <strong>${stepMax[0]}</strong> — daleko najviše od svih deonica`
        : "stepenica ukupno",
      warn: true,
    },
  ];

  $("nalazi").innerHTML = tiles.map(x => `
    <div class="nalaz${x.warn ? " nalaz-warn" : ""}">
      <p class="nalaz-broj">${x.v}</p>
      <p class="nalaz-tekst">${x.tekst}</p>
    </div>`).join("");
}

/* ── 8.1 stanja timeline ─────────────────────────────────────── */

function renderStanjaTimeline() {
  const totalKm = D.osa_km;
  const tacke = D.stanja.tacke.filter(t => t.km !== null);
  const vrste = ["loše", "srednje", "dobro", "deponija", "ostalo"];

  // legenda — samo vrste koje postoje u podacima
  const prisutne = vrste.filter(v => tacke.some(t => t.stanje === v));
  $("stanja-legenda").innerHTML = prisutne.map(v =>
    `<span class="hl-item"><span class="hl-swatch" style="background:${STANJE_COLOR[v]};border-radius:50%"></span> ${STANJE_LABEL[v]}</span>`
  ).join("");

  // pinovi
  const pinsEl = $("stanja-pins");
  pinsEl.innerHTML = tacke.map(t => {
    const pct = (t.km / totalKm * 100).toFixed(2);
    const col = STANJE_COLOR[t.stanje] || "#888";
    const label = STANJE_LABEL[t.stanje] || t.stanje;
    const km = t.km.toFixed(2);
    const tooltip = `${label} · km ${km}${t.deonica ? " · " + t.deonica : ""}${t.name ? " — " + t.name : ""}`;
    return `
      <div class="stanja-pin" style="left:${pct}%;--pin-color:${col}" title="${tooltip}">
        <div class="stanja-tooltip">${tooltip}</div>
        <div class="pin-dot"></div>
        <div class="pin-line"></div>
      </div>`;
  }).join("");

  // km osa
  const axisEl = $("stanja-axis");
  const marks = [];
  for (let k = 0; k <= Math.floor(totalKm); k += 2) {
    marks.push(`<span style="left:${(k / totalKm * 100).toFixed(1)}%">${k}</span>`);
  }
  axisEl.innerHTML = marks.join("");
}

/* ── stepenice by deonica table ──────────────────────────────── */

function renderStepTable() {
  const data = D.stepenice_po_deonici.po_deonici;
  const max = Math.max(...Object.values(data), 1);
  const el = $("bars-stepenice");

  el.innerHTML = DEONICE_ORDER.filter(dn => data[dn]).map(dn => {
    const v = data[dn];
    const pct = Math.round(v / max * 100);
    const col = colorForCount(v, max);
    return `
      <div class="bar-row">
        <div class="label">${dn}</div>
        <div class="track" style="background:#f0ede8">
          <div class="fill" style="width:${pct}%;background:${col};border-radius:999px"></div>
        </div>
        <div class="value">${v}</div>
      </div>`;
  }).join("");
}

/* ── 8.1 stanja table ────────────────────────────────────────── */

const STANJE_COLOR = {
  "loše":    "#c0392b",
  "srednje": "#e0a03a",
  "dobro":   "#2f6b46",
  "deponija":"#7d3c98",
  "ostalo":  "#6b776f",
};

const STANJE_LABEL = {
  "loše":    "Loše",
  "srednje": "Srednje",
  "dobro":   "Dobro",
  "deponija":"Deponija",
  "ostalo":  "Ostalo",
};

const DEONICE_ORDER = [
  "Medoševac", "Centar", "Delta - Lidl",
  "Gabrovačka Reka", "Brzi Brod", "Niška Banja",
];

function dot(stanje) {
  return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;
    background:${STANJE_COLOR[stanje] || "#aaa"};margin-right:.35em;vertical-align:middle"></span>`;
}

function renderStanjaTable() {
  const bd = D.stanja.po_deonici;
  const pt = D.stanja.po_tipu;
  const vrste = ["loše", "srednje", "dobro", "deponija", "ostalo"];

  const head = `<thead><tr>
    <th>Deonica</th>
    ${vrste.map(v => `<th>${dot(v)}${STANJE_LABEL[v]}</th>`).join("")}
  </tr></thead>`;

  const row = (name, data) => {
    const d = data || {};
    return `<tr>
      <td>${name}</td>
      ${vrste.map(v => `<td class="num">${d[v] || "—"}</td>`).join("")}
    </tr>`;
  };

  const body = DEONICE_ORDER.filter(dn => bd[dn])
    .map(dn => row(dn, bd[dn])).join("")
    + `<tr><td><strong>Ukupno</strong></td>
       ${vrste.map(v => `<td class="num"><strong>${pt[v] || "—"}</strong></td>`).join("")}
       </tr>`;

  $("stanja-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

/* ── stepenice histogram ─────────────────────────────────────── */

const SH = { padL: 44, padR: 12, padT: 10, padB: 26, h: 140 };

function colorForCount(v, max) {
  if (v === 0) return "#e8e5df";
  const t = v / max;
  if (t < 0.25) return "#7fa05c";
  if (t < 0.55) return "#e0a03a";
  return "#c0392b";
}

function drawStepHistogram() {
  const cv = $("stepenice-histogram");
  const wrap = $("stepenice-histogram-wrap");
  const wrapW = wrap.clientWidth;
  const plotW = wrapW - SH.padL - SH.padR;
  const plotH = SH.h - SH.padT - SH.padB;
  const dpr = window.devicePixelRatio || 1;
  cv.width = wrapW * dpr;
  cv.height = SH.h * dpr;
  cv.style.width = wrapW + "px";
  cv.style.height = SH.h + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, wrapW, SH.h);

  const bins = D.stepenice_po_deonici.histogram || [];
  const totalKm = D.osa_km;
  const max = Math.max(...bins.map(b => b.count), 1);

  const xOf = km => SH.padL + (km / totalKm) * plotW;
  const yOf = v  => SH.padT + plotH * (1 - v / max);

  // gridlines
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#6b776f";
  [0, Math.round(max / 2), max].forEach(v => {
    ctx.strokeStyle = v === 0 ? "#d8ddd6" : "rgba(168,177,171,.4)";
    ctx.beginPath();
    ctx.moveTo(SH.padL, yOf(v));
    ctx.lineTo(SH.padL + plotW, yOf(v));
    ctx.stroke();
    ctx.fillText(String(v), SH.padL - 5, yOf(v));
  });

  // bars
  for (const bin of bins) {
    if (bin.count === 0) continue;
    const x = xOf(bin.km_od);
    const w = xOf(bin.km_do) - x - 1;
    const y = yOf(bin.count);
    ctx.fillStyle = colorForCount(bin.count, max);
    ctx.fillRect(x, y, w, yOf(0) - y);
  }

  // km axis
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillStyle = "#6b776f";
  for (let k = 0; k <= Math.floor(totalKm); k += 2) {
    ctx.fillText(k + " km", xOf(k), yOf(0) + 7);
  }
}

function bindStepTooltip() {
  const wrap = $("stepenice-histogram-wrap");
  const tip  = $("stepenice-tooltip");
  const bins = D.stepenice_po_deonici.histogram || [];
  const totalKm = D.osa_km;

  wrap.addEventListener("mousemove", ev => {
    const wrapW = wrap.clientWidth;
    const plotW = wrapW - SH.padL - SH.padR;
    const r = wrap.getBoundingClientRect();
    const mx = ev.clientX - r.left;
    if (mx < SH.padL || mx > SH.padL + plotW) { tip.hidden = true; return; }
    const km = ((mx - SH.padL) / plotW) * totalKm;
    const bin = bins.find(b => km >= b.km_od && km <= b.km_do);
    if (!bin) { tip.hidden = true; return; }
    tip.querySelector(".tt-state").textContent =
      bin.count === 0 ? "Nema stepenica" : `${bin.count} stepenica`;
    tip.querySelector(".tt-meta").textContent =
      `km ${bin.km_od.toFixed(1)}–${bin.km_do.toFixed(1)}`;
    tip.hidden = false;
    const tw = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(mx - tw / 2, wrapW - tw - 4)) + "px";
    tip.style.top = "4px";
  });
  wrap.addEventListener("mouseleave", () => { tip.hidden = true; });
}

/* ── 8.2 tamne zone strip ────────────────────────────────────── */

function buildLightingSegments() {
  const totalKm = D.osa_km;
  const dark = [...D.tamne_zone.zone].sort((a, b) => a.km_od - b.km_od);
  const segs = [];
  let pos = 0;

  for (const z of dark) {
    if (z.km_od > pos + 0.001) {
      segs.push({ km_od: pos, km_do: z.km_od, lit: true });
    }
    segs.push({ km_od: z.km_od, km_do: z.km_do, lit: false, deonica: z.deonica });
    pos = z.km_do;
  }
  if (pos < totalKm - 0.001) {
    segs.push({ km_od: pos, km_do: totalKm, lit: true });
  }
  return segs;
}

function renderDarkStrip() {
  const totalKm = D.osa_km;
  const segs = buildLightingSegments();
  const strip = $("tamne-strip");

  strip.innerHTML = segs.map(s => {
    const pct = ((s.km_do - s.km_od) / totalKm * 100).toFixed(2);
    const bg = s.lit ? "#f0d684" : "#2c2c2c";
    const title = s.lit
      ? `Osvetljeno: km ${s.km_od.toFixed(1)}–${s.km_do.toFixed(1)}`
      : `Tamna zona: km ${s.km_od.toFixed(1)}–${s.km_do.toFixed(1)} (${s.km_do - s.km_od < 1 ? Math.round((s.km_do - s.km_od) * 1000) + " m" : ((s.km_do - s.km_od).toFixed(1) + " km")})${s.deonica ? " · " + s.deonica : ""}`;
    return `<span class="strip-seg" style="width:${pct}%;background:${bg}" title="${title}"></span>`;
  }).join("");

  // km axis
  const axis = $("tamne-axis");
  const marks = [];
  for (let k = 0; k <= Math.floor(totalKm); k += 2) {
    marks.push(`<span style="left:${(k / totalKm * 100).toFixed(1)}%">${k}</span>`);
  }
  axis.innerHTML = marks.join("");
}

function renderDarkStats() {
  const t = D.tamne_zone;
  const tiles = [
    { v: t.tamno_pct + " %", label: "trase u tamnoj zoni",
      sub: "razmak između svetiljki > 200 m", warn: true },
    { v: t.broj_zona, label: "tamne zone ukupno",
      sub: `prag: ${t.prag_m} m između svetiljki` },
    { v: (t.najduza_zona_m / 1000).toFixed(1) + " km", label: "najduža tamna zona",
      sub: "bez ijedne svetiljke", warn: true },
    { v: Math.round(t.ukupno_tamnih_m / 1000) + " km", label: "ukupno bez osvetljenja",
      sub: `od ${D.osa_km.toFixed(1)} km trase`, warn: true },
  ];

  $("tamne-stats").innerHTML = tiles.map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.label}</div>
      <div class="shade-stat-sub">${x.sub}</div>
    </div>`).join("");
}

/* ── 8.3 konflikti table ─────────────────────────────────────── */

function renderKonfliktiStats() {
  const k = D.konflikti;
  const tiles = [
    { v: k.ukupno_parking, label: "parking konflikata",
      sub: "parkiranje na stazi, rampe, koso parkiranje", warn: k.ukupno_parking > 0 },
    { v: k.ukupno_prelaza, label: "kritičnih prelaza",
      sub: "most, promena puta, nedostatak pešačkog prelaza", warn: k.ukupno_prelaza > 0 },
  ];

  $("konflikti-stats").innerHTML = tiles.map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.label}</div>
      <div class="shade-stat-sub">${x.sub}</div>
    </div>`).join("");
}

function renderKonfliktiTable() {
  const bd = D.konflikti.po_deonici;

  const head = `<thead><tr>
    <th>Deonica</th>
    <th><span style="color:#e76f1f">●</span> Parking</th>
    <th><span style="color:#c0392b">●</span> Prelaz / ukrštanje</th>
    <th>Ukupno</th>
  </tr></thead>`;

  const row = (name, d) => {
    const p = d.parking || 0;
    const pr = d.prelaz || 0;
    return `<tr>
      <td>${name}</td>
      <td class="num">${p || "—"}</td>
      <td class="num">${pr || "—"}</td>
      <td class="num"><strong>${p + pr}</strong></td>
    </tr>`;
  };

  const totP = D.konflikti.ukupno_parking;
  const totPr = D.konflikti.ukupno_prelaza;

  const body = DEONICE_ORDER.filter(dn => bd[dn])
    .map(dn => row(dn, bd[dn])).join("")
    + `<tr><td><strong>Ukupno</strong></td>
       <td class="num"><strong>${totP}</strong></td>
       <td class="num"><strong>${totPr}</strong></td>
       <td class="num"><strong>${totP + totPr}</strong></td>
       </tr>`;

  $("konflikti-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

/* ── mapa ────────────────────────────────────────────────────── */

function haversineKm(lon1, lat1, lon2, lat2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180)
    * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function resampleAxis(coords) {
  const pts = [{ lon: coords[0][0], lat: coords[0][1], km: 0 }];
  let cumKm = 0;
  for (let i = 1; i < coords.length; i++) {
    const [lon1, lat1] = coords[i - 1];
    const [lon2, lat2] = coords[i];
    cumKm += haversineKm(lon1, lat1, lon2, lat2);
    pts.push({ lon: lon2, lat: lat2, km: cumKm });
  }
  return pts;
}

function isDark(km) {
  return D.tamne_zone.zone.some(z => km >= z.km_od && km <= z.km_do);
}

const SafetyCanvasLayer = L.Layer.extend({
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
  setPts(pts) {
    this._pts = pts;
    this.redraw();
  },
  redraw() {
    if (!this._map || !this._pts) return;
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

    const pts = this._pts;
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      // preskočimo ako je skok veći od ~100 m (diskontinuitet u koordinatama)
      if (b.km - a.km > 0.1) continue;
      const pa = m.latLngToContainerPoint([a.lat, a.lon]);
      const pb = m.latLngToContainerPoint([b.lat, b.lon]);
      ctx.strokeStyle = isDark(a.km) ? "#2c2c2c" : "#d8a93a";
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
  },
});

function buildMap() {
  const map = L.map("safety-map", { scrollWheelZoom: false });

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
    maxZoom: 19,
  }).addTo(map);

  const layer = new SafetyCanvasLayer();
  layer.addTo(map);

  // Učitaj osu i postavi canvas layer
  fetch(DATA + "staze_mreza.geojson")
    .then(r => r.json())
    .then(gj => {
      const axis = gj.features.find(f => f.properties.uloga === "osa");
      if (!axis) return;
      const pts = resampleAxis(axis.geometry.coordinates);
      layer.setPts(pts);
      const bounds = L.latLngBounds(pts.map(p => [p.lat, p.lon]));
      map.fitBounds(bounds, { padding: [18, 18] });
    });

  // Parking konflikti — narandžasto
  for (const p of D.konflikti.parking) {
    L.circleMarker([p.lat, p.lon], {
      radius: 8, color: "#b35000", fillColor: "#e76f1f", fillOpacity: 0.9, weight: 2,
    }).addTo(map)
      .bindPopup(`<strong>Parking konflikt</strong><br>${p.name}<br><em>${p.deonica || ""}</em>`);
  }

  // Prelazi — crveno
  for (const p of D.konflikti.prelazi) {
    L.circleMarker([p.lat, p.lon], {
      radius: 8, color: "#8b0000", fillColor: "#c0392b", fillOpacity: 0.9, weight: 2,
    }).addTo(map)
      .bindPopup(`<strong>Prelaz / ukrštanje</strong><br>${p.name}<br><em>${p.deonica || ""}</em>`);
  }
}

/* ── start ───────────────────────────────────────────────────── */

async function init() {
  try {
    const r = await fetch(DATA + "safety.json");
    D = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam safety.json:", e);
    return;
  }

  renderNalazi();
  renderStanjaTimeline();
  renderStanjaTable();
  drawStepHistogram();
  bindStepTooltip();
  renderStepTable();
  renderDarkStrip();
  renderDarkStats();
  renderKonfliktiStats();
  renderKonfliktiTable();
  buildMap();
}

init();
