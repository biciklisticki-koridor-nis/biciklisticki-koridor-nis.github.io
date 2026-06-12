/* Nišavski biciklistički koridor — main script.
 * Loads stats + GeoJSON layers, renders KPI tiles, bar charts, and Leaflet map.
 */

const DATA = "data/";

const DEONICA_COLORS = ["#2f6b46", "#d8a93a", "#8a5a2b", "#4f87a5"];

const LC_COLORS = {
  tree_cover:  "#2f6b46",
  shrubland:   "#7fb88f",
  grassland:   "#a4c054",
  cropland:    "#e29b3e",
  built_up:    "#9aa5a2",
  bare:        "#d3d8d3",
  water:       "#4f87a5",
  wetland:     "#7da9ad",
  snow_ice:    "#eef0f3",
  mangroves:   "#3a9d6b",
  moss_lichen: "#b9a76b",
};
const LC_LIGHT_TEXT = new Set(["bare", "snow_ice", "shrubland"]);

const PREKID_TIP_LABELS = {
  dalekovod:             "Dalekovod",
  privatno_zemljiste:    "Privatno zemljište",
  most_prelaz:           "Most / prelaz",
  bedem:                 "Bedem",
  pritoka:               "Pritoka / vodotok",
  nedostatak_rampe:      "Nedostatak rampe",
  nedostatak_stepenista: "Nedostatak stepeništa",
  objekat:               "Objekat / ograda",
  promena_puta:          "Promena karaktera puta",
  ostalo:                "Neoznačeno",
};

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

  renderTipoviPrekida(s);
  renderDeoniceCards(s);
  renderShade(s);
  renderLandcover(s);
}

function renderShade(s) {
  const sh = s.shade;
  if (!sh) return;
  renderShadeStrip("shade-strip-total", sh.strip, s.trasa_km);
  renderShadeAxis("shade-strip-axis", s.trasa_km);
  renderShadeStats(sh.totals);
  renderShadeByDeonica(s);
}

function renderShadeStrip(elId, strip, totalKm) {
  const el = document.getElementById(elId);
  if (!el || !Array.isArray(strip)) return;
  const totalM = totalKm * 1000;
  el.innerHTML = strip.map(iv => {
    const w = totalM > 0 ? (iv.length_m / totalM) * 100 : 0;
    const cls = iv.shade ? "shade" : "sun";
    const dn = iv.deonica ? `${iv.deonica}: ` : "";
    const title = `${dn}km ${iv.km_start.toFixed(2)}–${iv.km_end.toFixed(2)} (${iv.length_m} m) — ${iv.shade ? "u senci drveća" : "na suncu"}`;
    return `<div class="strip-seg ${cls}" style="width:${w}%" title="${title}"></div>`;
  }).join("");
}

function renderShadeAxis(elId, totalKm) {
  const el = document.getElementById(elId);
  if (!el) return;
  const step = totalKm > 10 ? 2 : 1;
  const ticks = [];
  for (let k = 0; k <= totalKm + 0.01; k += step) ticks.push(Math.min(k, totalKm));
  el.innerHTML = ticks.map(k => `<span>${k.toFixed(0)} km</span>`).join("");
}

function renderShadeStats(totals) {
  const el = document.getElementById("shade-stats-total");
  if (!el || !totals || !totals.shade) return;
  const sh = totals.shade;
  const gr = totals.green || { pct: 0 };
  const openGreen = Math.max(0, Math.round((gr.pct - sh.pct) * 10) / 10);
  const tiles = [
    { val: sh.pct,           unit: "%",  label: "U senci drveća",                  sub: "jedino drveće daje stalnu senku" },
    { val: openGreen,        unit: "%",  label: "Otvoreno zelenilo",               sub: "trava, polja, obradivo — zeleno, ali bez senke" },
    { val: sh.longest_m,     unit: " m", label: "Najduži deo u senci",             sub: "neprekinut interval drveća" },
    { val: sh.longest_gap_m, unit: " m", label: "Najduža rupa u senci",            sub: "kritična zona izloženosti suncu", warn: sh.longest_gap_m >= 1000 },
  ];
  el.innerHTML = tiles.map(t => `
    <div class="shade-stat">
      <div class="shade-stat-value ${t.warn ? "warn" : ""}">${t.val}<span class="unit">${t.unit}</span></div>
      <div class="shade-stat-label">${t.label}</div>
      <div class="shade-stat-sub">${t.sub}</div>
    </div>
  `).join("");
}

