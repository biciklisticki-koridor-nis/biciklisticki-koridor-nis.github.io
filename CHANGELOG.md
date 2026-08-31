# Changelog

Sve značajne izmene sajta i pipeline-a su u ovoj listi, sa najnovijim na vrhu.
Format prati [Keep a Changelog](https://keepachangelog.com/sr/1.1.0/).

## [Neobjavljeno]

### Dodato
- **Parser sloja „Definirane staze" → `data/staze_mreza.geojson`** — koridor
  više nije jedna linija nego tri paralelne mreže: biciklistička staza,
  pešačka na gornjem i pešačka na donjem bedemu.
  - Klasifikacija se čita iz `<description>` placemark-a, ne iz imena —
    MyMaps imena su auto-generisana („Línea 52") i ponavljaju se.
    Typo handling „peshaci" → `pesacki_*`, kao i za vegetaciju.
  - `splice_chains()` spaja fragmente u orijentisane lance po poklapanju
    krajnjih tačaka (2 m): 78 linija → 61 lanac. Bez toga nijedna mreža
    osim biciklističke nema upotrebljivu km-osu. Y-raskrsnice ostaju
    razdvojene — polilinija se ne grana.
  - **Referentna osa koridora** = najduži lanac tipa `bici`
    (`uloga: "osa"`, 14.03 km); ostalih 32 `bici` lanaca su `krak`
    (prilazi naseljima, rampe, izlaz na petlju).
  - Svaki lanac nosi `km_od`/`km_do` — raspon kilometraže ose koji pokriva,
    da bi sve tri mreže ostale na istoj kilometraži. `null` za tri kraka
    uz Gabrovačku Reku, koji su dalje od 40 m od ose.
  - `stats.staze_mreza`: dužina, broj lanaca, pokrivenost ose i rupe po
    mreži. Gornji bedem pokriva 99.3 % ose, donji **90.0 %** — nedostaje
    na km 1.69–2.13 (450 m) i km 13.23–14.03 (810 m).
  - Ostatak pipeline-a je netaknut: `trasa_km` je i dalje 14.67 km sa stare
    „Indicaciones" linije. Prelazak sajta na novu osu je zaseban korak.
- **Stranica „Analiza podataka" (`analiza.html`) sa sekcijom „Pokrivenost
  senkom"** — senka od krošnji izračunata sat po sat za 4 referentna dana
  (solsticiji + ravnodnevnice), na 10 m koraku duž trase (1.469 tačaka):
  - Toplotna mapa km × sat (canvas, tabovi po dobu godine, hover tooltip
    sa visinom krošnje, granice deonica).
  - Mapa sa trasom obojenom po stanju sunce/senka u izabranom satu
    (custom Leaflet canvas layer + klizač); režim „Ceo dan" boji trasu
    gradijentom po ukupnim sunčanim satima.
  - Stat kartice + tabela po deonicama (pokrivenost drvoredom, prosečna
    visina krošnje, % senke po datumu).
- **`shade_canopy.py` + `make canopy`** — reaktivacija uspavanog shade
  eksperimenta iz juna: uslov iz post-mortema („slobodan canopy source")
  ispunjen je pojavom [Meta/WRI Canopy Height Map](https://registry.opendata.aws/dataforgood-fb-forests/)
  (1 m, CC BY 4.0, COG na AWS Open Data — čita se samo prozor oko trase).
  Umesto shadeMap SDK-a: NOAA položaj sunca + numpy ray-marching od
  bicikliste (1.5 m) ka suncu preko rastera krošnji. Bez API ključa i
  Puppeteer-a. Sanity check: dec 15.8 % > mar 13.0 % > jun 9.0 % senke
  (nisko sunce = duže senke); pokrivenost drvećem 26.8 % konzistentna sa
  WorldCover proksijem (23.4 %). Izlaz `data/shade_canopy.json` (75 KB);
  CHM keš u `data/.cache/canopy/`. Venv sada uključuje numpy + rasterio.
- Linkovi na novu stranicu sa početne (sekcija zelenila + footer);
  dnevnik post sa metodom i ograničenjima (snimci 2018–2020, bez zgrada,
  teren zanemaren).

- **WhatsApp grupa zajednice** — dugme „Uključi se" u hero-u sada vodi direktno
  na grupu (ranije skrolovalo na sekciju), plus kartica u sekciji „Uključi se"
  i link u futeru.
- **Tri staze na glavnoj mapi** — `staze_mreza.geojson` se crta kao tri sloja
  (biciklistička narandžasto, gornji bedem plavo, donji bedem ljubičasto;
  puna linija = glavna osa, isprekidana = prilazi), sa legendom iznad mape.
  Stara „Glavna trasa" ostaje kao sloj, ali podrazumevano isključena — KPI
  dužine i visinski profil se i dalje računaju sa nje.
  - Globalni prekidač staza na početnoj **namerno nije dodat**: dužina, profil
    i gustine opreme se i dalje računaju sa stare linije, pa bi prekidač
    obećavao da se svi brojevi menjaju po stazi, a menjali bi se samo neki.
- **Kontinuitet drvoreda po stazi** — `shade_canopy.py` računa najduži
  neprekidan deo uz drvored, najdužu rupu i broj prelaza, iz CHM podataka
  (1 m) umesto dosadašnjeg WorldCover proksija (10 m). Prikazano kao dve nove
  stat kartice i kolona u tabeli na `analiza.html`. Rupe u samoj stazi
  prekidaju niz, da se odsustvo staze ne bi računalo kao odsustvo drvoreda.
  Najduži deo biciklističke staze bez ijednog drveta uz nju: **3.13 km**
  (gornji bedem 1.01 km, donji 1.46 km).

### Izmenjeno
- **Sekcija senke na početnoj svedena na traku + link** — dosad su tu stajale
  stat kartice i kartice po deonicama izvedene iz ESA WorldCover klasifikacije
  zemljišta (10 m), pod imenom „senka". To je odgovaralo na drugo pitanje
  („ima li ovde drveća kao klase zemljišta") nego `analiza.html`
  („da li je staza stvarno u senci u 14h"), a brojevi se nisu slagali.
  Sada na početnoj ostaje traka kao gruba orijentacija, preimenovana u
  „Drvored duž cele trase", a stvarna senka i kontinuitet su na `analiza.html`.
  Uklonjeni `renderShadeStats()` i `renderShadeByDeonica()` iz `app.js`.
- **Senka se računa za sve tri staze** — `shade_canopy.py` više ne čita jednu
  liniju nego `data/staze_mreza.geojson`, i računa zaseban profil senke za
  biciklističku stazu i obe pešačke. Kilometraža je zajednička: svaka tačka
  dobija km projekcijom na biciklističku osu (tačke dalje od 40 m —
  prilazi naseljima — se izostavljaju), pa su tri profila direktno uporediva.
  `CANOPY_SCHEMA` 2 → 3, izlaz 75 KB → 214 KB.
  - **Nalaz: donji bedem ima duplo više hlada.** U junu 23.8 % vremena u
    senci, prema 11.6 % na biciklističkoj i 8.6 % na gornjem bedemu;
    pokrivenost drvoredom 50.3 % prema 27.3 % i 27.6 %. Tri staze su na
    svega ~9 m jedna od druge, ali su tri različite mikroklime. Razlika je
    najveća u Brzom Brodu (donji bedem 77.7 % uz drvored) i najmanja u
    Medoševcu (0.6 %).
  - Prelazak sa stare „biciklisticka trasa" linije na novu bici osu sam
    diže senku u junu sa 8.0 % na 11.6 % — nova osa prolazi bliže drvoredu.
    Provereno puštanjem stare linije kroz novi kod: reprodukuje 8.0 %,
    dakle razlika je geometrijska, ne posledica izmene računa.
  - `analiza.html` dobija prekidač staza; heat-mapa i tabela prate izbor.
    x-osa heat-mape je uvek puna dužina referentne ose, pa se prekidi u
    pešačkim stazama vide kao praznine umesto da se sakriju rastezanjem.
  - CHM keš sada nosi hash uzoraka i sam se poništava kad se skup staza
    promeni — prozor mora da pokrije sve tri.
- **Senka se računa po ručno crtanoj trasi** — `shade_canopy.py` sada čita
  liniju „biciklisticka trasa" iz `meta_deonice` sloja KML-a (fallback:
  `data/trasa.geojson`), a deonice dodeljuje point-in-polygon testom na
  `deonice.geojson` poligonima. Nova linija (14.40 km, medijan 2.0 m od
  terenski mapiranih staza vs 3.5 m kod Google-rutirane) prati stazu na
  keju umesto okolnih ulica; ispravlja obilaske na km 2.9, 4.7–5.1 i 11.2.
  Efekat na brojke: ukupna senka 21. jun 9.0 % → **7.8 %**; najveća
  promena u Centru (16.1 % → 0.9 % jun) — stara linija je senku
  „pozajmljivala" od drvoreda na uličnoj strani, dok stvarna staza ide
  otvorenim donjim šetalištem. `CANOPY_SCHEMA` 1 → 2. Ostatak sajta
  (dužina, profil) za sada ostaje na staroj trasi — odluka o potpunom
  prelasku je odložena.

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
