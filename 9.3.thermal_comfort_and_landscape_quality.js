/* Analiza 9.3 — Termalni komfor.
 * Čita data/termalni.json (termalni.py): po tački svake od tri staze (10 m)
 * UTCI i Tmrt na vruć letnji dan, faktor vidljivosti neba, sati u senci, i
 * mesta predaha. Renderuje profil duž trase (canvas), mapu obojenu istom
 * skalom, sat po sat, tabelu po deonicama i spisak predaha. Uz to čita
 * data/river_views.json za drugu polovinu sekcije — kvalitet predela.
 */
"use strict";

const DATA = "data/";

/* Pojasevi su kategorije UTCI skale, ne naša podela. Ispod 26 °C nema stresa,
 * a toga na vruć dan na koridoru nema nijedan metar — pa se te kategorije i
 * ne crtaju, samo se pominju u legendi kad se pojave. */
const KATEGORIJE = [
  { max: 26, color: "#2f6b46", label: "bez toplotnog stresa" },
  { max: 32, color: "#7fa05c", label: "umeren toplotni stres" },
  { max: 38, color: "#e0a03a", label: "jak toplotni stres" },
  { max: 46, color: "#c0392b", label: "vrlo jak toplotni stres" },
  { max: 999, color: "#7b241c", label: "ekstremni toplotni stres" },
];

const STAZA_SHORT = {
  bici: "Biciklistička",
  pesacki_gornji: "Pešačka — gornji bedem",
  pesacki_donji: "Pešačka — donji bedem",
};

let D = null;      // termalni.json
let V = null;      // river_views.json — druga polovina sekcije 9.3
let S = null;
let map = null;
let termoLayer = null;
let predahLayer = null;
const state = { staza: "bici" };

function $(id) { return document.getElementById(id); }
function br(x, d = 1) { return x.toFixed(d).replace(".", ","); }
function katOf(v) { return KATEGORIJE.find(k => v < k.max) || KATEGORIJE[KATEGORIJE.length - 1]; }
function colorOf(v) { return katOf(v).color; }

/* ---------- ključni nalazi ---------- */

function renderNalazi() {
  const b = D.staze.find(s => s.tip === "bici") || D.staze[0];
  const jak = Object.entries(b.totals.kategorije)
    .filter(([ime]) => ime.includes("jak") || ime.includes("ekstremni"))
    .reduce((a, [, v]) => a + v, 0);
  const kl = (D.oprema || {}).klupe;
  const u = D.uporedba;

  const karte = [
    { broj: `${br(jak, 0)} %`, warn: true,
      tekst: `trase je u <strong>jakom toplotnom stresu</strong> vrelog popodneva. Preostalih ${br(100 - jak, 0)} % je u umerenom — potpuno ugodnog dela nema nijedan metar.` },
    { broj: `${br(u.tmrt_razlika, 0)} °C`,
      tekst: `za toliko krošnja spušta zračenje koje pada na čoveka. Na skali osećaja to je <strong>${br(u.utci_razlika)} °C</strong> i jedna cela kategorija stresa manje.` },
  ];
  if (kl) {
    karte.push({ broj: `${kl.bez_senke} od ${kl.ukupno}`, warn: true,
      tekst: `klupa nema <strong>nijedan sat senke</strong> u najtoplijem delu dana. Prosečan UTCI na klupi je ${br(kl.utci)} °C.` });
  }
  $("nalazi").innerHTML = karte.map(k => `
    <div class="nalaz${k.warn ? " nalaz-warn" : ""}">
      <p class="nalaz-broj">${k.broj}</p>
      <p class="nalaz-tekst">${k.tekst}</p>
    </div>`).join("");
}

function renderScenario() {
  const sc = D.scenario;
  const s = sc.po_satu;
  const tmin = Math.min(...s.map(x => x.vazduh));
  const tmax = Math.max(...s.map(x => x.vazduh));
  $("scenario-callout").innerHTML = `
    <p><strong>Računa se vruć vedar dan, ne prosečan.</strong> Uzeto je
    ${sc.dana_u_uzorku} najtoplijih od ${sc.dana_ukupno} dana oko letnjeg
    solsticija, ${sc.godine[0]}–${sc.godine[1]}: vazduh
    ${br(tmin)}–${br(tmax)} °C, vetar oko ${br(s[0].vetar_ms)} m/s,
    vlažnost oko ${s[0].vlaga} %. Kišni i oblačni dani bi razblažili ono što se
    meri — senka se ne sadi zbog njih.</p>`;
}