function renderShadeByDeonica(s) {
  const el = document.getElementById("shade-by-deonica");
  if (!el) return;
  const sh = s.shade;
  el.innerHTML = (s.deonice || []).map(name => {
    const m = sh.by_deonica[name];
    const trasaKm = (s.by_deonica[name] && s.by_deonica[name].trasa_km) || 0;
    if (!m || trasaKm <= 0) return "";
    const dnStrip = sh.strip.filter(iv => iv.deonica === name);
    const dnLenM = dnStrip.reduce((acc, iv) => acc + iv.length_m, 0);
    const segs = dnStrip.map(iv => {
      const w = dnLenM > 0 ? (iv.length_m / dnLenM) * 100 : 0;
      return `<div class="strip-seg ${iv.shade ? "shade" : "sun"}" style="width:${w}%" title="km ${iv.km_start.toFixed(2)}–${iv.km_end.toFixed(2)} (${iv.length_m} m) ${iv.shade ? "— senka" : "— sunce"}"></div>`;
    }).join("");
    const lowShade = m.shade.pct < 10;
    const openGreen = Math.max(0, Math.round((m.green.pct - m.shade.pct) * 10) / 10);
    return `
      <div class="shade-deonica-card">
        <h4>
          <span>${name}</span>
          <span class="pct ${lowShade ? "low" : ""}">${m.shade.pct}%</span>
        </h4>
        <div class="mini-strip">${segs}</div>
        <div class="shade-deonica-row"><span class="label">🌳 Drveće (daje senku)</span><span class="value">${m.shade.pct}%</span></div>
        <div class="shade-deonica-row"><span class="label">🌾 Otvoreno zelenilo</span><span class="value">${openGreen}%</span></div>
        <div class="shade-deonica-row"><span class="label">Najduži deo u senci</span><span class="value">${m.shade.longest_m} m</span></div>
        <div class="shade-deonica-row"><span class="label">Najduža rupa bez senke</span><span class="value">${m.shade.longest_gap_m} m</span></div>
        <div class="shade-deonica-row"><span class="label">Prelaza senka ↔ sunce</span><span class="value">${m.shade.transitions}</span></div>
      </div>`;
  }).join("");
}

function lcStackedSegments(dist, order, labels, minPctForLabel) {
  return order
    .filter(k => (dist[k] || 0) > 0)
    .map(k => {
      const pct = dist[k];
      const txt = pct >= minPctForLabel ? `${Math.round(pct)}%` : "";
      const cls = LC_LIGHT_TEXT.has(k) ? "ink-dark" : "";
      const lab = labels[k] || k;
      const title = `${lab}: ${pct.toFixed(1)}%`;
      return `<div class="${cls}" style="background:${LC_COLORS[k] || "#999"}; width:${pct}%" title="${title}">${txt}</div>`;
    }).join("");
}

function renderLandcover(s) {
  const lc = s.landcover;
  if (!lc) return;
  const labels = lc.labels || {};
  const totals = lc.totals_pct || {};
  const seen = new Set(Object.keys(totals));
  for (const dn in (lc.by_deonica_pct || {})) {
    Object.keys(lc.by_deonica_pct[dn]).forEach(k => seen.add(k));
  }
  const order = [...seen].sort((a, b) => (totals[b] || 0) - (totals[a] || 0));

  const leg = document.getElementById("lc-legend");
  if (leg) {
    leg.innerHTML = order.map(k => `
      <span class="lc-legend-item">
        <span class="lc-legend-swatch" style="background:${LC_COLORS[k] || "#999"}"></span>
        ${labels[k] || k}
      </span>`).join("");
  }

  const totalsBar = document.getElementById("lc-totals-bar");
  if (totalsBar) totalsBar.innerHTML = lcStackedSegments(totals, order, labels, 4);
  const totalsKm = document.getElementById("lc-totals-km");
  if (totalsKm) totalsKm.textContent = `${s.trasa_km.toFixed(2)} km`;

  const byEl = document.getElementById("lc-by-deonica");
  if (byEl) {
    byEl.innerHTML = (s.deonice || []).map(name => {
      const dist = (lc.by_deonica_pct || {})[name];
      const km = (s.by_deonica[name] && s.by_deonica[name].trasa_km) || 0;
      if (!dist || km <= 0) return "";
      return `
        <div class="lc-bar-row">
          <div class="label">${name}</div>
          <div class="lc-bar">${lcStackedSegments(dist, order, labels, 6)}</div>
          <div class="km">${km.toFixed(2)} km</div>
        </div>`;
    }).join("");
  }
}

