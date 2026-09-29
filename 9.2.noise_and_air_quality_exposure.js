/* Analiza 9.2 — Buka i kvalitet vazduha.
 * Tri izvora, jer su tri različite priče:
 *   data/buka.json        (buka.py)   — indeks 0–100 po tački, za sve tri staze
 *   data/vazduh.json      (vazduh.py) — merne stanice, nivoi i NO₂ po deonici
 *   data/merne_tacke.json (docs/…)    — planirane tačke terenskog merenja
 * Renderuje profil duž trase (canvas), mapu obojenu istom skalom, tabelu po
 * deonicama, i sekciju o vazduhu sa stanicama, prekoračenjima i sezonom.
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

let D = null;                     // buka.json
let A = null;                     // vazduh.json
let T = null;                     // merne_tacke.json
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
    // poslednja oznaka bi se presekla o desnu ivicu platna
    if (xOf(k) > PF.padL + g.plotW - 16) continue;
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
  dodajMerneTacke(map);
}

/* Planirane tačke merenja: model se njima proverava, pa im je mesto na istoj
 * mapi koju proveravaju. Parovi gornji/donji bedem se razlikuju bojom. */
function dodajMerneTacke(m) {
  if (!T || !T.tacke) return;
  T.tacke.forEach(t => {
    L.circleMarker([t.lat, t.lon], {
      radius: 6, color: "#fff", weight: 2,
      fillColor: t.par ? "#1f3b2d" : "#3b4a40", fillOpacity: 1,
    }).addTo(m).bindTooltip(
      `<strong>${t.id}</strong> · km ${t.km.toFixed(2)}<br>`
      + `model: ${t.idx}<br>${t.uloga}`, { direction: "top" });
  });
  $("merne-tacke-nota").innerHTML =
    `Crne tačke su <strong>${T.tacke.length} planiranih mesta merenja</strong>.
     Birane su tako da pokriju ceo raspon modela, od najtišeg do najbučnijeg dela
     trase — jer raspon, a ne broj merenja, određuje koliko će prevod u decibele
     biti pouzdan. Tamnije tačke su parovi gornji/donji bedem na istoj kilometraži.
     <a href="${T.gpx}">GPX za telefon</a> ·
     <a href="docs/9.2-kalibracija-buke/obrazac.pdf">obrazac za štampu (PDF)</a>`;
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
  no2: "NO₂ — azot-dioksid",
};
const ZAG_KRATKO = { pm2_5: "PM2.5", pm10: "PM10", no2: "NO₂" };
const ZAG_RED = ["pm2_5", "pm10", "no2"];

const TIP_SR = { traffic: "saobraćajna", background: "pozadinska", industrial: "industrijska" };
const OKR_SR = { urban: "gradsko okruženje", suburban: "prigradsko okruženje", rural: "ruralno okruženje" };

const POLEN_LABEL = { trave: "Trave", breza: "Breza", ambrozija: "Ambrozija" };