/* ---------- sunce protiv senke ---------- */

function renderUporedba() {
  const u = D.uporedba;
  const red = (x, ime, boja) => `
    <div class="up-red">
      <div class="up-ime">${ime}</div>
      <div class="up-traka"><span style="width:${100 * (x.utci - 24) / 18}%;background:${boja}"></span></div>
      <div class="up-broj">${br(x.utci)}<span class="up-jed"> °C</span></div>
      <div class="up-kat">${x.kategorija}</div>
    </div>`;
  $("uporedba").innerHTML =
    red(u.sunce, "Na otvorenom", colorOf(u.sunce.utci))
    + red(u.senka, "Pod krošnjom", colorOf(u.senka.utci))
    + `<p class="muted up-nota">Zračenje koje pada na telo (Tmrt) razlikuje se
       <strong>${br(u.tmrt_razlika)} °C</strong> — ${br(u.sunce.tmrt)} prema
       ${br(u.senka.tmrt)} °C. Osećaj se ne menja za toliko jer ga vazduh i vetar
       delimično izravnaju, ali je razlika dovoljna da se pređe granica kategorije.</p>`;
}

/* ---------- profil ---------- */

const PF = { padL: 46, padR: 12, padT: 10, padB: 26, h: 190 };

function profGeom() {
  const wrapW = $("profil-wrap").clientWidth;
  return { wrapW, plotW: wrapW - PF.padL - PF.padR, plotH: PF.h - PF.padT - PF.padB };
}

function profOpseg() {
  // zajednički opseg za sve tri staze, da se prekidač ne čita kao promena
  let lo = Infinity, hi = -Infinity;
  D.staze.forEach(s => s.points.utci.forEach(v => {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }));
  return [Math.floor(lo - 1), Math.ceil(hi + 1)];
}

function drawProfil() {
  const cv = $("termo-profil");
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
  const [lo, hi] = profOpseg();
  const { km, utci, deonica } = S.points;
  const xOf = k => PF.padL + (k / totalKm) * g.plotW;
  const yOf = v => PF.padT + g.plotH * (1 - (v - lo) / (hi - lo));
  const colW = Math.max(1, (D.step_m / 1000 / totalKm) * g.plotW + 0.5);

  ctx.font = "10px system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let v = lo; v <= hi; v += 2) {
    ctx.strokeStyle = "rgba(168,177,171,.45)";
    ctx.beginPath();
    ctx.moveTo(PF.padL, yOf(v));
    ctx.lineTo(PF.padL + g.plotW, yOf(v));
    ctx.stroke();
    ctx.fillStyle = "#6b776f";
    ctx.fillText(v + "°", PF.padL - 6, yOf(v));
  }
  // granice kategorija su vodoravne linije preko celog grafikona
  KATEGORIJE.forEach(k => {
    if (k.max <= lo || k.max >= hi) return;
    ctx.strokeStyle = k.color;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(PF.padL, yOf(k.max));
    ctx.lineTo(PF.padL + g.plotW, yOf(k.max));
    ctx.stroke();
    ctx.setLineDash([]);
  });

  for (let i = 0; i < km.length; i++) {
    ctx.fillStyle = colorOf(utci[i]);
    const y = yOf(utci[i]);
    ctx.fillRect(xOf(km[i]), y, colW, yOf(lo) - y);
  }

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
      ctx.lineTo(xOf(km[i]), yOf(lo));
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.fillStyle = "#3b4a40";
    ctx.fillText(D.deonice[deonica[i]], xOf(km[i]) + 4, PF.padT + 2);
    prev = deonica[i];
  }

  ctx.textAlign = "center";
  ctx.fillStyle = "#6b776f";
  for (let k = 0; k <= Math.floor(totalKm); k += 2) {
    // poslednja oznaka bi se presekla o desnu ivicu platna
    if (xOf(k) > PF.padL + g.plotW - 16) continue;
    ctx.fillText(k + " km", xOf(k), yOf(lo) + 7);
  }
}

