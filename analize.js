/* Analize podataka — sadržaj stranice i tabela pokazatelja sekcije 9.
 *
 * Sadržaj se gradi iz same stranice: svaka numerisana sekcija
 * (.analiza-grupa sa id-jem) i njene kartice. Nova sekcija ili analiza se
 * dodaje samo kao HTML kartica, a sadržaj je prati bez posebnog održavanja.
 *
 * Tabela čita data/indikatori.json (indikatori.py): po jedan broj za svaku od
 * tri staze, za svaki pokazatelj. Opisi mera se grade iz parametara u fajlu,
 * da tekst ne bi zaostao kad se prag promeni.
 */
"use strict";

function buildSadrzaj() {
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const items = [...document.querySelectorAll(".analiza-grupa[id]")].map(sec => {
    const h2 = sec.querySelector("h2").textContent.trim();
    const m = h2.match(/^(\d+)\.\s*(.*)$/);
    const [num, naziv] = m ? [m[1] + ".", m[2]] : ["", h2];

    const kids = [...sec.querySelectorAll(".analiza-card")].map(card => {
      const n = card.querySelector(".analiza-num").textContent.trim();
      const t = esc(card.querySelector("h3").textContent.trim());
      const href = card.getAttribute("href");
      // broj i naslov su dve kolone, da se dug naslov prelama poravnat sa sobom
      return href
        ? `<li><a href="${href}"><span class="sd-num">${n}</span><span class="sd-t">${t}<span class="sd-go" aria-hidden="true">→</span></span></a></li>`
        : `<li class="sd-plan"><span class="sd-num">${n}</span><span class="sd-t">${t}<span class="sd-status">u pripremi</span></span></li>`;
    });
    const tabela = sec.querySelector(".pokazatelji[id]");
    if (tabela) {
      const t = esc(tabela.querySelector("h3").textContent.trim());
      kids.push(`<li class="sd-extra"><a href="#${tabela.id}"><span class="sd-num"></span><span class="sd-t">${t}</span></a></li>`);
    }
    return `<li><a href="#${sec.id}"><span class="sd-num">${num}</span><span class="sd-t">${esc(naziv)}</span></a>
      ${kids.length ? `<ol>${kids.join("")}</ol>` : ""}</li>`;
  });
  if (!items.length) return;
  document.getElementById("sadrzaj-lista").innerHTML = items.join("");
  document.getElementById("sadrzaj").hidden = false;
}

buildSadrzaj();

const STAZA_SHORT = {
  bici: "Biciklistička",
  pesacki_gornji: "Gornji bedem",
  pesacki_donji: "Donji bedem",
};
// na telefonu tri kolone brojeva moraju da stanu bez skrolovanja
const STAZA_MOB = { bici: "Bici", pesacki_gornji: "Gornji", pesacki_donji: "Donji" };

const ANALIZA_URL = {
  "9.1": "9.1.shade_and_tree_canopy_coverage.html",
  "9.2": "9.2.noise_and_air_quality_exposure.html",
};

// naziv, izvorni naziv iz okvira, opis mere
const POKAZATELJ = {
  kontinuitet_senke: p => ["Kontinuitet senke", "Shade continuity",
    `% dužine u neprekidnoj senci od bar ${p.kontinuitet_min_m}\u00a0m, 21. jun, ${p.sunce_sati[0]}-${p.sunce_sati[1]}\u00a0h`],
  krosnje: p => ["Pokrivenost krošnjama", "Tree canopy",
    `% dužine uz krošnju višu od ${p.krosnje_min_h_m}\u00a0m`],
  sunce: p => ["Izloženost suncu", "Exposure to sun",
    `% dužine na suncu, 21. jun, ${p.sunce_sati[0]}-${p.sunce_sati[1]}\u00a0h`],
  pogled_na_reku: p => ["Pogled na reku", "River views",
    "% dužine sa koje se vidi Nišava"],
  buka: p => ["Izloženost buci", "Noise exposure",
    `% dužine sa indeksom buke ${p.buka_min_indeks} i više`],
  termalni_komfor: () => ["Termalni komfor", "Thermal comfort", "u pripremi"],
};

function fmt(v) { return v.toFixed(1) + " %"; }

function render(d) {
  const tips = d.staze.map(s => s.tip);
  const head = `<thead><tr>
      <th class="tl">Pokazatelj</th><th class="tl pk-col-mera">Mera</th>
      ${tips.map(t => `<th><span class="pk-long">${STAZA_SHORT[t] || t}</span><span class="pk-short">${STAZA_MOB[t] || t}</span></th>`).join("")}
      <th class="pk-col-izvor">Analiza</th>
    </tr></thead>`;

  const body = d.redovi.map(r => {
    const [naziv, en, mera] = POKAZATELJ[r.key](d.parametri);
    const url = ANALIZA_URL[r.izvor];
    const izvor = url ? `<a href="${url}">${r.izvor}</a>` : `<span class="muted">${r.izvor}</span>`;
    // opis mere se na telefonu prikazuje ispod naziva, umesto u svojoj koloni
    const opis = `<td class="pk-naziv">${naziv}<span class="pk-en">${en}</span><span class="pk-mera-mob">${mera}</span></td>`;

    if (!r.vrednosti) {
      return `<tr class="pk-plan">${opis}<td class="pk-col-mera muted">${mera}</td>
        <td colspan="${tips.length}"></td><td class="num pk-col-izvor">${izvor}</td></tr>`;
    }
    const vals = tips.map(t => r.vrednosti[t]);
    const best = r.bolje === "manje" ? Math.min(...vals) : Math.max(...vals);
    return `<tr>${opis}<td class="pk-mera pk-col-mera">${mera}</td>
      ${vals.map(v => `<td class="num${v === best ? " pk-best" : ""}">${fmt(v)}</td>`).join("")}
      <td class="num pk-col-izvor">${izvor}</td></tr>`;
  }).join("");

  document.getElementById("pokazatelji").insertAdjacentHTML("beforeend",
    head + `<tbody>${body}</tbody>`);

  document.getElementById("pokazatelji-nota").innerHTML =
    "Podebljano je najbolja od tri staze. Za sunce i buku manje je bolje. " +
    "Buka je relativni indeks, ne decibeli. Pogled sa gornjeg bedema je verovatno " +
    "i veći od prikazanog, jer izračun ne zna da je bedem uzdignut. " +
    `Metod je u <a href="dnevnik.html">tehničkom dnevniku</a>.`;
}

fetch("data/indikatori.json")
  .then(r => r.json())
  .then(render)
  .catch(e => {
    console.error("Ne mogu da učitam indikatori.json:", e);
    document.querySelector(".pokazatelji").hidden = true;
  });
