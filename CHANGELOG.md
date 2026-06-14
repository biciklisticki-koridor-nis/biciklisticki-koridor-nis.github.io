# Changelog

Sve značajne izmene sajta i pipeline-a su u ovoj listi, sa najnovijim na vrhu.
Format prati [Keep a Changelog](https://keepachangelog.com/sr/1.1.0/).

## [Neobjavljeno]

## [2026-06-14]

### Uklonjeno
- **Kartice „Ukupan uspon" i „Ukupan pad"** iz visinskog profila — ne
  odgovaraju ni na jedno pitanje koje obični biciklista postavlja o
  ravnom urbanom keju (22.8 m raspona na 14.67 km, max 3.7 % nagib).
  Metrika je centralna u Strava / Garmin svetu za brdovite treninge;
  za našu publiku je informaciona buka. Ostaju: <strong>Raspon visina</strong>
  i <strong>Maks. nagib</strong> u totals i per-deonica karticama; profil grafik.
- `compute_elevation_stats()` u `convert.py` više ne vraća `ascent_m` /
  `descent_m`; histerezisni deadband filter (`asc_desc_grad()`) obrisan.
- `.info-mark` custom tooltip implementacija u `style.css` (više nema
  šta da objašnjava). `ELEV_SCHEMA` 6 → 7.

### Eksperimentisali (ne objavljeno)
- **shadeMap pre-compute pipeline** — pokušaj zamene tree-cover proksija sa
  stvarnim ray-tracing izračunom senke. Puppeteer + headless Chrome +
  leaflet-shadow-simulator, 491 sample tačaka × 4 referentna dana.
  Pipeline radi, ali rezultat (2–6 % senke svuda, gotovo bez varijacije
  između sezona) je neinformativan: SDK je samo engine, ne dolazi sa
  podacima o drveću i zgradama — bez `canopySource` / `getFeatures` /
  `dsmSource` izračun je samo bare-earth DEM. Niška dolina sa terenom
  samim ne pravi mnogo senke. Sekcija nije objavljena; postojeća
  tree-cover analiza ostaje glavni indikator senke od drveća; interaktivni
  ☀ dugme na mapi otvara shadeMap.app gde su drveće i zgrade serverski
  integrisani.
  - Pipeline (`shade_real.py`, `shade_compute.js`, `package.json`, Makefile
    `shade` + `node-deps` targeti) ostaje u repo-u, _uspavan_. Aktivacija
    je trivijalna ako se pojavi slobodno dostupan canopy/DSM tile source
    ili paid shadeMap tier.
  - Output (`data/shade_real.json`) je u `.gitignore`-u.
  - Detalji u `dnevnik.html` (post-mortem od 14. jun 2026.)

### Izmenjeno
- **Gušće uzorkovanje visine** — `ELEV_STEP_M` 50 → **30** (match nativnoj
  rezoluciji SRTM-a). Smoothing prozor 5 → **9** tačaka (ekvivalent fizičkog
  prozora od ~270 m). 293 → **491** uzoraka.
  - Ukupan uspon: 59 → **55 m**
  - Ukupan pad: 42 → **38 m**
  - Centar: 8 → **6 m** (preciznija lokalizacija rampi / mostova)
  - Max nagib: 3.2 % → **3.7 %** (bolje uhvaćen kratak uspon u Brzom Brodu)
- **Catmull-Rom spline za visinski profil** — SVG path je sada glatka
  cubic Bezier kriva umesto polyline cik-cak. Kriva i dalje prolazi kroz
  iste tačke (hover dot i tooltip pogađaju realne vrednosti), samo se
  segmenti između njih iscrtavaju glatko. Bez D3 ili drugih biblioteka.
- **Realističniji uspon i pad** — `asc_desc_grad()` sada koristi histerezisni
  filter sa pragom 1 m (ranije: naivno sabiranje svake promene). Eliminiše
  rezidualni SRTM šum koji je veštački napumpao kumulativne vrednosti na
  ravnim deonicama. Pristup je isti kao kod Strava / Garmin „elevation gain".
- Max gradient filter: segmenti kraći od pola koraka (15 m) se preskaču —
  filter krajnjeg „repa" trase posle resampling-a, koji je davao fiktivnih
  10 % nagiba (0.1 m / 1 m).
- KML podaci osveženi (`koridor_data.kml`) — novi pinovi i ažurirane
  oznake sa terena.

### Dodato
- Custom CSS tooltip (`.info-mark[data-tip]`) sa fokus podrškom za
  touch uređaje — zamenjuje nepouzdan native `title` atribut.
- Tooltip ⓘ pored „Ukupan uspon" / „Ukupan pad" objašnjava razliku
  između kumulativnog uspona i raspona min–max, jezikom koji ne traži
  tehnički background.
- Nova `CHANGELOG.md`.

## [2026-06-12]

### Dodato
- **Anketa: glas građana** — 277 anonimnih odgovora prikazanih kao donut
  i bar chart-ovi, sa karuselom od 83 slobodna komentara (auto-rotacija
  8 s, pauza na hover).
  - `anketa.py`: anonimizacija CSV-a (izbacuje ime / e-mail / vreme /
    komentare iz agregata; defanzivni regex briše e-mail / telefon /
    URL iz komentara koji idu u karusel), de-duplikacija, filter ispod
    15 znakova, deterministican shuffle (seed 42).
  - `data/anketa.json` izlaz; sirov `anketa.csv` u `.gitignore`-u.
- **Pokrivenost zelenila i diskontinuitet senke** — satelitska
  klasifikacija (ESA WorldCover 2021 v2, 10 m, preko Terrascope WMTS) sa
  3×3 majority kernel i „land-prior" bias-om koji ispravlja mixed-pixel
  artefakte (Centar: 22 % vode → 1 %).
- **Visinski profil trase** — Open-Topo-Data SRTM 30 m sa 5-tačka
  centralnim moving average-om; handroll SVG sa hover tooltip-om i
  pozadinskim trakama po deonicama.
- **shadeMap.app integracija** — dugme ☀ gore-levo na mapi otvara
  shadeMap sa trenutnom pozicijom i slider-om za datum / sat.
- **Tipovi prekida u kretanju** — klasifikacija 52 prekida u 10 tipova
  regex pattern matching-om.
- **Instagram „zapratite nas"** — link na [@es.quina_urbana](https://www.instagram.com/es.quina_urbana/)
  u hero CTA grupi, u sekciji „Uključi se" i u footer-u.
- **Tehnički dnevnik** (`dnevnik.html`) — hronološki pregled tehničkih
  odluka i izvora podataka.
- **GPL-3.0 licenca** (`LICENSE`) + link na GitHub repository u footer-u.
- `data/.cache/` i `anketa.csv` u `.gitignore`-u; `.venv/` za Pillow.

## [2026-06-05]

### Dodato
- **Galerija „Sa terena"** — 28 mapiranih fotografija filterabilnih po
  kategoriji (prekidi, stepenice i rampe, urbana oprema, stanja,
  vegetacija, urbani džepovi); lightbox sa keyboard navigacijom i swipe-om.
  - MyMaps `fife=sNNNN` normalizovan na `s1024` (ukupna veličina 577 MB
    → 43 MB bez vidljive razlike na popup-u i lightbox-u).
  - Imena fajlova su SHA1 hash izvornog URL-a — idempotentno preuzimanje.
  - Orphan prune posle konverzije briše slike koje više nisu referencirane.
- **`meta_deonice` u KML-u** — koridor je podeljen na 6 deonica
  (Medoševac → Centar → Delta-Lidl → Gabrovačka Reka → Brzi Brod →
  Niška Banja). Sva mapiranja se grupišu po deonici za lokalnu analizu.
  - Pinovi klasifikovani ray-casting „point-in-polygon" testom.
  - Linije klasifikovane po midpoint-u; dužina razdeljena proporcionalno
    između deonica preko pojedinačnih segmenata.
  - Smoothing pass posle klasifikacije popunjava izolovane „None" tačke.

## [2026-06-04]

### Dodato
- **Inicijalna verzija sajta i KML pipeline-a**.
  - `convert.py` čita KML preko `xml.etree.ElementTree`, normalizuje
    imena slojeva (typo handling: „vioska vegetacija" → „visoka_vegetacija",
    „loshe stanje" → „loše"…), kategorizuje pinove regex pattern matching-om.
  - Generiše po jedan GeoJSON per kategoriju + `data/stats.json` sa
    svim agregatima.
  - Leaflet mapa sa CartoDB Voyager (default), ESRI World Imagery
    (satelit) i OSM HOT (humanitarni stil) bazama; OpenStreetMap kao
    osnova kartografskih podataka.
  - KPI brojevi i bar chart-ovi po tipu podloge, urbane opreme i vegetacije.
  - Vanilla JavaScript + Leaflet — bez framework-a, bez build step-a,
    bez NPM-a. Sve statičko, GitHub Pages servira direktno.
- **`make fetch`** — ekstraktuje pravi `<href>` iz Google MyMaps
  NetworkLink-a i čuva u `koridor_data.kml`.

### Izmenjeno
- Mobilna mapa — popravljen tile provider, vidljiviji „Slojevi" toggle.
- Auto-collapse layer kontrole na mobile ↔ desktop granici.
- Tap mape zatvara layer panel (mobile UX).