/* Rastojanje čitljivo: metri do kilometra, dalje u kilometrima. */
function dist(m) {
  return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`;
}
function br(x, d = 1) {
  return x === null || x === undefined ? "—" : x.toFixed(d).replace(".", ",");
}
function stanicaPo(kod) { return A.stanice.find(s => s.kod === kod); }

/* ---------- stanice ---------- */

function ulogaOf(kod) {
  if (kod === A.reprezentativna) {
    return { znak: "predstavlja kej", glavna: true,
             opis: "Najbliža stazi i pozadinskog tipa — meri vazduh kakav dišu ljudi na keju, bez uticaja jedne konkretne ulice. Svi nivoi na ovoj stranici dolaze odavde." };
  }
  if (kod === A.saobracajna) {
    return { znak: "daje saobraćajni deo",
             opis: "Stoji uz prometnu saobraćajnicu. Razlika između nje i pozadinske stanice pokazuje koliko vazduhu dodaje blizina puta." };
  }
  if (kod === A.ruralna) {
    return { znak: "daje pozadinu regiona",
             opis: "Van grada. Pokazuje koliko zagađenja ima u vazduhu i pre nego što se uđe u Niš." };
  }
  return { znak: "", opis: "" };
}

function renderStanice() {
  $("stanice-grid").innerHTML = A.stanice.map(s => {
    const u = ulogaOf(s.kod);
    const pol = ZAG_RED.filter(p => (A.mereno[s.kod] || {})[p]);
    const per = pol.map(p => A.mereno[s.kod][p].glavni.period).flat();
    return `
      <div class="st-kartica${u.glavna ? " glavna" : ""}">
        <div class="st-znak">${u.znak}</div>
        <p class="st-d">${dist(s.do_koridora_m)}<span class="st-d-sub"> od staze</span></p>
        <p class="st-tip">${TIP_SR[s.tip] || s.tip} stanica, ${OKR_SR[s.okruzenje] || s.okruzenje}</p>
        <p class="st-opis">${u.opis}</p>
        <p class="st-meta">${pol.map(p => ZAG_KRATKO[p]).join(" · ")}${per.length ? ` · ${Math.min(...per)}–${Math.max(...per)}` : ""} · oznaka ${s.kod}</p>
      </div>`;
  }).join("");
}

/* Najbliža tačka trase datoj stanici — za potez koji pokazuje rastojanje. */
function najblizaTacka(st) {
  const b = D.staze.find(s => s.tip === "bici") || D.staze[0];
  let naj = null, najD = Infinity;
  for (let i = 0; i < b.points.lat.length; i++) {
    const dla = (b.points.lat[i] - st.lat) * 111.32;
    const dlo = (b.points.lon[i] - st.lon) * 111.32 * Math.cos(st.lat * Math.PI / 180);
    const d = dla * dla + dlo * dlo;
    if (d < najD) { najD = d; naj = [b.points.lat[i], b.points.lon[i]]; }
  }
  return naj;
}

function buildVazduhMap() {
  // Isečak drži koridor i stanice uz njega. Ruralna je 8,8 km severno i kad
  // uđe u okvir, ceo koridor se skupi na crticu — ona se pominje u kartici,
  // a ispod mape stoji napomena gde je.
  const bounds = L.latLngBounds([]);
  D.staze.forEach(s => s.points.lat.forEach(
    (la, i) => bounds.extend([la, s.points.lon[i]])));
  const uOkviru = A.stanice.filter(s => s.do_koridora_m <= 3000);
  uOkviru.forEach(s => bounds.extend([s.lat, s.lon]));
  const m = L.map("vazduh-map", { scrollWheelZoom: false });
  m.fitBounds(bounds, { padding: [24, 24] });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
    maxZoom: 19,
  }).addTo(m);

  // trasa kao jedna linija po lancu, da se ne crta preko praznina
  const bici = D.staze.find(s => s.tip === "bici") || D.staze[0];
  const lanci = new Map();
  bici.points.lat.forEach((la, i) => {
    const c = bici.points.chain[i];
    if (!lanci.has(c)) lanci.set(c, []);
    lanci.get(c).push([la, bici.points.lon[i]]);
  });
  lanci.forEach(pts => L.polyline(pts, {
    color: "#2f6b46", weight: 4, opacity: .85,
  }).addTo(m));

  uOkviru.forEach(s => {
    const u = ulogaOf(s.kod);
    const boja = s.kod === A.reprezentativna ? "#2f6b46"
      : s.kod === A.saobracajna ? "#c0392b" : "#6b776f";
    // isprekidani potez do trase: odgovara na „zašto baš ova stanica"
    const cilj = najblizaTacka(s);
    if (cilj) {
      L.polyline([[s.lat, s.lon], cilj], {
        color: boja, weight: 2, opacity: .7, dashArray: "5 5",
      }).addTo(m).bindTooltip(`${dist(s.do_koridora_m)} do trase`, { direction: "top" });
    }
    L.circleMarker([s.lat, s.lon], {
      radius: u.glavna ? 11 : 8, color: "#fff", weight: 2,
      fillColor: boja, fillOpacity: 1,
    }).addTo(m).bindTooltip(
      `<strong>${TIP_SR[s.tip] || s.tip} stanica</strong><br>${u.znak}<br>${dist(s.do_koridora_m)} od staze`,
      { direction: "top" });
  });

  const izvan = A.stanice.filter(s => !uOkviru.includes(s));
  if (izvan.length) {
    $("vazduh-map").insertAdjacentHTML("afterend",
      `<p class="muted mapa-nota">Izvan isečka: ${izvan.map(s =>
        `${TIP_SR[s.tip] || s.tip} stanica (${OKR_SR[s.okruzenje] || s.okruzenje}), ${dist(s.do_koridora_m)} severno od trase`
      ).join("; ")}.</p>`);
  }
}

/* ---------- nivoi ---------- */

function renderCams() {
  const red = ZAG_RED.filter(p => A.cams[p]);
  if (!red.length) { $("cams-callout").hidden = true; return; }
  const spisak = red.map(p =>
    `${ZAG_KRATKO[p]} <strong>${br(A.cams[p].odnos, 1)}×</strong>`).join(", ");
  $("cams-callout").innerHTML = `
    <p><strong>Brojevi su se popravili nagore.</strong> Ova stranica je do sada prikazivala
    satelitski model, jer je bio jedini izvor koji nam je bio poznat. Na istim danima on
    daje niže vrednosti od onoga što stanica izmeri: ${spisak} niže. Sve što sledi je
    merenje, a ne procena.</p>`;
}

function renderZagadjivaci() {
  const rep = A.mereno[A.reprezentativna];
  $("vazduh-kartice").innerHTML = ZAG_RED.filter(p => rep[p]).map(p => {
    const g = rep[p].glavni;
    const szoG = A.szo_godisnji[p], szoD = A.szo_dnevni[p];
    const puta = g.prosek / szoG;
    const zakon = A.granica_godisnja[p];
    // tri stepena, da 92 % granice ne bude opisano istom rečju kao 99 %
    const odnosZakon = zakon ? g.prosek / zakon : 0;
    const recZakon = odnosZakon >= 1 ? "preko zakonske granice od"
      : odnosZakon >= 0.95 ? "na samoj zakonskoj granici od"
      : odnosZakon >= 0.85 ? "blizu zakonske granice od" : null;
    return `
      <div class="vazduh-kartica">
        <h4>${ZAG_LABEL[p] || p}</h4>
        <p class="vk-broj${g.pct_preko_szo >= 20 ? " warn" : ""}">${br(g.prosek)}<span class="vk-jed"> µg/m³</span></p>
        <p class="vk-sub">prosek ${g.period[0]}–${g.period[1]} — <strong>${br(puta)}×</strong> smernica SZO (${br(szoG, szoG < 10 ? 0 : 0)})</p>
        <div class="vk-bar"><span style="width:${Math.min(100, g.pct_preko_szo)}%"></span></div>
        <p class="vk-note">${g.pct_preko_szo} % dana preko dnevne smernice (${br(szoD, 0)} µg/m³)</p>
        ${recZakon ? `<p class="vk-zakon">${recZakon} ${br(zakon, 0)} µg/m³</p>` : ""}
      </div>`;
  }).join("");
}

/* Godine sa podatkom za PM10, po stanici: [{kod, godine:[[god, dana]]}] */
function pm10Serije() {
  return [A.saobracajna, A.reprezentativna]
    .filter(k => k && (A.mereno[k] || {}).pm10)
    .map(k => ({
      kod: k,
      godine: Object.entries(A.mereno[k].pm10.godine)
        .filter(([, v]) => v.preko_granice !== null)
        .map(([y, v]) => [Number(y), v.preko_granice])
        .sort((a, b) => a[0] - b[0]),
    }));
}

function renderZakon() {
  const dop = A.granica_dopusteno_dana.pm10;
  const s = pm10Serije().find(x => x.kod === A.saobracajna);
  if (!s || !s.godine.length) { $("zakon-callout").hidden = true; return; }
  const vals = s.godine.map(([, n]) => n);
  const najgora = s.godine[vals.indexOf(Math.max(...vals))];
  const svePreko = vals.every(n => n > dop);
  $("zakon-callout").innerHTML = `
    <p><strong>Granica nije prekoračena — ona se prekoračuje redovno.</strong>
    ${svePreko ? "U svakoj od" : "U"} ${s.godine.length} godina za koje postoje merenja
    PM10 je prešao dnevnu granicu između <strong>${Math.min(...vals)}</strong> i
    <strong>${Math.max(...vals)}</strong> dana, a zakon dopušta ${dop}. Najgora je bila
    ${najgora[0]}. godina, sa ${najgora[1]} dana — što je
    ${br(najgora[1] / dop)}× više od dopuštenog.</p>`;
}

function renderPm10Godine() {
  const serije = pm10Serije();
  if (!serije.length) return;
  const dop = A.granica_dopusteno_dana.pm10;
  // ceo raspon godina, sa praznim mestima tamo gde merenja nema — bez toga
  // grafikon preskače 2015. i 2016. i izgleda kao neprekidan niz
  const sve = serije.flatMap(s => s.godine.map(([y]) => y));
  const godine = [];
  for (let y = Math.min(...sve); y <= Math.max(...sve); y++) godine.push(y);
  const max = Math.max(...serije.flatMap(s => s.godine.map(([, n]) => n)), dop) * 1.08;
  const boja = k => k === A.saobracajna ? "gg-saob" : "gg-poz";
  const kolone = godine.map(y => {
    const stupci = serije.map(s => {
      const hit = s.godine.find(([yy]) => yy === y);
      if (!hit) return "";
      return `<span class="gg-bar ${boja(s.kod)}" style="height:${100 * hit[1] / max}%"
                title="${y}: ${hit[1]} dana (${TIP_SR[stanicaPo(s.kod).tip]} stanica)">
                <span class="gg-val">${hit[1]}</span></span>`;
    }).join("");
    return `<div class="gg-col"><div class="gg-stupci">${stupci}</div>
      <span class="gg-ime"><span class="gg-vek">20</span>${String(y).slice(2)}</span></div>`;
  }).join("");
  $("pm10-godine").innerHTML = `
    <div class="gg-plot" style="--dop:${100 * dop / max}">
      ${kolone}
      <span class="gg-dop-oznaka">dopušteno ${dop}</span>
    </div>
    <p class="mg-legend">
      <span class="mg-key gg-key-saob"></span> saobraćajna stanica
      <span class="mg-key gg-key-poz"></span> stanica kod keja
      <span class="gg-praznine">prazna mesta su godine bez dovoljno merenja</span></p>`;
}

function renderMesecno() {
  const pm = (A.mereno[A.reprezentativna] || {}).pm2_5;
  if (!pm) return;
  const m = pm.glavni.po_mesecu;
  const szo = A.szo_dnevni.pm2_5;
  const max = Math.max(...m.filter(x => x !== null), szo);
  $("pm-mesecno").innerHTML = `
    <div class="mg-plot" style="--szo:${100 * szo / max}">
      ${m.map((v, i) => {
        if (v === null) return `<div class="mg-col"><span class="mg-ime">${A.meseci[i]}</span></div>`;
        return `<div class="mg-col" title="${A.meseci[i]}: ${br(v)} µg/m³">
            <span class="mg-val">${Math.round(v)}</span>
            <span class="mg-bar${v > szo ? " over" : ""}" style="height:${100 * v / max}%"></span>
            <span class="mg-ime">${A.meseci[i]}</span>
          </div>`;
      }).join("")}
    </div>
    <p class="mg-legend"><span class="mg-key over"></span> preko dnevne smernice SZO (${br(szo, 0)} µg/m³)
      <span class="mg-key ok"></span> ispod smernice</p>`;
}

/* ---------- NO₂ po deonicama ---------- */

/* Najčistija i najprljavija kombinacija deonice i staze — one nose poentu:
 * osnova je ista, razlikuje se samo saobraćajni deo. */
function krajnostiNo2() {
  const svi = [];
  Object.entries(A.po_deonici).forEach(([tip, po]) =>
    Object.entries(po).forEach(([dn, v]) => svi.push({ tip, dn, ...v })));
  svi.sort((a, b) => a.no2 - b.no2);
  return [svi[0], svi[svi.length - 1]];
}

function renderNo2Raspodela() {
  if (!A.model || !A.po_deonici) { $("no2-raspodela").hidden = true; return; }
  const [min, max] = krajnostiNo2();
  const reg = A.model.regionalno, urb = A.model.urbano;
  const skala = max.no2;
  const bar = (x, naslov) => `
    <div class="rp-red">
      <div class="rp-ime">${naslov}<span class="rp-ime-sub">${STAZA_SHORT[x.tip]}</span></div>
      <div class="rp-traka">
        <span class="rp-seg rp-reg" style="width:${100 * reg / skala}%" title="regionalna pozadina ${br(reg)} µg/m³"></span>
        <span class="rp-seg rp-urb" style="width:${100 * urb / skala}%" title="ostatak grada ${br(urb)} µg/m³"></span>
        <span class="rp-seg rp-saob" style="width:${100 * x.saobracajni / skala}%" title="blizina saobraćaja ${br(x.saobracajni)} µg/m³"></span>
      </div>
      <div class="rp-suma">${br(x.no2)}<span class="rp-jed"> µg/m³</span></div>
    </div>`;
  $("no2-raspodela").innerHTML =
    bar(min, `Najčistija: ${min.dn}`) + bar(max, `Najizloženija: ${max.dn}`) + `
    <p class="mg-legend">
      <span class="mg-key rp-key-reg"></span> pozadina regiona
      <span class="mg-key rp-key-urb"></span> ostatak grada
      <span class="mg-key rp-key-saob"></span> blizina saobraćaja</p>
    <p class="muted rp-nota">Prva dva dela su izmerena i ista su duž cele trase. Razlikuje se
      samo treći: između najčistije i najizloženije deonice stoji
      <strong>${br(max.no2 - min.no2)} µg/m³</strong>, dok preostalih ${br(reg + urb)} nosi
      grad podjednako svuda.</p>`;
}

function renderNo2Table() {
  if (!A.po_deonici) { $("no2-table").hidden = true; return; }
  const tipovi = D.staze.map(s => s.tip).filter(t => A.po_deonici[t]);
  const head = `
    <thead><tr><th>Deonica</th>
      ${tipovi.map(t => `<th class="num">${STAZA_SHORT[t]}</th>`).join("")}
    </tr></thead>`;
  const red = (ime, vals) => {
    const brojevi = vals.filter(v => v !== null);
    const najbolji = Math.min(...brojevi);
    return `<tr><td>${ime}</td>${vals.map(v => v === null ? '<td class="num">—</td>'
      : `<td class="num${v === najbolji ? " pk-best" : ""}">${br(v)}</td>`).join("")}</tr>`;
  };
  const tela = A.deonice
    .filter(dn => tipovi.some(t => A.po_deonici[t][dn]))
    .map(dn => red(dn, tipovi.map(t => (A.po_deonici[t][dn] || {}).no2 ?? null)))
    .join("");
  // cela staza: prosek po deonicama otežan brojem tačaka
  const cele = tipovi.map(t => {
    const v = Object.values(A.po_deonici[t]);
    const n = v.reduce((a, x) => a + x.n, 0);
    return n ? v.reduce((a, x) => a + x.no2 * x.n, 0) / n : null;
  });
  $("no2-table").innerHTML = head + `<tbody>${tela}
    ${red("<strong>Cela staza</strong>", cele)}</tbody>`;
}

function renderPolen() {
  const vrste = Object.entries((A.polen || {}).vrste || {});
  if (!vrste.length) return;
  $("polen-kalendar").innerHTML = vrste.map(([k, v]) => {
    const max = Math.max(...v.po_mesecu.filter(x => x !== null), 1);
    return `
      <div class="pk-red">
        <div class="pk-ime">${POLEN_LABEL[k] || k}</div>
        <div class="pk-traka">
          ${v.po_mesecu.map((x, i) => {
            const t = x === null ? 0 : x / max;
            return `<span class="pk-cel" style="--t:${t.toFixed(3)}"
                      title="${A.meseci[i]}: ${x === null ? "nema podataka" : br(x) + " zrna/m³"}"></span>`;
          }).join("")}
        </div>
        <div class="pk-vrh">vrhunac ${v.vrhunac_mesec}</div>
      </div>`;
  }).join("")
    + `<div class="pk-osa">${A.meseci.map(m => `<span>${m}</span>`).join("")}</div>`;
}

function renderVazduh() {
  if (!A) { $("vazduh").hidden = true; return; }
  const rep = stanicaPo(A.reprezentativna);
  if (rep) $("rep-d").textContent = dist(rep.do_koridora_m);
  renderCams();
  renderStanice();
  buildVazduhMap();
  renderZagadjivaci();
  renderZakon();
  renderPm10Godine();
  renderMesecno();
  renderNo2Raspodela();
  renderNo2Table();
  renderPolen();
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
    const r = await fetch(DATA + "buka.json");
    D = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam buka.json:", e);
    return;
  }
  // vazduh je odvojen fajl i odvojena priča: ako on padne, buka se i dalje
  // prikazuje, samo se sekcija o vazduhu sakrije
  try {
    const r = await fetch(DATA + "vazduh.json");
    A = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam vazduh.json:", e);
  }
  try {
    const r = await fetch(DATA + "merne_tacke.json");
    T = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam merne_tacke.json:", e);
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
