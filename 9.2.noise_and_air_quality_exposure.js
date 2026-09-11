/* Analiza 9.2 — Buka i kvalitet vazduha.
 * Čita data/noise_air.json (noise_air.py): po tački svake od tri staze (10 m)
 * indeks izloženosti buci 0–100 na zajedničkoj km-osi, plus godišnji presek
 * kvaliteta vazduha za koridor. Renderuje profil duž trase (canvas), mapu
 * obojenu istom skalom, tabelu po deonicama i sezonski prikaz vazduha.
 */
"use strict";

const DATA = "data/";

/* Skala je namerno ista logika kao svuda na sajtu: zeleno = dobro.
 * Četiri pojasa umesto neprekidnog gradijenta — čitljivije je i poklapa se
 * sa rečima kojima se deonice opisuju u tekstu. */
const BANDS = [
  { max: 25,  color: "#2f6b46", label: "tiho" },
  { max: 50,  color: "#7fa05c", label: "umereno" },
  { max: 75,  color: "#e0a03a", label: "izloženo" },
  { max: 101, color: "#c0392b", label: "vrlo izloženo" },
];

const STAZA_SHORT = {
  bici: "Biciklistička",
  pesacki_gornji: "Pešačka — gornji bedem",
  pesacki_donji: "Pešačka — donji bedem",
};

const POLEN_LABEL = {
  birch_pollen: "Breza",
  grass_pollen: "Trave",
  ragweed_pollen: "Ambrozija",
};

let D = null;                     // ceo dataset
let S = null;                     // izabrana staza
let map = null;
let bukaLayer = null;
const state = { staza: "bici" };

function $(id) { return document.getElementById(id); }

function bandOf(v) { return BANDS.find(b => v < b.max) || BANDS[BANDS.length - 1]; }
function colorOf(v) { return bandOf(v).color; }

/* ---------- stat kartice ---------- */

