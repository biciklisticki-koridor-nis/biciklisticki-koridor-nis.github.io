/* Nišavski biciklistički koridor — main script.
 * Loads stats + GeoJSON layers, renders KPI tiles, bar charts, and Leaflet map.
 */

const DATA = "data/";

// ---------- KPI + bar chart rendering ----------

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function bars(containerId, rows, opts = {}) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const max = opts.max ?? Math.max(...rows.map(r => r.value));
  el.innerHTML = rows.map(r => {
    const pct = max > 0 ? Math.max(2, (r.value / max) * 100) : 0;
    return `
      <div class="bar-row">
        <div class="label">${r.label}</div>
        <div class="track"><div class="fill ${r.color || ""}" style="width:${pct}%"></div></div>
        <div class="value">${r.display ?? r.value}</div>
      </div>`;
  }).join("");
}

function fmtM(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

async function loadStats() {
  const r = await fetch(DATA + "stats.json");
  const s = await r.json();

  setText("kpi-trasa",      s.trasa_km.toFixed(2));
  setText("kpi-prekidi",    s.counts.prekidi);
  setText("kpi-osvetljenje", s.counts.osvetljenje);
  setText("kpi-klupe",      s.counts.klupe);
  setText("kpi-stepenice",  s.counts.stepenice);
  setText("kpi-rampe",      s.counts.rampe);

  setText("kpi-prekidi-density",    s.density.prekidi_m_per_prekid);
  setText("kpi-osvetljenje-density", s.density.osvetljenje_m_per_lamp);
  setText("kpi-klupe-density",      s.density.klupe_m_per_klupa);

  setText("staze-total", Math.round(s.staze.total_m));

  bars("bars-podloga", [
    { label: "Zemljana",  value: s.staze.zemljana_m,  display: `${fmtM(s.staze.zemljana_m)} · ${s.staze.zemljana_pct}%`,  color: "earth" },
    { label: "Asfaltirana", value: s.staze.asfalt_m,  display: `${fmtM(s.staze.asfalt_m)} · ${s.staze.asfalt_pct}%`,      color: "dark"  },
    { label: "Popločana", value: s.staze.popločana_m, display: `${fmtM(s.staze.popločana_m)} · ${s.staze.popločana_pct}%`, color: "stone" },
  ]);

  bars("bars-oprema", [
    { label: "Ulična svetiljka", value: s.counts.osvetljenje, color: "sun" },
    { label: "Klupa",            value: s.counts.klupe,       color: "earth" },
    { label: "Kanta",            value: s.counts.kante,       color: "dark" },
    { label: "Letnjikovac",      value: s.counts.letnjikovci, color: "green" },
    { label: "Sport. sadržaj",   value: s.counts.sport,       color: "water" },
  ]);

  bars("bars-zelena", [
    { label: "Visoka vegetacija", value: s.zelena_linije_m.visoka_vegetacija, display: fmtM(s.zelena_linije_m.visoka_vegetacija), color: "green" },
    { label: "Niska vegetacija",  value: s.zelena_linije_m.niska_vegetacija,  display: fmtM(s.zelena_linije_m.niska_vegetacija),  color: "green" },
  ]);

  bars("bars-gustina", [
    { label: "Svetiljke / km", value: s.density.osvetljenje_per_km, display: s.density.osvetljenje_per_km.toFixed(2), color: "sun" },
    { label: "Klupe / km",     value: s.density.klupe_per_km,       display: s.density.klupe_per_km.toFixed(2),       color: "earth" },
    { label: "Prekidi / km",   value: s.density.prekidi_per_km,     display: s.density.prekidi_per_km.toFixed(2),     color: "warn" },
  ]);

  renderDeoniceCards(s);
}

function renderDeoniceCards(s) {
  const grid = document.getElementById("deonice-grid");
  if (!grid || !s.deonice || !s.by_deonica) return;
  const dl = s.deonice;

  // Iste skale preko svih kartica
  const maxStaza = Math.max(1, ...dl.flatMap(n => {
    const sm = s.by_deonica[n].staze_m;
    return [sm.asfalt, sm.popločana, sm.zemljana];
  }));
  const counters = ["klupe", "osvetljenje", "prekidi", "stepenice", "rampe"];
  const maxCount = Object.fromEntries(counters.map(k =>
    [k, Math.max(1, ...dl.map(n => s.by_deonica[n].counts[k] || 0))]
  ));

  const row = (label, val, max, color, display) => {
    const pct = max > 0 ? Math.max(2, (val / max) * 100) : 0;
    return `<div class="bar-row">
      <div class="label">${label}</div>
      <div class="track"><div class="fill ${color}" style="width:${pct}%"></div></div>
      <div class="value">${display ?? (val || "—")}</div>
    </div>`;
  };
  const mShow = v => v > 0 ? fmtM(v) : "—";

  grid.innerHTML = dl.map(name => {
    const d = s.by_deonica[name];
    const c = d.counts || {};
    return `
      <div class="deonica-card">
        <div class="deonica-card-head">
          <h3>${name}</h3>
          <div class="deonica-card-km">${d.trasa_km > 0 ? d.trasa_km.toFixed(2) + " km" : "—"}</div>
        </div>
        <div class="deonica-card-section">
          <h4>Podloga staza</h4>
          <div class="bars">
            ${row("Asfalt",     d.staze_m.asfalt,    maxStaza, "dark",  mShow(d.staze_m.asfalt))}
            ${row("Popločana",  d.staze_m.popločana, maxStaza, "stone", mShow(d.staze_m.popločana))}
            ${row("Zemljana",   d.staze_m.zemljana,  maxStaza, "earth", mShow(d.staze_m.zemljana))}
          </div>
        </div>
        <div class="deonica-card-section">
          <h4>Oprema i prepreke</h4>
          <div class="bars">
            ${row("Sijalice",  c.osvetljenje || 0, maxCount.osvetljenje, "sun")}
            ${row("Klupe",     c.klupe       || 0, maxCount.klupe,       "earth")}
            ${row("Prekidi",   c.prekidi     || 0, maxCount.prekidi,     "warn")}
            ${row("Stepenice", c.stepenice   || 0, maxCount.stepenice,   "dark")}
            ${row("Rampe",     c.rampe       || 0, maxCount.rampe,       "water")}
          </div>
        </div>
      </div>`;
  }).join("");
}

// ---------- map ----------

const _geoCache = {};
function loadGeoJSON(name) {
  if (!_geoCache[name]) {
    _geoCache[name] = fetch(`${DATA}${name}.geojson`).then(r => r.json());
  }
  return _geoCache[name];
}

function circleMarker(color, radius = 6) {
  return (feature, latlng) => L.circleMarker(latlng, {
    radius,
    fillColor: color,
    color: "#ffffff",
    weight: 1.5,
    opacity: 1,
    fillOpacity: 0.95,
  });
}

function triangleIcon(color) {
  return L.divIcon({
    className: "warn-marker",
    html: `<div class="tri" style="border-bottom: 14px solid ${color};"></div>`,
    iconSize: [16, 14],
    iconAnchor: [8, 12],
  });
}

function popup(feature) {
  const p = feature.properties || {};
  const name = (p.name || "").trim() || "(bez imena)";
  let extra = "";
  if (p.kategorija) extra += `<br><span class="muted">kategorija: ${p.kategorija}</span>`;
  if (p.podloga)    extra += `<br><span class="muted">podloga: ${p.podloga}</span>`;
  if (p.duzina_m)   extra += `<br><span class="muted">dužina: ${Math.round(p.duzina_m)} m</span>`;
  if (p.stanje)     extra += `<br><span class="muted">stanje: ${p.stanje}</span>`;
  if (Array.isArray(p.images) && p.images.length) {
    const imgs = p.images.map(u =>
      `<a href="${DATA}${u}" target="_blank" rel="noopener"><img src="${DATA}${u}" alt="" loading="lazy"></a>`
    ).join("");
    extra += `<div class="popup-images">${imgs}</div>`;
  }
  return `<strong>${name}</strong>${extra}`;
}

function bindPopups(layer) {
  layer.eachLayer(l => {
    if (l.feature) l.bindPopup(popup(l.feature));
  });
  return layer;
}

const SURFACE_STYLE = {
  asfalt:    { color: "#3b4a40", weight: 5, opacity: 0.95 },
  popločana: { color: "#9aa5a2", weight: 5, opacity: 0.95 },
  zemljana:  { color: "#c08a4f", weight: 5, opacity: 0.95, dashArray: "6 6" },
  ostalo:    { color: "#6b776f", weight: 4, opacity: 0.8 },
};

const GREEN_STYLE = {
  visoka_vegetacija: { color: "#2f6b46", weight: 4, opacity: 0.6 },
  niska_vegetacija:  { color: "#7fb88f", weight: 4, opacity: 0.6 },
  ostalo:            { color: "#7fb88f", weight: 3, opacity: 0.5 },
};

const STATE_COLOR = {
  "loše":     "#c0392b",
  "srednje":  "#d8a93a",
  "dobro":    "#4a9367",
  "deponija": "#5b3a1e",
  "ostalo":   "#6b776f",
};

async function loadMap() {
  const map = L.map("map", { scrollWheelZoom: false }).setView([43.32, 21.9], 13);
  map.on("focus", () => map.scrollWheelZoom.enable());
  map.on("blur",  () => map.scrollWheelZoom.disable());

  // CartoDB Voyager — OSM-bazirani tile-ovi, dozvoljava javni embed bez API ključa
  const carto = L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> · © <a href='https://carto.com/attributions'>CARTO</a>",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);
  const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "Tiles © Esri",
    maxZoom: 19,
  });
  const osmHot = L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap · HOT",
    maxZoom: 19,
  });

  // load all layers
  const [
    trasa, staze, prekidi, stepenice, rampe,
    osvetljenje, klupe, kante, letnjikovci, sport, urbanaOstalo,
    zelena, stanja, socijalni, deonice,
  ] = await Promise.all([
    loadGeoJSON("trasa"), loadGeoJSON("staze"), loadGeoJSON("prekidi"),
    loadGeoJSON("stepenice"), loadGeoJSON("rampe"),
    loadGeoJSON("osvetljenje"), loadGeoJSON("klupe"), loadGeoJSON("kante"),
    loadGeoJSON("letnjikovci"), loadGeoJSON("sport"), loadGeoJSON("urbana_ostalo"),
    loadGeoJSON("zelena"), loadGeoJSON("stanja"), loadGeoJSON("socijalni"),
    loadGeoJSON("deonice"),
  ]);

  // styled layers
  const trasaLayer = L.geoJSON(trasa, {
    style: { color: "#e76f1f", weight: 5, opacity: 0.95 },
    onEachFeature: (f, l) => l.bindPopup(`<strong>Glavna trasa koridora</strong><br><span class="muted">od Medoševca do Niške Banje</span>`),
  });

  const stazeLayer = L.geoJSON(staze, {
    style: f => SURFACE_STYLE[f.properties.podloga] || SURFACE_STYLE.ostalo,
    onEachFeature: (f, l) => l.bindPopup(popup(f)),
  });

  const prekidiLayer = bindPopups(L.geoJSON(prekidi, {
    pointToLayer: (f, ll) => L.marker(ll, { icon: triangleIcon("#c0392b") }),
  }));

  const stepeniceLayer = bindPopups(L.geoJSON(stepenice, { pointToLayer: circleMarker("#6b776f", 5) }));
  const rampeLayer     = bindPopups(L.geoJSON(rampe,     { pointToLayer: circleMarker("#4f87a5", 6) }));
  const osvetljLayer   = bindPopups(L.geoJSON(osvetljenje, { pointToLayer: circleMarker("#d8a93a", 4) }));
  const klupeLayer     = bindPopups(L.geoJSON(klupe,     { pointToLayer: circleMarker("#8a5a2b", 5) }));
  const kanteLayer     = bindPopups(L.geoJSON(kante,     { pointToLayer: circleMarker("#3b4a40", 4) }));
  const letnjikovciLayer = bindPopups(L.geoJSON(letnjikovci, { pointToLayer: circleMarker("#2f6b46", 6) }));
  const sportLayer     = bindPopups(L.geoJSON(sport,     { pointToLayer: circleMarker("#4f87a5", 6) }));
  const ostaloLayer    = bindPopups(L.geoJSON(urbanaOstalo, { pointToLayer: circleMarker("#9aa5a2", 4) }));

  const zelenaLayer = L.geoJSON(zelena, {
    style: f => GREEN_STYLE[f.properties.kategorija] || GREEN_STYLE.ostalo,
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 5, fillColor: "#4f87a5", color: "#fff", weight: 1.5, fillOpacity: .9 }),
    onEachFeature: (f, l) => l.bindPopup(popup(f)),
  });

  const stanjaLayer = bindPopups(L.geoJSON(stanja, {
    style: f => ({ color: STATE_COLOR[f.properties.stanje] || "#6b776f", weight: 4, opacity: 0.9 }),
    pointToLayer: (f, ll) => L.circleMarker(ll, {
      radius: 7, fillColor: STATE_COLOR[f.properties.stanje] || "#6b776f",
      color: "#fff", weight: 1.5, fillOpacity: 0.95,
    }),
  }));

  const socijalniLayer = bindPopups(L.geoJSON(socijalni, { pointToLayer: circleMarker("#7d3c98", 7) }));

  const DEONICA_COLORS = ["#2f6b46", "#d8a93a", "#8a5a2b", "#4f87a5"];
  const deoniceLayer = L.geoJSON(deonice, {
    style: (f) => {
      const idx = (deonice.features || []).indexOf(f);
      const col = DEONICA_COLORS[idx % DEONICA_COLORS.length];
      return { color: col, weight: 2, opacity: 0.85, fillColor: col, fillOpacity: 0.10 };
    },
    onEachFeature: (f, l) => {
      l.bindTooltip(f.properties.name, { permanent: true, direction: "center", className: "deonica-label" });
      l.bindPopup(`<strong>Deonica:</strong> ${f.properties.name}`);
    },
  });

  // add defaults
  trasaLayer.addTo(map);
  stazeLayer.addTo(map);
  prekidiLayer.addTo(map);
  stepeniceLayer.addTo(map);
  rampeLayer.addTo(map);

  // fit bounds to route
  try {
    map.fitBounds(trasaLayer.getBounds(), { padding: [20, 20] });
  } catch (e) { /* noop */ }

  // layer control
  const overlays = {
    "Granice deonica": deoniceLayer,
    "Glavna trasa": trasaLayer,
    "Staze (po tipu podloge)": stazeLayer,
    "Prekidi u kretanju": prekidiLayer,
    "Stepenice": stepeniceLayer,
    "Rampe": rampeLayer,
    "Ulično osvetljenje": osvetljLayer,
    "Klupe": klupeLayer,
    "Kante za smeće": kanteLayer,
    "Letnjikovci": letnjikovciLayer,
    "Sportski sadržaji": sportLayer,
    "Stanja očuvanosti": stanjaLayer,
    "Urbani džepovi": socijalniLayer,
    "Zelena infrastruktura": zelenaLayer,
    "Ostala urbana oprema": ostaloLayer,
  };
  const layersCtrl = L.control.layers(
    { "Mapa": carto, "Mapa (HOT)": osmHot, "Satelit": sat },
    overlays,
    { collapsed: window.innerWidth < 900, position: "topright" }
  ).addTo(map);

  // Auto-collapse / expand on viewport resize (desktop ↔ mobile)
  let lastCollapsed = window.innerWidth < 900;
  window.addEventListener("resize", () => {
    const shouldCollapse = window.innerWidth < 900;
    if (shouldCollapse !== lastCollapsed) {
      lastCollapsed = shouldCollapse;
      if (shouldCollapse) layersCtrl.collapse();
      else                layersCtrl.expand();
    }
  });

  // Touch UX: tap na mapu zatvara otvoreni layer panel (Leaflet to ne radi sam).
  // Marker click ne okida map.click (Leaflet stop-uje propagaciju), tako da
  // toggle slojeva ne ometa interakciju sa tačkama na mapi.
  map.on("click", () => {
    if (window.innerWidth < 900) layersCtrl.collapse();
  });
}