function nearestIndex(arr, k) {
  let lo = 0, hi = arr.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] < k) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(arr[lo - 1] - k) < Math.abs(arr[lo] - k)) lo--;
  return Math.abs(arr[lo] - k) > 0.15 ? -1 : lo;
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
    const v = S.points.utci[i];
    const kat = katOf(v);
    tip.querySelector(".tt-state").innerHTML =
      `<span style="color:${kat.color}">●</span> ${br(v)} °C — ${kat.label}`;
    tip.querySelector(".tt-meta").textContent =
      `km ${S.points.km[i].toFixed(2)} · ${D.deonice[S.points.deonica[i]]} · `
      + `zračenje ${br(S.points.tmrt[i])} °C · nebo ${Math.round(S.points.svf[i] * 100)} % · `
      + `senka ${S.points.senka_sati[i]} od ${D.sati.length} h`;
    tip.hidden = false;
    const tw = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(mx - tw / 2, g.wrapW - tw - 4)) + "px";
    tip.style.top = "4px";
  });
  wrap.addEventListener("mouseleave", hide);
}

function renderKatLegend() {
  const prisutne = new Set();
  D.staze.forEach(s => s.points.utci.forEach(v => prisutne.add(katOf(v).label)));
  $("kat-legend").innerHTML = KATEGORIJE.filter(k => prisutne.has(k.label)).map(k => {
    const i = KATEGORIJE.indexOf(k);
    const lo = i === 0 ? "" : `${KATEGORIJE[i - 1].max}–`;
    return `<span class="hl-item"><span class="hl-swatch" style="background:${k.color}"></span> ${k.label} <span class="muted">(${lo}${k.max} °C)</span></span>`;
  }).join("");
}

/* ---------- mapa ---------- */

const TermoCanvasLayer = L.Layer.extend({
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
    const { lat, lon, km, chain, utci } = S.points;
    const stepKm = D.step_m / 1000;
    const pts = km.map((_, i) => m.latLngToContainerPoint([lat[i], lon[i]]));
    for (let i = 1; i < km.length; i++) {
      if (chain[i] !== chain[i - 1]) continue;
      if (km[i] - km[i - 1] > stepKm * 1.8) continue;
      ctx.strokeStyle = colorOf(utci[i]);
      ctx.beginPath();
      ctx.moveTo(pts[i - 1].x, pts[i - 1].y);
      ctx.lineTo(pts[i].x, pts[i].y);
      ctx.stroke();
    }
  },
});

function buildMap() {
  const bounds = L.latLngBounds([]);
  D.staze.forEach(s => s.points.lat.forEach(
    (la, i) => bounds.extend([la, s.points.lon[i]])));
  map = L.map("termo-map", { scrollWheelZoom: false });
  map.fitBounds(bounds, { padding: [18, 18] });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
    maxZoom: 19,
  }).addTo(map);
  termoLayer = new TermoCanvasLayer();
  termoLayer.addTo(map);
  predahLayer = L.layerGroup().addTo(map);
  crtajPredahe();
}

function crtajPredahe() {
  if (!predahLayer) return;
  predahLayer.clearLayers();
  S.predasi.forEach(p => {
    L.circleMarker([p.lat, p.lon], {
      radius: Math.min(11, 4 + p.duzina_m / 60), color: "#fff", weight: 2,
      fillColor: "#1f3b2d", fillOpacity: 1,
    }).addTo(predahLayer).bindTooltip(
      `<strong>km ${br(p.km, 2)}</strong> · ${p.duzina_m} m u senci<br>`
      + `UTCI ${br(p.utci)} °C · ${p.deonica}<br>`
      + (p.klupe ? `klupa: ${p.klupe}` : "bez klupe"),
      { direction: "top" });
  });
}

/* ---------- sat po sat ---------- */