function renderStats() {
  const t = S.totals;
  const tiles = [
    { v: t.avg, sub: "prosečan indeks", note: t.band, warn: t.avg >= 50 },
    { v: t.pct_tiho + " %", sub: "trase je tiho", note: "indeks ispod 25" },
    { v: t.pct_izlozeno + " %", sub: "trase je izloženo", note: "indeks 50 i više",
      warn: t.pct_izlozeno >= 40 },
    { v: t.pct_bez_glavnog + " %", sub: "bez glavnog puta u blizini",
      note: "ni jedan u 300 m" },
  ];
  $("buka-stats").innerHTML = tiles.map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.sub}</div>
      <div class="shade-stat-sub">${x.note}</div>
    </div>`).join("");
}

/* ---------- profil duž trase ---------- */

const PF = { padL: 44, padR: 12, padT: 10, padB: 26, h: 190 };

function profGeom() {
  const wrapW = $("profil-wrap").clientWidth;
  return { wrapW, plotW: wrapW - PF.padL - PF.padR, plotH: PF.h - PF.padT - PF.padB };
}

function drawProfil() {
  const cv = $("buka-profil");
  const g = profGeom();
  const dpr = window.devicePixelRatio || 1;
  cv.width = g.wrapW * dpr;
  cv.height = PF.h * dpr;
  cv.style.width = g.wrapW + "px";
  cv.style.height = PF.h + "px";
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, g.wrapW, PF.h);

  const totalKm = D.osa_km;
  const { km, idx, deonica } = S.points;
  const xOf = k => PF.padL + (k / totalKm) * g.plotW;
  const yOf = v => PF.padT + g.plotH * (1 - v / 100);
  const colW = Math.max(1, (D.step_m / 1000 / totalKm) * g.plotW + 0.5);

  // vodoravne linije po pojasevima — daju oku sidro za "koliko je ovo"
  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  [0, 25, 50, 75, 100].forEach(v => {
    ctx.strokeStyle = v === 0 ? "#d8ddd6" : "rgba(168,177,171,.45)";
    ctx.beginPath();
    ctx.moveTo(PF.padL, yOf(v));
    ctx.lineTo(PF.padL + g.plotW, yOf(v));
    ctx.stroke();
    ctx.fillStyle = "#6b776f";
    ctx.fillText(String(v), PF.padL - 6, yOf(v));
  });

  // stubići, obojeni po pojasu
  for (let i = 0; i < km.length; i++) {
    ctx.fillStyle = colorOf(idx[i]);
    const y = yOf(idx[i]);
    ctx.fillRect(xOf(km[i]), y, colW, yOf(0) - y);
  }

  // granice deonica + imena
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  let prev = null;
  for (let i = 0; i < km.length; i++) {
    if (deonica[i] === prev) continue;
    if (prev !== null) {
      ctx.strokeStyle = "rgba(26,31,27,.35)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(xOf(km[i]), PF.padT);
      ctx.lineTo(xOf(km[i]), yOf(0));
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.fillStyle = "#3b4a40";
    ctx.fillText(D.deonice[deonica[i]], xOf(km[i]) + 4, PF.padT + 2);
    prev = deonica[i];
  }

  // km osa
  ctx.textAlign = "center";
  ctx.fillStyle = "#6b776f";
  for (let k = 0; k <= Math.floor(totalKm); k += 2) {
    ctx.fillText(k + " km", xOf(k), yOf(0) + 7);
  }
}

function bindProfilTooltip() {
  const wrap = $("profil-wrap");
  const tip = $("profil-tooltip");
  const hide = () => { tip.hidden = true; };

  wrap.addEventListener("mousemove", ev => {
    const g = profGeom();
    const r = wrap.getBoundingClientRect();
    const mx = ev.clientX - r.left;
    if (mx < PF.padL || mx > PF.padL + g.plotW) return hide();
    const k = ((mx - PF.padL) / g.plotW) * D.osa_km;
    const i = nearestIndex(S.points.km, k);
    if (i < 0) return hide();
    const v = S.points.idx[i];
    const b = bandOf(v);
    const near = S.points.near_m[i];
    tip.querySelector(".tt-state").innerHTML =
      `<span style="color:${b.color}">●</span> ${b.label} — indeks ${v}`;
    tip.querySelector(".tt-meta").textContent =
      `km ${S.points.km[i].toFixed(2)} · ${D.deonice[S.points.deonica[i]]} · `
      + (near === null ? "nema glavnog puta u 300 m" : `glavni put na ${near} m`);
    tip.hidden = false;
    const tw = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(mx - tw / 2, g.wrapW - tw - 4)) + "px";
    tip.style.top = "4px";
  });
  wrap.addEventListener("mouseleave", hide);
}

// km niz je sortiran ali nije ekvidistantan (staze imaju prekide)
function nearestIndex(arr, k) {
  let lo = 0, hi = arr.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < k) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(arr[lo - 1] - k) < Math.abs(arr[lo] - k)) lo--;
  return Math.abs(arr[lo] - k) > 0.15 ? -1 : lo;
}

function renderBandLegend() {
  $("band-legend").innerHTML = BANDS.map((b, i) => {
    const lo = i === 0 ? 0 : BANDS[i - 1].max;
    const hi = b.max > 100 ? 100 : b.max - 1;
    return `<span class="hl-item"><span class="hl-swatch" style="background:${b.color}"></span> ${b.label} <span class="muted">(${lo}–${hi})</span></span>`;
  }).join("");
}

/* ---------- mapa ---------- */

const BukaCanvasLayer = L.Layer.extend({
  onAdd(m) {
    this._canvas = L.DomUtil.create("canvas", "leaflet-zoom-hide");
    m.getPanes().overlayPane.appendChild(this._canvas);
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

    const { lat, lon, km, chain, idx } = S.points;
    const stepKm = D.step_m / 1000;
    const pts = km.map((_, i) => m.latLngToContainerPoint([lat[i], lon[i]]));
    // tačke su sortirane po zajedničkoj km-osi, pa susedi u nizu mogu biti
    // sa različitih lanaca — crtaj lanac po lanac
    const byChain = new Map();
    for (let i = 0; i < km.length; i++) {
      if (!byChain.has(chain[i])) byChain.set(chain[i], []);
      byChain.get(chain[i]).push(i);
    }
    for (const ids of byChain.values()) {
      for (let j = 0; j < ids.length - 1; j++) {
        const a = ids[j], b = ids[j + 1];
        if (km[b] - km[a] > stepKm * 1.5) continue;
        ctx.strokeStyle = colorOf(idx[a]);
        ctx.beginPath();
        ctx.moveTo(pts[a].x, pts[a].y);
        ctx.lineTo(pts[b].x, pts[b].y);
        ctx.stroke();
      }
    }
  },
});

function buildMap() {
  const bounds = L.latLngBounds([]);
  D.staze.forEach(s => s.points.lat.forEach(
    (la, i) => bounds.extend([la, s.points.lon[i]])));
  map = L.map("buka-map", { scrollWheelZoom: false });
  map.fitBounds(bounds, { padding: [18, 18] });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
    maxZoom: 19,
  }).addTo(map);
  bukaLayer = new BukaCanvasLayer();
  bukaLayer.addTo(map);
}

/* ---------- tabela ---------- */

function renderTable() {
  const head = `
    <thead><tr>
      <th>Deonica</th><th>km</th><th>Prosek</th><th class="tl">Ocena</th>
      <th>Tiho</th><th>Izloženo</th><th>Van domašaja saobraćaja</th>
    </tr></thead>`;
  const row = (name, s) => `
    <tr>
      <td>${name}</td>
      <td class="num">${s.km_start !== undefined ? `${s.km_start.toFixed(1)}–${s.km_end.toFixed(1)}` : "0–" + D.osa_km.toFixed(1)}</td>
      <td class="num"><span class="idx-pill" style="background:${colorOf(s.avg)}">${s.avg}</span></td>
      <td>${s.band}</td>
      <td class="num">${s.pct_tiho}%</td>
      <td class="num">${s.pct_izlozeno}%</td>
      <td class="num">${s.pct_bez_glavnog}%</td>
    </tr>`;
  const body = D.deonice.filter(dn => S.by_deonica[dn])
    .map(dn => row(dn, S.by_deonica[dn])).join("")
    + row("<strong>Cela staza</strong>", S.totals);
  $("buka-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

/* ---------- vazduh ---------- */

const ZAG_LABEL = {
  pm2_5: "PM2.5 — sitne čestice",
  pm10: "PM10 — krupnije čestice",
  nitrogen_dioxide: "NO₂ — azot-dioksid",
};

function renderVazduh() {
  const a = D.vazduh;
  if (!a) { $("vazduh").hidden = true; return; }

  $("vazduh-kartice").innerHTML = Object.entries(a.zagadjivaci).map(([k, v]) => {
    const puta = (v.prosek / v.szo_godisnji).toFixed(1);
    const lose = v.pct_dana_preko >= 20;
    return `
      <div class="vazduh-kartica">
        <h4>${ZAG_LABEL[k] || k}</h4>
        <p class="vk-broj${lose ? " warn" : ""}">${v.prosek}<span class="vk-jed"> µg/m³</span></p>
        <p class="vk-sub">godišnji prosek — <strong>${puta}×</strong> smernica SZO (${v.szo_godisnji})</p>
        <div class="vk-bar"><span style="width:${Math.min(100, v.pct_dana_preko)}%"></span></div>
        <p class="vk-note">${v.pct_dana_preko} % dana preko dnevne smernice (${v.szo_dnevni} µg/m³)</p>
      </div>`;
  }).join("");

  // mesečni PM2.5 — CSS stupci, čitljiviji i pristupačniji od canvasa
  const pm = a.zagadjivaci.pm2_5;
  if (pm) {
    const max = Math.max(...pm.po_mesecu.filter(x => x !== null), pm.szo_dnevni);
    const linija = 100 * (pm.szo_dnevni / max);
    $("pm-mesecno").innerHTML = `
      <div class="mg-plot" style="--szo:${linija}%">
        ${pm.po_mesecu.map((v, i) => {
          if (v === null) return `<div class="mg-col"><span class="mg-ime">${a.meseci[i]}</span></div>`;
          const preko = v > pm.szo_dnevni;
          return `<div class="mg-col" title="${a.meseci[i]}: ${v} µg/m³">
              <span class="mg-val">${v}</span>
              <span class="mg-bar${preko ? " over" : ""}" style="height:${100 * v / max}%"></span>
              <span class="mg-ime">${a.meseci[i]}</span>
            </div>`;
        }).join("")}
      </div>
      <p class="mg-legend"><span class="mg-key over"></span> preko dnevne smernice SZO (${pm.szo_dnevni} µg/m³)
        <span class="mg-key ok"></span> ispod smernice</p>`;
  }

  const pol = Object.entries(a.polen);
  if (pol.length) {
    $("polen-kalendar").innerHTML = pol.map(([k, v]) => {
      const max = Math.max(...v.po_mesecu.filter(x => x !== null), 1);
      return `
        <div class="pk-red">
          <div class="pk-ime">${POLEN_LABEL[k] || k}</div>
          <div class="pk-traka">
            ${v.po_mesecu.map((x, i) => {
              const t = x === null ? 0 : x / max;
              return `<span class="pk-cel" style="--t:${t.toFixed(3)}"
                        title="${a.meseci[i]}: ${x === null ? "nema podataka" : x + " zrna/m³"}"></span>`;
            }).join("")}
          </div>
          <div class="pk-vrh">vrhunac ${v.vrhunac_mesec}</div>
        </div>`;
    }).join("")
      + `<div class="pk-osa">${a.meseci.map(m => `<span>${m}</span>`).join("")}</div>`;
  }
}

/* ---------- prekidač staza ---------- */

function selectStaza(tip) {
  state.staza = tip;
  S = D.staze.find(s => s.tip === tip);
  document.querySelectorAll("#staza-pills .chip").forEach(c =>
    c.classList.toggle("active", c.dataset.staza === tip));
  renderStats();
  drawProfil();
  renderTable();
  if (bukaLayer) bukaLayer.redraw();
}

function buildStazaPills() {
  const el = $("staza-pills");
  el.innerHTML = D.staze.map(s =>
    `<button type="button" class="chip${s.tip === state.staza ? " active" : ""}" data-staza="${s.tip}">${STAZA_SHORT[s.tip] || s.label}</button>`
  ).join("");
  el.addEventListener("click", ev => {
    const btn = ev.target.closest("button[data-staza]");
    if (btn) selectStaza(btn.dataset.staza);
  });
}

/* ---------- start ---------- */

async function init() {
  try {
    const r = await fetch(DATA + "noise_air.json");
    D = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam noise_air.json:", e);
    return;
  }
  S = D.staze.find(s => s.tip === state.staza) || D.staze[0];
  state.staza = S.tip;

  buildStazaPills();
  renderBandLegend();
  renderStats();
  drawProfil();
  bindProfilTooltip();
  renderTable();
  buildMap();
  renderVazduh();

  let t = null;
  window.addEventListener("resize", () => {
    clearTimeout(t);
    t = setTimeout(drawProfil, 150);
  });
}

init();
