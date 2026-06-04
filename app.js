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
}

// ---------- map ----------

async function loadGeoJSON(name) {
  const r = await fetch(`${DATA}${name}.geojson`);
  return r.json();
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

  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap doprinosioci",
    maxZoom: 19,
  }).addTo(map);
  const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: "Tiles © Esri",
    maxZoom: 19,
  });

  // load all layers
  const [
    trasa, staze, prekidi, stepenice, rampe,
    osvetljenje, klupe, kante, letnjikovci, sport, urbanaOstalo,
    zelena, stanja, socijalni,
  ] = await Promise.all([
    loadGeoJSON("trasa"), loadGeoJSON("staze"), loadGeoJSON("prekidi"),
    loadGeoJSON("stepenice"), loadGeoJSON("rampe"),
    loadGeoJSON("osvetljenje"), loadGeoJSON("klupe"), loadGeoJSON("kante"),
    loadGeoJSON("letnjikovci"), loadGeoJSON("sport"), loadGeoJSON("urbana_ostalo"),
    loadGeoJSON("zelena"), loadGeoJSON("stanja"), loadGeoJSON("socijalni"),
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
  L.control.layers(
    { "Mapa (OSM)": osm, "Satelit": sat },
    overlays,
    { collapsed: false, position: "topright" }
  ).addTo(map);
}

// ---------- boot ----------

(async function () {
  try {
    await Promise.all([loadStats(), loadMap()]);
  } catch (e) {
    console.error(e);
    const note = document.querySelector(".legend-note");
    if (note) {
      note.innerHTML = `<strong>Greška pri učitavanju podataka.</strong> Ako otvaraš stranicu direktno iz fajl sistema (file://), pokreni lokalni server: <code>python3 -m http.server</code> i otvori <code>http://localhost:8000</code>.`;
    }
  }
})();