function renderSatGraf() {
  const red = S.po_satu;
  // Stubići ne počinju od nule nego od granice kategorije ispod najniže
  // vrednosti. Da počnu tik ispod minimuma, razlika od 1,6 °C izgledala bi
  // kao petostruka — a da počnu od nule, ne bi se videla uopšte. Baza se
  // ispisuje, da razmera ne obmanjuje.
  const min = Math.min(...red.map(x => x.utci));
  const max = Math.max(...red.map(x => x.utci));
  const baza = KATEGORIJE.map(k => k.max).filter(g => g < min).pop() || 0;
  const vrh = max + (max - baza) * 0.12;
  $("sat-graf").innerHTML = `
    <div class="sg-plot">
      ${red.map(x => {
        const h = 100 * (x.utci - baza) / (vrh - baza);
        return `<div class="sg-col" title="${x.sat}h: UTCI ${br(x.utci)} °C, zračenje ${br(x.tmrt)} °C">
            <span class="sg-val">${br(x.utci)}</span>
            <span class="sg-bar" style="height:${h}%;background:${colorOf(x.utci)}"></span>
            <span class="sg-ime">${x.sat}h</span>
          </div>`;
      }).join("")}
    </div>
    <p class="mg-legend">Stubići počinju od ${baza}&nbsp;°C, granice kategorije —
      ne od nule. Vrh je u ${red.reduce((a, b) => a.utci > b.utci ? a : b).sat}
      časova, ne u podne: kad je Sunce visoko, na uspravno telo pada manji deo snopa.</p>`;
}

/* ---------- činioci ---------- */

function renderCinioci() {
  const t = S.totals;
  const stavke = [
    { naslov: "Otvoreno nebo", v: `${Math.round(t.svf * 100)} %`,
      opis: "koliko nebeskog svoda tačka prosečno vidi. Što je otvorenije, to više Sunca stiže — i to manje zaklona ima." },
    { naslov: "Senka u vrelim satima", v: `${br(t.sati_u_senci)} od ${D.sati.length} h`,
      opis: "prosečan broj sati u kojima krošnja stoji između Sunca i staze." },
    { naslov: "Zračenje na telo", v: `${br(t.tmrt)} °C`,
      opis: "srednja radijantna temperatura. Ovo je veličina koju senka zapravo menja — vazduh se duž 13 km praktično ne menja." },
    { naslov: "Najtoplija deonica", v: najgoraDeonica(),
      opis: "deonica sa najvišim prosečnim UTCI na izabranoj stazi." },
  ];
  $("cinioci").innerHTML = stavke.map(x => `
    <div class="cinilac">
      <div class="ci-broj">${x.v}</div>
      <div class="ci-naslov">${x.naslov}</div>
      <p class="ci-opis">${x.opis}</p>
    </div>`).join("");
}

function najgoraDeonica() {
  const e = Object.entries(S.by_deonica);
  if (!e.length) return "—";
  const [ime, v] = e.reduce((a, b) => a[1].utci > b[1].utci ? a : b);
  return `${ime} <span class="ci-sub">${br(v.utci)} °C</span>`;
}

/* ---------- tabele ---------- */