function renderTipoviPrekida(s) {
  const tipovi = s.prekidi_po_tipu || {};
  const entries = Object.entries(tipovi)
    .filter(([k]) => k !== "ostalo")
    .sort((a, b) => b[1] - a[1]);
  if (tipovi.ostalo) entries.push(["ostalo", tipovi.ostalo]);
  const total = Object.values(tipovi).reduce((a, b) => a + b, 0);
  bars("bars-prekidi-tipovi",
    entries.map(([k, v]) => ({
      label: PREKID_TIP_LABELS[k] || k,
      value: v,
      display: total > 0 ? `${v} · ${Math.round(100 * v / total)}%` : String(v),
      color: k === "ostalo" ? "stone" : "warn",
    })),
  );
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

// ---------- visinski profil (SVG handroll) ----------

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(name, attrs = {}) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

async function loadElevation() {
  let elev;
  try {
    const r = await fetch(DATA + "elevation.json");
    if (!r.ok) return;
    elev = await r.json();
  } catch (e) { return; }
  if (!elev || !Array.isArray(elev.profile) || elev.profile.length < 2) return;
  renderProfileStats(elev);
  renderProfileSvg(elev);
  renderProfileDeonice(elev);
}

function renderProfileStats(elev) {
  const el = document.getElementById("profile-stats");
  const t = elev.totals || {};
  if (!el) return;
  const tiles = [
    { val: t.ascent_m,         unit: "m", label: "Ukupan uspon",  sub: "kumulativan duž trase", arrow: "up"   },
    { val: t.descent_m,        unit: "m", label: "Ukupan pad",    sub: "kumulativan duž trase", arrow: "down" },
    { val: t.raspon_m,         unit: "m", label: "Raspon visina", sub: `${t.min_m}–${t.max_m} m n.v.` },
    { val: t.max_gradient_pct, unit: "%", label: "Maks. nagib",   sub: "najveći lokalni nagib"   },
  ];
  el.innerHTML = tiles.map(s => `
    <div class="profile-stat">
      <div class="profile-stat-value">
        ${s.arrow ? `<span class="arrow ${s.arrow}">${s.arrow === "up" ? "↑" : "↓"}</span>` : ""}${s.val}<span class="unit">${s.unit}</span>
      </div>
      <div class="profile-stat-label">${s.label}</div>
      <div class="profile-stat-sub">${s.sub}</div>
    </div>
  `).join("");
}

function renderProfileSvg(elev) {
  const svg = document.getElementById("profile-svg");
  if (!svg) return;
  svg.innerHTML = "";

  const profile = elev.profile;
  const totals = elev.totals;
  const W = 1000, H = 280;
  const M = { top: 28, right: 24, bottom: 24, left: 42 };
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;

  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const totalKm = profile[profile.length - 1].km || 1;
  const minE = Math.floor((totals.min_m - 1) / 5) * 5;
  const maxE = Math.ceil((totals.max_m + 1) / 5) * 5;
  const xOf = km => M.left + (km / totalKm) * innerW;
  const yOf = e  => M.top + (1 - (e - minE) / (maxE - minE)) * innerH;

  // 1) Background bands po deonicama
  const bandRanges = [];
  let cur = null;
  for (const p of profile) {
    if (!p.deonica) { cur = null; continue; }
    if (!cur || cur.name !== p.deonica) {
      cur = { name: p.deonica, kmStart: p.km, kmEnd: p.km };
      bandRanges.push(cur);
    } else {
      cur.kmEnd = p.km;
    }
  }
  bandRanges.forEach((b, i) => {
    const color = DEONICA_COLORS[i % DEONICA_COLORS.length];
    const x = xOf(b.kmStart), w = Math.max(2, xOf(b.kmEnd) - x);
    svg.appendChild(svgEl("rect", {
      class: "band", x, y: M.top, width: w, height: innerH, fill: color,
    }));
    // band label iznad chart area da ne preklapa Y-tick brojeve
    svg.appendChild(svgEl("text", {
      class: "band-label", x: x + w / 2, y: M.top - 8, "text-anchor": "middle",
    })).textContent = b.name;
  });

  // 2) Horizontalne grid linije + Y axis tick-ovi (5m intervali)
  for (let e = minE; e <= maxE; e += 5) {
    const y = yOf(e);
    svg.appendChild(svgEl("line", {
      class: "grid-line", x1: M.left, y1: y, x2: W - M.right, y2: y,
    }));
    svg.appendChild(svgEl("text", {
      class: "axis-tick", x: M.left - 8, y: y + 3, "text-anchor": "end",
    })).textContent = e;
  }

  // 3) Vertikalne tick-ovi (2km koraci) — poslednji tick nosi i jedinicu "km"
  const xStep = totalKm > 8 ? 2 : 1;
  const lastKm = Math.floor(totalKm / xStep) * xStep;
  for (let km = 0; km <= totalKm + 0.001; km += xStep) {
    const isLast = km === lastKm;
    const x = xOf(Math.min(km, totalKm));
    svg.appendChild(svgEl("line", {
      class: "grid-line", x1: x, y1: M.top + innerH, x2: x, y2: M.top + innerH + 4,
    }));
    svg.appendChild(svgEl("text", {
      class: "axis-tick", x, y: M.top + innerH + 16, "text-anchor": "middle",
    })).textContent = isLast ? `${km} km` : `${km}`;
  }

  // 4) Area + line path (koristi elev_smooth)
  const valid = profile.filter(p => p.elev_smooth != null);
  if (valid.length >= 2) {
    let areaD = `M ${xOf(valid[0].km)} ${M.top + innerH}`;
    let lineD = "";
    valid.forEach((p, i) => {
      const x = xOf(p.km), y = yOf(p.elev_smooth);
      areaD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
      lineD += (i === 0 ? "M " : " L ") + `${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    areaD += ` L ${xOf(valid[valid.length - 1].km)} ${M.top + innerH} Z`;
    svg.appendChild(svgEl("path", { class: "area", d: areaD }));
    svg.appendChild(svgEl("path", { class: "line", d: lineD }));
  }

  // 5) Hover line + dot + capture rect
  const hoverLine = svgEl("line", {
    class: "hover-line", x1: 0, y1: M.top, x2: 0, y2: M.top + innerH,
  });
  const hoverDot = svgEl("circle", { class: "hover-dot", cx: 0, cy: 0 });
  svg.appendChild(hoverLine);
  svg.appendChild(hoverDot);

  const capture = svgEl("rect", {
    x: M.left, y: M.top, width: innerW, height: innerH,
    fill: "transparent",
  });
  svg.appendChild(capture);

  const wrap = document.getElementById("profile-chart-wrap");
  const tt = document.getElementById("profile-tooltip");
  const ttElev = tt.querySelector(".tt-elev");
  const ttMeta = tt.querySelector(".tt-meta");

  function onMove(evt) {
    const rect = svg.getBoundingClientRect();
    // SVG je preserveAspectRatio="xMidYMid meet"; mapiraj client→viewbox koristeći stvarni scale
    const scale = rect.width / W;
    const localX = (evt.clientX - rect.left) / scale;
    if (localX < M.left || localX > W - M.right) { hideTooltip(); return; }
    const km = ((localX - M.left) / innerW) * totalKm;
    // Find nearest sample
    let lo = 0, hi = profile.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (profile[mid].km < km) lo = mid; else hi = mid;
    }
    const p = (Math.abs(profile[lo].km - km) < Math.abs(profile[hi].km - km)) ? profile[lo] : profile[hi];
    if (p.elev_smooth == null) { hideTooltip(); return; }
    const cx = xOf(p.km), cy = yOf(p.elev_smooth);
    hoverLine.setAttribute("x1", cx); hoverLine.setAttribute("x2", cx);
    hoverLine.style.opacity = "1";
    hoverDot.setAttribute("cx", cx); hoverDot.setAttribute("cy", cy);
    hoverDot.style.opacity = "1";
    ttElev.textContent = `${p.elev_smooth} m n.v.`;
    ttMeta.textContent = `${p.km.toFixed(2)} km · ${p.deonica || "—"}`;
    const wrapRect = wrap.getBoundingClientRect();
    tt.style.left = `${(evt.clientX - wrapRect.left)}px`;
    tt.style.top  = `${(cy * scale)}px`;
    tt.hidden = false;
    tt.style.opacity = "1";
  }
  function hideTooltip() {
    hoverLine.style.opacity = "0";
    hoverDot.style.opacity = "0";
    tt.style.opacity = "0";
  }
  capture.addEventListener("mousemove", onMove);
  capture.addEventListener("mouseleave", hideTooltip);
  capture.addEventListener("touchmove", e => {
    if (e.touches[0]) onMove(e.touches[0]);
  }, { passive: true });
  capture.addEventListener("touchend", hideTooltip);
}

function renderProfileDeonice(elev) {
  const el = document.getElementById("profile-deonice");
  if (!el || !elev.by_deonica) return;
  const entries = Object.entries(elev.by_deonica);
  el.innerHTML = entries.map(([name, d], i) => {
    const color = DEONICA_COLORS[i % DEONICA_COLORS.length];
    return `
      <div class="profile-deonica-card" style="border-top: 3px solid ${color};">
        <h4>${name}</h4>
        <div class="profile-deonica-row"><span class="label">Uspon</span><span class="value up">↑ ${d.ascent_m} m</span></div>
        <div class="profile-deonica-row"><span class="label">Pad</span><span class="value down">↓ ${d.descent_m} m</span></div>
        <div class="profile-deonica-row"><span class="label">Raspon</span><span class="value">${d.raspon_m} m (${d.min_m}–${d.max_m})</span></div>
        <div class="profile-deonica-row"><span class="label">Maks. nagib</span><span class="value">${d.max_gradient_pct}%</span></div>
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

  // shadeMap link — daje stvarne senke iz DSM-a za trenutnu poziciju i bilo koji datum/sat
  const ShadeMapCtrl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const btn = L.DomUtil.create("a", "leaflet-bar leaflet-control shademap-btn");
      btn.href = "#";
      btn.title = "Otvori shadeMap — interaktivno proveri senku za trenutnu poziciju, datum i čas";
      btn.setAttribute("role", "button");
      btn.setAttribute("aria-label", "Otvori shadeMap u novom tabu");
      btn.textContent = "☀";
      L.DomEvent.on(btn, "click", L.DomEvent.preventDefault);
      L.DomEvent.on(btn, "click", () => {
        const c = map.getCenter();
        const z = Math.round(map.getZoom());
        const t = Date.now();
        const url = `https://shademap.app/@${c.lat.toFixed(5)},${c.lng.toFixed(5)},${z}z,${t}t,0b,0p,1m`;
        window.open(url, "_blank", "noopener");
      });
      L.DomEvent.disableClickPropagation(btn);
      return btn;
    },
  });
  new ShadeMapCtrl().addTo(map);

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
    await Promise.all([loadStats(), loadMap(), loadGallery(), loadElevation()]);
  } catch (e) {
    console.error(e);
    const note = document.querySelector(".legend-note");
    if (note) {
      note.innerHTML = `<strong>Greška pri učitavanju podataka.</strong> Ako otvaraš stranicu direktno iz fajl sistema (file://), pokreni lokalni server: <code>python3 -m http.server</code> i otvori <code>http://localhost:8000</code>.`;
    }
  }
})();
