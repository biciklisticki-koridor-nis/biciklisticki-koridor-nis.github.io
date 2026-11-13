/* Analiza 2 — Nivo saobraćajnog stresa (LTS).
 * Čita data/lts.json i data/lts_mreza.json (lts.py), staze_mreza.geojson za
 * osu na mapi i anketa.json za podatak o pešacima na keju.
 *
 * Nijedan broj nije upisan u tekst stranice: sve dolazi iz JSON-a, da novi
 * `make lts` ažurira stranicu bez ručnog prepravljanja.
 */
"use strict";

const DATA = "data/";

/* Iste boje kao kategorije stresa u 9.3 — zelena je mirno, crvena je stres. */
const LTS_COLOR = { 1: "#2f6b46", 2: "#7fa05c", 3: "#e0a03a", 4: "#c0392b" };
const CELL_COLOR = { 2: "#4a9367", 1: "#e0a03a", 0: "#c0392b" };
const CELL_LABEL = {
  2: "stiže uz LTS ≤ 2",
  1: "stiže tek uz veći obilazak",
  0: "ne stiže bez stresa",
};

let D = null;
let NET = null;
let ANKETA = null;

function $(id) { return document.getElementById(id); }
function br(x, d = 1) { return x.toFixed(d).replace(".", ","); }
function ceo(x) { return Math.round(x).toLocaleString("sr-Latn").replace(/,/g, "."); }
function badge(l) { return `<span class="lts-badge" data-lts="${l}">${l}</span>`; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function ulica(x) { return x ? esc(x) : '<span class="muted">bez imena</span>'; }
/* 1 traka, 2–4 trake, 5+ traka (21 traka, 22 trake…) */
function trake(n) {
  const d = n % 10, s = n % 100;
  return `${n} ${d >= 2 && d <= 4 && !(s >= 12 && s <= 14) ? "trake" : "traka"}`;
}

function r2() { return D.povezanost.radijusi.find(r => r.r_m === D.povezanost.zahvat_m); }

/* ── ključni nalazi ──────────────────────────────────────────── */

function renderNalazi() {
  const r = r2();
  const ul = D.pristupi;
  const n34 = ul.filter(p => p.lts > 2).length;
  const km = D.osa.km_po_lts;
  const iznad2 = Object.entries(km).filter(([k]) => +k > 2).reduce((a, [, v]) => a + v, 0);
  const tiles = [
    { v: br(r.lts2_pct) + " %", warn: true,
      tekst: `stanovnika do ${D.povezanost.zahvat_m / 1000} km stiže do keja i nazad bez ulice iznad <strong>LTS 2</strong>, od ${ceo(r.stanovnika)} koliko ih tu živi.` },
    { v: br(r.lts1_pct) + " %", warn: true,
      tekst: "može da stigne <strong>dete samo</strong> (LTS 1). Mreža za decu su gotovo samo parkovske i pešačke staze." },
    { v: `${n34} od ${ul.length}`, warn: n34 > 0,
      tekst: "mapiranih ulaza izlazi na ulicu ocene <strong>3 ili 4</strong>, kojom se do keja mora doći." },
    { v: br(km["1"] || 0) + " km", warn: false,
      tekst: iznad2 > 0
        ? `ose je LTS 1. Iznad LTS 2 je ${br(iznad2)} km.`
        : "ose je LTS 1, a nijedan metar nije iznad LTS 2. Problem je put do keja, ne sam kej." },
  ];
  $("nalazi").innerHTML = tiles.map(x => `
    <div class="nalaz${x.warn ? " nalaz-warn" : ""}">
      <p class="nalaz-broj">${x.v}</p>
      <p class="nalaz-tekst">${x.tekst}</p>
    </div>`).join("");
}

/* ── 2.1 okvir ───────────────────────────────────────────────── */

function bandLabels(limits) {
  const out = [];
  let lo = 0;
  for (const b of limits) {
    out.push(b >= 999 ? `${lo}+ km/h` : (lo === 0 ? `do ${b} km/h` : `${lo}–${b} km/h`));
    lo = b + 1;
  }
  return out;
}

function renderTabele() {
  const k = D.kriterijumi;
  const head = `<thead><tr><th class="tl">Brzina</th><th>do 3 trake</th><th>4–5 traka</th><th>6+ traka</th></tr></thead>`;

  const t4labels = bandLabels(k.T4.map(r => r.do_kmh));
  $("t4").innerHTML = head + "<tbody>" + k.T4.map((r, i) => `
    <tr><td class="tl">${t4labels[i]}</td>${r.vrednosti.map(v =>
      `<td>${Array.isArray(v) ? badge(v[0]) + " / " + badge(v[1]) : badge(v)}</td>`).join("")}</tr>`).join("") + "</tbody>";

  const t6labels = bandLabels(k.T6_pojasevi_kmh);
  $("t6").innerHTML = head + "<tbody>" + k.T6a.map((row, i) => `
    <tr><td class="tl">${t6labels[i]}</td>${row.map((v, j) =>
      `<td>${badge(v)} / ${badge(k.T6b[i][j])}</td>`).join("")}</tr>`).join("") + "</tbody>";
  $("t4").querySelector("tbody").classList.add("lts-noshade");
  $("t6").querySelector("tbody").classList.add("lts-noshade");

  const u = D.osa.udaljenost_od_ulice_pct;
  $("zamka").innerHTML = `Po tabeli 1, staza odvojena od saobraćaja je LTS 1. <strong>${br(u.preko_50 || 0)} %</strong> biciklističke ose je dalje od 50 m od bilo koje ulice, a samo ${br(u.do_10 || 0)} % bliže od 10 m, pa bi ceo kej dobio istu ocenu. Stres je na ulazu: u ulicama kojima se do keja stiže i na prelazima preko njih.`;

  const p = D.podaci;
  const tiles = [
    { v: br(p.brzina_sa_znaka_pct) + " %", label: "ulica sa upisanom brzinom",
      sub: "ostale: 50 km/h, zakonsko u naselju", warn: p.brzina_sa_znaka_pct < 50 },
    { v: br(p.trake_tag_pct) + " %", label: "ulica sa upisanim brojem traka",
      sub: "ostale: 2, ili 1 za jednosmernu", warn: p.trake_tag_pct < 50 },
    { v: ceo(p.semafora), label: "semafora u zahvatu", sub: "prelaz u krugu od 25 m je LTS 1" },
    { v: ceo(p.obelezenih_traka), label: "obeleženih biciklističkih traka",
      sub: "u OSM-u — tabele 2 i 3 ne učestvuju" },
  ];
  $("podaci-stats").innerHTML = tiles.map(statTile).join("");
}

function statTile(x) {
  return `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.label}</div>
      <div class="shade-stat-sub">${x.sub}</div>
    </div>`;
}

/* ── 2.2 osa ─────────────────────────────────────────────────── */

function renderOsa() {
  const o = D.osa;
  const km = o.km_po_lts;
  const maxPrelaz = o.prelazi.reduce((a, p) => Math.max(a, p.lts), 0);
  $("osa-stats").innerHTML = [
    { v: br(km["1"] || 0) + " km", label: "LTS 1", sub: "staza odvojena od saobraćaja" },
    { v: br(km["2"] || 0) + " km", label: "LTS 2", sub: "osa ide mirnom ulicom" },
    { v: o.prelazi.length, label: "prelaza u nivou",
      sub: o.prelazi.length ? `najgori je LTS ${maxPrelaz}` : "nema ih", warn: maxPrelaz > 2 },
    { v: o.van_nivoa.length, label: "ukrštanja van nivoa", sub: "most iznad staze — bez konflikta" },
  ].map(statTile).join("");

  $("lts-legenda-osa").innerHTML = [1, 2, 3, 4].map(l =>
    `<span class="hl-item"><span class="hl-swatch" style="background:${LTS_COLOR[l]}"></span> LTS ${l}</span>`).join("");

  // trake po kilometru: spajaju se uzastopni uzorci iste ocene
  const total = o.duzina_km;
  const runs = [];
  for (const [k, l] of o.uzorci) {
    const last = runs[runs.length - 1];
    if (last && last.lts === l) last.do = k;
    else runs.push({ od: k, do: k, lts: l });
  }
  runs.forEach((r, i) => { r.do = i + 1 < runs.length ? runs[i + 1].od : total; });
  $("osa-strip").innerHTML = runs.map(r => {
    const w = ((r.do - r.od) / total * 100).toFixed(3);
    return `<span class="strip-seg" style="width:${w}%;background:${LTS_COLOR[r.lts]}" title="LTS ${r.lts}: km ${br(r.od, 2)}–${br(r.do, 2)}"></span>`;
  }).join("");

  const marks = o.prelazi.map(p => ({ ...p, klasa: "nivo",
    t: `Prelaz u nivou, km ${br(p.km, 2)}: ${p.ulica || "ulica bez imena"} — LTS ${p.lts}` }))
    .concat(o.van_nivoa.map(p => ({ ...p, klasa: "van",
      t: `${p.tip === "tunel" ? "Tunel" : "Most"} iznad staze, km ${br(p.km, 2)}${p.ulica ? ": " + p.ulica : ""}` })));
  $("osa-marks").innerHTML = marks.map(m =>
    `<span class="lts-tri lts-tri-${m.klasa}" style="left:${(m.km / total * 100).toFixed(2)}%" title="${esc(m.t)}"></span>`).join("");

  const ticks = [];
  for (let k = 0; k <= Math.floor(total); k += 2) {
    ticks.push(`<span style="left:${(k / total * 100).toFixed(2)}%">${k}</span>`);
  }
  $("osa-axis").innerHTML = ticks.join("");

  $("potezi-table").innerHTML = `
    <thead><tr><th class="tl">Km</th><th class="tl">Ulica</th><th>Dužina</th><th>LTS</th></tr></thead>
    <tbody class="lts-noshade">${o.ulicni_potezi.map(p => `
      <tr><td class="tl">${br(p.km_od, 2)}–${br(p.km_do, 2)}<br><span class="muted">${esc(p.deonica)}</span></td>
          <td class="tl">${ulica(p.ulica)}<br><span class="muted">${esc(p.pravilo)}</span></td>
          <td class="num">${ceo(p.duzina_m)} m</td><td>${badge(p.lts)}</td></tr>`).join("")}
    </tbody>`;

  $("prelazi-table").innerHTML = `
    <thead><tr><th class="tl">Km</th><th class="tl">Ulica</th><th>Prelaz</th><th>LTS</th></tr></thead>
    <tbody class="lts-noshade">${o.prelazi.map(p => `
      <tr><td class="tl">${br(p.km, 2)}<br><span class="muted">${esc(p.deonica)}</span></td>
          <td class="tl">${ulica(p.ulica)}<br><span class="muted">${trake(p.trake)}${p.trake_izvor === "pretpostavka" ? " (pretp.)" : ""}, ${p.kmh} km/h${p.kmh_izvor === "pretpostavka" ? " (pretp.)" : ""}</span></td>
          <td class="tl">${p.semafor ? "semafor" : (p.ostrvo ? "ostrvo, bez semafora" : "bez semafora i ostrva")}</td>
          <td>${badge(p.lts)}</td></tr>`).join("")}
    </tbody>`;
}

/* ── 2.2 ulazi ───────────────────────────────────────────────── */

function renderUlazi() {
  const ul = D.pristupi;
  const n = ul.length;
  $("ulazi-bars").innerHTML = [1, 2, 3, 4].map(l => {
    const c = ul.filter(p => p.lts === l).length;
    const pct = n ? c / n * 100 : 0;
    return `
      <div class="bar-row">
        <div class="label">LTS ${l}</div>
        <div class="track" style="background:#f0ede8">
          <div class="fill" style="width:${pct.toFixed(1)}%;background:${LTS_COLOR[l]};border-radius:999px"></div>
        </div>
        <div class="value">${c} od ${n}</div>
      </div>`;
  }).join("");

  $("ulazi-table").innerHTML = `
    <thead><tr><th class="tl">Km</th><th class="tl">Izlazi na</th><th class="tl">Na samom ulazu</th><th>LTS</th></tr></thead>
    <tbody class="lts-noshade">${ul.map(p => {
      const nap = [];
      if (p.stepenice) nap.push("stepenice");
      if (p.prekid) nap.push("prekid u kretanju");
      const opis = p.hw
        ? `${ulica(p.ulica)}<br><span class="muted">${trake(p.trake)}, ${p.kmh} km/h${p.kmh_izvor === "pretpostavka" ? " (pretp.)" : ""}</span>`
        : '<span class="muted">staza, bez ulice na 25 m</span>';
      return `
      <tr><td class="tl">${p.km !== null ? br(p.km, 2) : "—"}<br><span class="muted">${esc(p.deonica)}</span></td>
          <td class="tl">${opis}</td>
          <td class="tl">${nap.length ? nap.join(", ") : '<span class="muted">—</span>'}</td>
          <td>${badge(p.lts)}</td></tr>`;
    }).join("")}
    </tbody>`;
}

/* ── 2.2 povezanost ──────────────────────────────────────────── */

function renderPovezanost() {
  const r = r2();
  $("povezanost-lead").innerHTML = `Od ${ceo(r.stanovnika)} stanovnika do ${D.povezanost.zahvat_m / 1000} km od keja (mereno mrežom ulica i staza) <strong>${br(r.lts2_pct)} %</strong> može do keja i nazad putem ocene najviše LTS 2, uz obilazak do 25 %. Za decu (LTS 1) to je ${br(r.lts1_pct)} %, za sigurne bicikliste (LTS 3) ${br(r.lts3_pct)} %.`;

  const pctCell = (v, best) => `<td class="num${best ? " pk-best" : ""}">${br(v)} %</td>`;
  const deo = D.povezanost.po_deonici;
  const best2 = Math.max(...deo.map(x => x.lts2_pct));
  $("deonice-table").innerHTML = `
    <thead><tr><th class="tl">Deonica</th><th>Stanovnika</th><th>LTS 1</th><th>LTS 2</th><th>LTS 3</th></tr></thead>
    <tbody>${deo.map(x => `
      <tr><td class="tl">${esc(x.deonica)}</td><td class="num">${ceo(x.stanovnika)}</td>
          ${pctCell(x.lts1_pct)}${pctCell(x.lts2_pct, x.lts2_pct === best2)}${pctCell(x.lts3_pct)}</tr>`).join("")}
      <tr><td class="tl"><strong>Ukupno</strong></td><td class="num">${ceo(r.stanovnika)}</td>
          ${pctCell(r.lts1_pct)}${pctCell(r.lts2_pct)}${pctCell(r.lts3_pct)}</tr>
    </tbody>`;

  $("radijusi-table").innerHTML = `
    <thead><tr><th class="tl">Do keja</th><th>Stanovnika</th><th>LTS 1</th><th>LTS 2</th><th>LTS 3</th></tr></thead>
    <tbody class="lts-noshade">${D.povezanost.radijusi.map(x => `
      <tr><td class="tl">do ${x.r_m / 1000} km</td><td class="num">${ceo(x.stanovnika)}</td>
          ${pctCell(x.lts1_pct)}${pctCell(x.lts2_pct)}${pctCell(x.lts3_pct)}</tr>`).join("")}
    </tbody>`;

  // zašto ostali ne stižu — delovi celine zahvata
  const nd = D.nedostizno;
  const tot = r.stanovnika;
  const obilazak = tot - r.lts2 - nd.stanovnika;
  const delovi = [
    { label: "stiže uz LTS ≤ 2", v: r.lts2, col: CELL_COLOR[2] },
    { label: "stiže tek uz obilazak veći od 25 %", v: obilazak, col: CELL_COLOR[1] },
    { label: "mirnim ulicama stiže samo kontra smeru, ili uz obilazak veći od 2,3 puta", v: nd.van_dometa, col: "#c46b2c" },
    { label: "ostrva — mirne ulice odsečene od keja", v: nd.u_ostrvima, col: CELL_COLOR[0] },
    { label: "nema mirne ulice u blizini", v: nd.bez_ulice_niskog_stresa, col: "#7b241c" },
  ];
  $("nedostizno-bars").innerHTML = delovi.map(x => `
    <div class="bar-row">
      <div class="label">${x.label}</div>
      <div class="track" style="background:#f0ede8">
        <div class="fill" style="width:${(x.v / tot * 100).toFixed(1)}%;background:${x.col};border-radius:999px"></div>
      </div>
      <div class="value">${br(x.v / tot * 100)} %</div>
    </div>`).join("");

  const s = D.povezanost.osetljivost;
  const o = D.ostrva[0];
  const nepov = delovi.slice(1);
  const najveci = nepov.reduce((a, x) => (x.v > a.v ? x : a));
  const share = x => br(x.v / (tot - r.lts2) * 100, 0);
  let uvod;
  if (najveci === delovi[1]) {
    uvod = `<strong>Najveći deo nepovezanih ima miran put do keja, ali predug.</strong> ${share(najveci)} % njih ima put niskog stresa koji je više od 25 % duži od najkraćeg. Fale prečice preko bulevara.`;
  } else if (najveci === delovi[2]) {
    uvod = `<strong>Najveći deo nepovezanih je zaključan smerom.</strong> ${share(najveci)} % njih ima mirnu ulicu do keja, ali ona vodi samo u jednom smeru ili je obilazak ogroman.`;
  } else {
    uvod = `<strong>Najveći deo nepovezanih živi na ostrvima</strong> — mirnim ulicama koje su od keja odsečene.`;
  }
  $("nedostizno-callout").querySelector("p").innerHTML = uvod
    + ` Kad bi se jednosmerne ulice zanemarile, povezanost bi bila ${br(s.jednosmerne_ignorisane)} % umesto ${br(r.lts2_pct)} %.`
    + (o ? ` Pravih ostrva ima malo; najveće je oko ulice ${esc(o.ulice[0] || "bez imena")}, sa ${ceo(o.stanovnika)} stanovnika.` : "");
}

/* ── mapa ────────────────────────────────────────────────────── */

function decodeLines() {
  return NET.linije.map(([lts, cls, d]) => {
    const pts = [];
    let x = 0, y = 0;
    for (let i = 0; i < d.length; i += 2) {
      x += d[i];
      y += d[i + 1];
      pts.push([y / 1e5, x / 1e5]);
    }
    return { lts, cls, pts };
  });
}

function renderMap(axisGeo) {
  const map = L.map("lts-map", { scrollWheelZoom: false, preferCanvas: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · WorldPop',
    opacity: 0.55,
  }).addTo(map);
  const renderer = L.canvas({ padding: 0.3 });

  const lines = decodeLines();
  const streetsLts = L.layerGroup(lines.map(l => L.polyline(l.pts, {
    renderer, color: LTS_COLOR[l.lts], weight: l.lts >= 3 ? 2.6 : 1.6, opacity: 0.9, interactive: false,
  })));
  const streetsGrey = L.layerGroup(lines.map(l => L.polyline(l.pts, {
    renderer, color: l.lts >= 3 ? "#8a8f8b" : "#b9bfba", weight: l.lts >= 3 ? 1.6 : 0.8, opacity: 0.8, interactive: false,
  })));

  const [lon0, lat0, step] = NET.celije_origin;
  const h = step / 2;
  const cells = L.layerGroup(NET.celije.map(([c, r, p, k]) => {
    const lon = lon0 + c * step, lat = lat0 + r * step;
    return L.rectangle([[lat - h, lon - h], [lat + h, lon + h]], {
      renderer, stroke: false, fillColor: CELL_COLOR[k],
      fillOpacity: Math.min(0.75, 0.25 + p / 400), interactive: true,
    }).bindTooltip(`${ceo(p)} stanovnika · ${CELL_LABEL[k]}`, { sticky: true });
  }));

  const axis = L.geoJSON(axisGeo, {
    style: { color: "#1f3b2d", weight: 5, opacity: 0.95 },
    interactive: false,
  });

  const ulazi = L.layerGroup(D.pristupi.map(p => L.circleMarker([p.lat, p.lon], {
    radius: 6, color: "#fff", weight: 2, fillColor: LTS_COLOR[p.lts], fillOpacity: 1,
  }).bindTooltip(`Ulaz, km ${p.km !== null ? br(p.km, 2) : "—"}: ${p.ulica || (p.hw ? "ulica bez imena" : "staza")} — LTS ${p.lts}`)));

  const barijere = L.layerGroup(D.barijere.map((b, i) => L.marker([b.lat, b.lon], {
    icon: L.divIcon({ className: "lts-num", html: `<span>${i + 1}</span>`, iconSize: [24, 24] }),
  }).bindTooltip(`${i + 1}. ${b.tip === "prelaz" ? "Prelaz preko" : "Potez"} ${b.ulica || "ulice bez imena"} — priključuje ${ceo(b.prikljucuje)}`)));

  const modes = {
    stanovnici: [streetsGrey, cells, axis, barijere],
    ulice: [streetsLts, axis, ulazi, barijere],
  };
  const legends = {
    stanovnici: [2, 1, 0].map(k =>
      `<span class="hl-item"><span class="hl-swatch" style="background:${CELL_COLOR[k]}"></span> ${CELL_LABEL[k]}</span>`).join("")
      + '<span class="hl-item"><span class="hl-swatch" style="background:#1f3b2d"></span> osa koridora</span>',
    ulice: [1, 2, 3, 4].map(l =>
      `<span class="hl-item"><span class="hl-swatch" style="background:${LTS_COLOR[l]}"></span> LTS ${l}</span>`).join("")
      + '<span class="hl-item"><span class="hl-swatch" style="background:#1f3b2d"></span> osa koridora</span>'
      + '<span class="hl-item"><span class="hl-swatch" style="background:#7fa05c;border-radius:50%"></span> ulaz (boja = ulica na koju izlazi)</span>',
  };
  let cur = null;
  function setMode(m) {
    if (cur) modes[cur].forEach(l => map.removeLayer(l));
    modes[m].forEach(l => l.addTo(map));
    $("map-legenda").innerHTML = legends[m];
    document.querySelectorAll("#map-mode .chip").forEach(c =>
      c.classList.toggle("active", c.dataset.mode === m));
    cur = m;
  }
  document.querySelectorAll("#map-mode .chip").forEach(c =>
    c.addEventListener("click", () => setMode(c.dataset.mode)));
  setMode("stanovnici");
  map.fitBounds(axis.getBounds(), { padding: [30, 30] });
}

/* ── 2.3 ciljevi ─────────────────────────────────────────────── */

function renderCiljevi() {
  const c = D.ciljevi;
  const o = D.osa;
  const km = o.km_po_lts;
  const r = r2();
  const n = D.pristupi.length;
  const maxPrelaz = o.prelazi.reduce((a, p) => Math.max(a, p.lts), 0);
  const ok = '<span class="lts-ok">ispunjeno</span>';
  const ne = '<span class="lts-ne">nije ispunjeno</span>';
  const rows = [
    { el: "Osa koridora", cilj: "LTS ≤ 2; za decu LTS 1",
      danas: `${br(km["1"] || 0)} km LTS 1, ${br(km["2"] || 0)} km LTS 2 (ulicom)`,
      st: c.osa_km_iznad_2 === 0
        ? `${ok} za odrasle; za decu fali ${br(km["2"] || 0)} km`
        : ne },
    { el: "Prelazi u nivou", cilj: "LTS ≤ 2",
      danas: `${o.prelazi.length} prelaza, najgori LTS ${maxPrelaz}`,
      st: c.prelazi_iznad_2 === 0 ? ok : ne },
    { el: "Ulazi", cilj: "ulica na izlazu LTS ≤ 2, bez stepenica",
      danas: `${c.pristupi_iznad_2} od ${n} izlazi na LTS 3–4; ${c.pristupi_stepenice} ima stepenice`,
      st: c.pristupi_iznad_2 === 0 && c.pristupi_stepenice === 0 ? ok : ne },
    { el: "Povezanost, odrasli", cilj: "rast od polazne vrednosti",
      danas: `${br(c.povezano_lts2_pct)} % stanovnika do ${D.povezanost.zahvat_m / 1000} km; ${br(c.povezano_lts2_posle_top)} % posle deset mera niže`,
      st: '<span class="muted">polazna vrednost</span>' },
    { el: "Povezanost, deca", cilj: "rast od polazne vrednosti",
      danas: `${br(c.povezano_lts1_pct)} % stanovnika do ${D.povezanost.zahvat_m / 1000} km`,
      st: '<span class="muted">polazna vrednost</span>' },
  ];
  $("ciljevi-table").innerHTML = `
    <thead><tr><th class="tl">Element</th><th class="tl">Cilj</th><th class="tl">Danas</th><th class="tl">Stanje</th></tr></thead>
    <tbody class="lts-noshade">${rows.map(x => `
      <tr><td class="tl"><strong>${x.el}</strong></td><td class="tl">${x.cilj}</td><td class="tl">${x.danas}</td><td class="tl">${x.st}</td></tr>`).join("")}
    </tbody>`;

  // prioriteti
  let cum = r.lts2;
  $("barijere-table").innerHTML = `
    <thead><tr><th>#</th><th class="tl">Mera</th><th class="tl">Danas</th><th>Priključuje</th><th>Povezano</th></tr></thead>
    <tbody class="lts-noshade">${D.barijere.map((b, i) => {
      cum += b.prikljucuje;
      // bulevar sa dva kolovoza već ima ostrvo i tako je ocenjen (tabela 6b)
      const mera = b.tip === "prelaz"
        ? (b.bulevar
          ? `Semafor na prelazu preko ulice ${ulica(b.ulica)} <span class="muted">(ostrvo već postoji)</span>`
          : `Semafor ili ostrvo na prelazu preko ulice ${ulica(b.ulica)}`)
        : `Smiriti ili odvojiti ${ceo(b.duzina_m)} m ulice ${ulica(b.ulica)}`;
      const danas = `LTS ${b.lts} · ${trake(b.trake)}${b.trake_izvor === "pretpostavka" ? " (pretp.)" : ""}, ${b.kmh} km/h${b.kmh_izvor === "pretpostavka" ? " (pretp.)" : ""}${b.bulevar ? ", bulevar" : ""}`;
      return `
      <tr><td class="num">${i + 1}</td>
          <td class="tl">${mera}<br><span class="muted">${esc(b.deonica)}</span></td>
          <td class="tl">${danas}</td>
          <td class="num">+${ceo(b.prikljucuje)}</td>
          <td class="num">${br(cum / r.stanovnika * 100)} %</td></tr>`;
    }).join("")}
    </tbody>`;

  const top = c.top_prikljucuje;
  $("barijere-callout").querySelector("p").innerHTML =
    `<strong>Deset mera zajedno priključuje ${ceo(top)} stanovnika</strong>: povezanost raste sa ${br(c.povezano_lts2_pct)} na ${br(c.povezano_lts2_posle_top)} %. To je malo, jer je nepovezana cela mreža jednosmernih i višetračnih ulica, a ne nekoliko uskih grla. Nijedna tačka nije obiđena na terenu, a većina zavisi od broja traka upisanog u OSM na kratkom potezu.`;

  // pešaci na keju — iz ankete
  if (ANKETA) {
    const q = ANKETA.questions.find(x => x.key === "purpose") ||
      ANKETA.questions.find(x => (x.answers || []).some(a => a.label.startsWith("Vožnja bicikla")));
    const get = pref => ((q && q.answers) || []).find(a => a.label.startsWith(pref));
    const set = get("Šetnja"), bic = get("Vožnja bicikla");
    if (set && bic) {
      $("deljena-tekst").innerHTML = `LTS meri stres od automobila, a kej je pre svega šetalište. U anketi je <strong>${set.count} od ${ANKETA.total}</strong> ispitanika reklo da kej koristi za šetnju, a ${bic.count} za vožnju bicikla. <a href="https://nacto.org/publication/urban-bikeway-design-guide/designing-ages-abilities-new/" target="_blank" rel="noopener">NACTO-ov vodič za infrastrukturu za sve uzraste</a> za prirodne koridore i obale reka preporučuje biciklističku stazu sa odvojenim šetalištem kad je pešaka mnogo, a deljenu stazu samo kad ih je malo.`;
    }
  }
}

/* ── osetljivost ─────────────────────────────────────────────── */

function renderOsetljivost() {
  const s = D.povezanost.osetljivost;
  const base = r2().lts2_pct;
  const rows = [
    ["Obilazak do 25 %", "do 50 %", s.obilazak_50],
    ["Obilazak do 25 %", "bez ograničenja obilaska", s.bez_praga_obilaska],
    ["Jednosmerne ulice se poštuju", "zanemaruju se", s.jednosmerne_ignorisane],
    ["Stambena ulica ima mali protok (LTS 2)", "stambena ulica je LTS 3", s.stambene_kao_lts3],
    ["Brzina je jednaka ograničenju", "+10 km/h na glavnim ulicama", s.brzina_plus_10],
    ["Pešačke staze se mogu voziti", "pešačke staze i zone isključene", s.bez_pesackih_staza],
    ["Svi ulazi u koridor važe", `bez ${s.ulaza_kod_stepenica} od ${s.ulaza_ukupno} ulaza na 15 m od stepenica`, s.bez_ulaza_kod_stepenica],
  ];
  $("osetljivost-table").innerHTML = `
    <thead><tr><th class="tl">Pretpostavka</th><th class="tl">Umesto toga</th><th>LTS 2 povezano</th><th>Razlika</th></tr></thead>
    <tbody class="lts-noshade">
      <tr><td class="tl"><strong>Osnova</strong></td><td class="tl">—</td><td class="num"><strong>${br(base)} %</strong></td><td class="num">—</td></tr>
      ${rows.map(([a, b, v]) => {
        const d = v - base;
        return `<tr><td class="tl">${a}</td><td class="tl">${b}</td><td class="num">${br(v)} %</td>
          <td class="num ${d < 0 ? "lts-minus" : "lts-plus"}">${d > 0 ? "+" : ""}${br(d)}</td></tr>`;
      }).join("")}
    </tbody>`;

  $("m-stambene").textContent = `Ako ta pretpostavka ne važi, povezanost na LTS 2 pada sa ${br(base)} na ${br(s.stambene_kao_lts3)} %.`;
  $("m-jednosmerne").textContent = `Kad bi se jednosmerne ulice zanemarile, povezanost bi bila ${br(s.jednosmerne_ignorisane)} % umesto ${br(base)} %.`;
  $("metod-foot").textContent = `Stanje OSM-a: ${D.izvori.osm} · stanovništvo: WorldPop ${D.izvori.worldpop} · ${ceo(D.podaci.ulica)} ulica u zahvatu · ${ceo(s.jednosmernih_kolovoza)} jednosmernih kolovoza.`;
}

/* ── start ───────────────────────────────────────────────────── */

async function main() {
  const [d, net, mreza, ank] = await Promise.all([
    fetch(DATA + "lts.json").then(r => r.json()),
    fetch(DATA + "lts_mreza.json").then(r => r.json()),
    fetch(DATA + "staze_mreza.geojson").then(r => r.json()),
    fetch(DATA + "anketa.json").then(r => r.ok ? r.json() : null).catch(() => null),
  ]);
  D = d;
  NET = net;
  ANKETA = ank;
  renderNalazi();
  renderTabele();
  renderOsa();
  renderUlazi();
  renderPovezanost();
  renderCiljevi();
  renderOsetljivost();
  const osa = { type: "FeatureCollection",
    features: mreza.features.filter(f => f.properties.tip === "bici" && f.properties.uloga === "osa") };
  renderMap(osa);
}

main().catch(err => {
  console.error("[lts]", err);
  $("nalazi").innerHTML = '<p class="muted">Podaci nisu učitani. Pokreni <code>make lts</code>.</p>';
});