// ---------- gallery + lightbox ----------

const GALLERY_CATEGORIES = [
  { id: "prekidi",   label: "Prekidi",           layers: ["prekidi"] },
  { id: "stepenice", label: "Stepenice i rampe", layers: ["stepenice", "rampe", "staze"] },
  { id: "urbana",    label: "Urbana oprema",     layers: ["osvetljenje", "klupe", "kante", "letnjikovci", "sport", "urbana_ostalo"] },
  { id: "stanja",    label: "Stanja",            layers: ["stanja"] },
  { id: "zelena",    label: "Vegetacija",        layers: ["zelena"] },
  { id: "socijalni", label: "Urbani džepovi",    layers: ["socijalni"] },
];

async function loadGallery() {
  const layerToCat = {};
  const allLayers = new Set();
  for (const cat of GALLERY_CATEGORIES) {
    for (const ly of cat.layers) {
      allLayers.add(ly);
      layerToCat[ly] = cat;
    }
  }

  const fetched = await Promise.all([...allLayers].map(ly => loadGeoJSON(ly).then(g => [ly, g])));
  const items = [];
  for (const [ly, gj] of fetched) {
    for (const f of (gj.features || [])) {
      const imgs = f.properties && f.properties.images;
      if (!Array.isArray(imgs) || !imgs.length) continue;
      const cat = layerToCat[ly];
      const name = (f.properties.name || "").trim() || "(bez imena)";
      const deonica = f.properties.deonica || "";
      for (const u of imgs) {
        items.push({
          url: DATA + u,
          name, deonica,
          categoryId: cat.id,
          categoryLabel: cat.label,
        });
      }
    }
  }

  const filtersEl = document.getElementById("gallery-filters");
  const gridEl = document.getElementById("gallery-grid");
  if (!filtersEl || !gridEl) return;

  const chip = (id, label, n, active) =>
    `<button type="button" class="chip${active ? " active" : ""}" data-cat="${id}">${label} <span class="chip-count">${n}</span></button>`;
  filtersEl.innerHTML = chip("all", "Sve", items.length, true) +
    GALLERY_CATEGORIES
      .map(c => ({ c, n: items.filter(i => i.categoryId === c.id).length }))
      .filter(x => x.n > 0)
      .map(x => chip(x.c.id, x.c.label, x.n, false))
      .join("");

  gridEl.innerHTML = items.map((it, i) => `
    <a href="${it.url}" class="gallery-item" data-cat="${it.categoryId}" data-idx="${i}">
      <img src="${it.url}" alt="${it.name}" loading="lazy">
      <div class="gallery-caption">
        <div class="gallery-name">${it.name}</div>
        <div class="gallery-meta">${it.categoryLabel}${it.deonica ? " · " + it.deonica : ""}</div>
      </div>
    </a>`).join("");

  filtersEl.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    filtersEl.querySelectorAll(".chip").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const cat = btn.dataset.cat;
    gridEl.querySelectorAll(".gallery-item").forEach(el => {
      el.style.display = (cat === "all" || el.dataset.cat === cat) ? "" : "none";
    });
  });

  setupLightbox(items, gridEl);
}