function renderTable() {
  const head = `
    <thead><tr>
      <th>Deonica</th><th>km</th><th>UTCI</th><th class="tl">Kategorija</th>
      <th>Zračenje</th><th>Nebo</th><th>Senka</th>
    </tr></thead>`;
  const row = (ime, v, km) => `
    <tr>
      <td>${ime}</td>
      <td class="num">${km}</td>
      <td class="num"><span class="idx-pill" style="background:${colorOf(v.utci)}">${br(v.utci)}</span></td>
      <td>${katOf(v.utci).label}</td>
      <td class="num">${br(v.tmrt)} °C</td>
      <td class="num">${Math.round(v.svf * 100)} %</td>
      <td class="num">${br(v.sati_u_senci)} h</td>
    </tr>`;
  const body = D.deonice.filter(dn => S.by_deonica[dn])
    .map(dn => {
      const v = S.by_deonica[dn];
      return row(dn, v, `${v.km_start.toFixed(1)}–${v.km_end.toFixed(1)}`);
    }).join("")
    + row("<strong>Cela staza</strong>", S.totals, `0–${D.osa_km.toFixed(1)}`);
  $("termo-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

function renderPredasi() {
  const t = S.totals;
  const naj = t.najduzi_bez_predaha;
  $("predah-stats").innerHTML = [
    { v: t.predaha, sub: "mesta predaha", note: `ukupno ${t.predah_m} m` },
    { v: br(t.pct_predah) + " %", sub: "trase je predah", note: `senka bar ${D.predah.min_sati} od ${D.sati.length} h`,
      warn: t.pct_predah < 10 },
    { v: br(naj.km, 1) + " km", sub: "najduži potez bez ijednog", note: `km ${br(naj.od, 1)}–${br(naj.do, 1)}`,
      warn: naj.km > 2 },
    { v: t.predah_sa_klupom, sub: "predaha ima klupu", note: `od ukupno ${t.predaha}`,
      warn: t.predah_sa_klupom === 0 },
  ].map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.sub}</div>
      <div class="shade-stat-sub">${x.note}</div>
    </div>`).join("");

  const kl = (D.oprema || {}).klupe;
  if (kl) {
    $("klupe-callout").innerHTML = `
      <p><strong>Klupe postoje — samo ne tamo gde ima hlada.</strong> Duž koridora
      je mapirano ${kl.ukupno} klupa. Od njih ${kl.bez_senke} nema
      <strong>nijedan sat senke</strong> između ${D.sati[0]} i ${D.sati[D.sati.length - 1]} časova,
      a ${kl.u_trajnoj_senci === 0 ? "nijedna nije" : `samo ${kl.u_trajnoj_senci} je`}
      u senci ceo taj deo dana. Prosečan UTCI na klupi je ${br(kl.utci)} °C —
      ${kl.kategorija}. Sesti na njih u letnje popodne nije odmor.</p>`;
  } else {
    $("klupe-callout").hidden = true;
  }

  const head = `<thead><tr><th>km</th><th>Dužina</th><th>UTCI</th>
    <th class="tl">Deonica</th><th class="tl">Oprema</th></tr></thead>`;
  const body = S.predasi.length ? S.predasi.map(p => `
    <tr>
      <td class="num">${br(p.km, 2)}</td>
      <td class="num">${p.duzina_m} m</td>
      <td class="num"><span class="idx-pill" style="background:${colorOf(p.utci)}">${br(p.utci)}</span></td>
      <td>${p.deonica}</td>
      <td>${[p.klupe ? `${p.klupe} klupa` : "", p.letnjikovci ? `${p.letnjikovci} letnjikovac` : ""]
        .filter(Boolean).join(", ") || '<span class="muted">nema</span>'}</td>
    </tr>`).join("")
    : `<tr><td colspan="5" class="muted">Na ovoj stazi nema nijednog poteza koji ostaje u senci.</td></tr>`;
  $("predah-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

/* ---------- kvalitet predela ---------- */

function renderPredeo() {
  if (!V) { $("predeo").hidden = true; return; }
  const s = V.staze.find(x => x.tip === state.staza) || V.staze[0];
  const t = s.totals;
  $("predeo-stats").innerHTML = [
    { v: br(t.pct_view) + " %", sub: "trase vidi Nišavu", note: `ugao pogleda ${br(t.avg_view_deg, 0)}°`,
      warn: t.pct_view < 50 },
    { v: t.median_water_m + " m", sub: "do vode", note: "medijana rastojanja" },
    { v: br(t.pct_potential, 0) + " %", sub: "geometrijski moguće", note: "bez zelenila reka bi se videla svuda" },
    { v: br(t.pct_potential - t.pct_view, 0) + " %", sub: "zaklanja zelenilo", note: "sav gubitak pogleda je vegetacija" },
  ].map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.sub}</div>
      <div class="shade-stat-sub">${x.note}</div>
    </div>`).join("");

  const tips = V.staze.map(x => x.tip);
  const head = `<thead><tr><th>Deonica</th>
    ${tips.map(x => `<th class="num">${STAZA_SHORT[x] || x}</th>`).join("")}</tr></thead>`;
  const red = (ime, vals) => {
    const best = Math.max(...vals.filter(v => v !== null));
    return `<tr><td>${ime}</td>${vals.map(v => v === null ? '<td class="num">—</td>'
      : `<td class="num${v === best ? " pk-best" : ""}">${br(v)} %</td>`).join("")}</tr>`;
  };
  const tela = V.deonice.filter(dn => V.staze.some(x => x.by_deonica[dn]))
    .map(dn => red(dn, V.staze.map(x => (x.by_deonica[dn] || {}).pct_view ?? null)))
    .join("");
  $("predeo-table").innerHTML = head + `<tbody>${tela}
    ${red("<strong>Cela staza</strong>", V.staze.map(x => x.totals.pct_view))}</tbody>`;

  // zapadne deonice vide reku skoro svuda, istočne jedva — a baš su istočne
  // one koje imaju senku. To je ista krošnja, posmatrana sa dve strane.
  const zapad = ["Medoševac", "Centar"].map(dn => (s.by_deonica[dn] || {}).pct_view)
    .filter(v => v !== undefined);
  const istok = ["Brzi Brod", "Niška Banja"].map(dn => (s.by_deonica[dn] || {}).pct_view)
    .filter(v => v !== undefined);
  const T = D.staze.find(x => x.tip === state.staza) || D.staze[0];
  // Sati senke pokazuju istu vezu jasnije od UTCI: razlika u osećaju je
  // prigušena vazduhom i vetrom, a razlika u zaklonu nije.
  const sZapad = ["Medoševac", "Centar"].map(dn => (T.by_deonica[dn] || {}).sati_u_senci)
    .filter(v => v !== undefined);
  const sIstok = ["Brzi Brod", "Niška Banja"].map(dn => (T.by_deonica[dn] || {}).sati_u_senci)
    .filter(v => v !== undefined);
  const sr = a => a.reduce((x, y) => x + y, 0) / a.length;
  if (zapad.length && istok.length && sZapad.length && sIstok.length) {
    $("predeo-callout").innerHTML = `
      <p><strong>Ista krošnja, dve strane.</strong> Na zapadnoj polovini
      (Medoševac, Centar) reka se vidi sa ${br(sr(zapad), 0)} % trase — ali
      senke tamo ima ${br(sr(sZapad))} sata od ${D.sati.length}. Na istočnoj
      (Brzi Brod, Niška Banja) pogled pada na ${br(sr(istok), 0)} %, a senke
      ima ${br(sr(sIstok))} sata. Drveće koje zaklanja reku isto je ono koje
      pravi hlad, i to se vidi u brojevima: <strong>sav gubitak pogleda otpada
      na zelenilo</strong>, jer je geometrijski reka vidljiva sa cele trase.
      Odluka gde se seče i gde se sadi zato nije popravka jednog bez cene po
      drugo, nego izbor između pogleda i hlada.</p>`;
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
  renderSatGraf();
  renderCinioci();
  renderTable();
  renderPredasi();
  renderPredeo();
  if (termoLayer) termoLayer.redraw();
  crtajPredahe();
}

function renderStats() {
  const t = S.totals;
  const tiles = [
    { v: br(t.utci) + " °C", sub: "prosečan UTCI", note: katOf(t.utci).label,
      warn: t.utci >= 32 },
    { v: br(t.utci_max) + " °C", sub: "najtoplija tačka", note: katOf(t.utci_max).label,
      warn: t.utci_max >= 38 },
    { v: br(t.tmrt) + " °C", sub: "zračenje na telo", note: "srednja radijantna temp." },
    { v: br(t.sati_u_senci) + " h", sub: `u senci, od ${D.sati.length}`,
      note: `nebo otvoreno ${Math.round(t.svf * 100)} %`, warn: t.sati_u_senci < 1 },
  ];
  $("termo-stats").innerHTML = tiles.map(x => `
    <div class="shade-stat">
      <div class="shade-stat-value${x.warn ? " warn" : ""}">${x.v}</div>
      <div class="shade-stat-label">${x.sub}</div>
      <div class="shade-stat-sub">${x.note}</div>
    </div>`).join("");
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
    const r = await fetch(DATA + "termalni.json");
    D = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam termalni.json:", e);
    return;
  }
  // pogled na reku je druga polovina iste sekcije okvira; ako padne,
  // termalni deo se i dalje prikazuje
  try {
    const r = await fetch(DATA + "river_views.json");
    V = await r.json();
  } catch (e) {
    console.error("Ne mogu da učitam river_views.json:", e);
  }
  S = D.staze.find(s => s.tip === state.staza) || D.staze[0];
  state.staza = S.tip;

  renderNalazi();
  renderScenario();
  renderUporedba();
  buildStazaPills();
  renderKatLegend();
  renderStats();
  drawProfil();
  bindProfilTooltip();
  renderSatGraf();
  renderCinioci();
  renderTable();
  buildMap();
  renderPredasi();
  renderPredeo();

  let t = null;
  window.addEventListener("resize", () => {
    clearTimeout(t);
    t = setTimeout(drawProfil, 150);
  });
}

init();