function setupLightbox(items, gridEl) {
  const lb = document.getElementById("lightbox");
  const img = document.getElementById("lightbox-img");
  const cap = document.getElementById("lightbox-caption");
  if (!lb || !img || !cap) return;

  let visible = items.slice();
  let idx = 0;

  const refreshVisible = () => {
    visible = [...gridEl.querySelectorAll(".gallery-item")]
      .filter(el => el.style.display !== "none")
      .map(el => items[+el.dataset.idx]);
  };

  const show = (i) => {
    if (!visible.length) return;
    idx = (i + visible.length) % visible.length;
    const it = visible[idx];
    img.src = it.url;
    cap.innerHTML = `<div class="lb-name">${it.name}</div>
      <div class="lb-meta">${it.categoryLabel}${it.deonica ? " · " + it.deonica : ""} · ${idx + 1} / ${visible.length}</div>`;
  };
  const open = (i) => { lb.hidden = false; document.body.style.overflow = "hidden"; show(i); };
  const close = () => { lb.hidden = true; document.body.style.overflow = ""; img.src = ""; };

  gridEl.addEventListener("click", (e) => {
    const a = e.target.closest(".gallery-item");
    if (!a) return;
    e.preventDefault();
    refreshVisible();
    const clickedUrl = a.getAttribute("href");
    const start = visible.findIndex(it => it.url === clickedUrl);
    open(Math.max(0, start));
  });

  lb.querySelector(".lightbox-close").addEventListener("click", close);
  lb.querySelector(".lightbox-prev").addEventListener("click", () => show(idx - 1));
  lb.querySelector(".lightbox-next").addEventListener("click", () => show(idx + 1));
  lb.addEventListener("click", (e) => { if (e.target === lb) close(); });
  document.addEventListener("keydown", (e) => {
    if (lb.hidden) return;
    if (e.key === "Escape") close();
    if (e.key === "ArrowLeft") show(idx - 1);
    if (e.key === "ArrowRight") show(idx + 1);
  });
}

// ---------- boot ----------

(async function () {
  try {
    await Promise.all([loadStats(), loadMap(), loadGallery()]);
  } catch (e) {
    console.error(e);
    const note = document.querySelector(".legend-note");
    if (note) {
      note.innerHTML = `<strong>Greška pri učitavanju podataka.</strong> Ako otvaraš stranicu direktno iz fajl sistema (file://), pokreni lokalni server: <code>python3 -m http.server</code> i otvori <code>http://localhost:8000</code>.`;
    }
  }
})();
