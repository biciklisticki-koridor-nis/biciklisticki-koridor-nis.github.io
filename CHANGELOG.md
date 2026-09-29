# Changelog

Sve značajne izmene sajta i pipeline-a su u ovoj listi, sa najnovijim na vrhu.
Format prati [Keep a Changelog](https://keepachangelog.com/sr/1.1.0/).

## [Neobjavljeno]

### Dodato
- **Analiza 9.3 — termalni komfor i kvalitet predela**, u stepenima a ne u
  oceni od 0 do 100. Predlog je bio da se senka, voda, vegetacija, podloga,
  sunce, otvorenost i izgrađenost saberu u jedinstven indeks; to bi izgledalo
  kao sedam faktora a ponašalo se kao jedan, pa se umesto toga računa fizika i
  izlazi **UTCI**, sa priznatom skalom toplotnog stresa. Činioci ostaju na
  stranici, ali kao objašnjenje zašto je negde toplije, ne kao ulaz u ocenu.
  - **93 %** biciklističke staze je u *jakom toplotnom stresu* vrelog
    popodneva; potpuno ugodnog dela nema nijedan metar.
  - Krošnja spušta zračenje na telo (Tmrt) za **21,9 °C** — 53,1 prema
    31,2 — što je jedna cela kategorija stresa manje.
  - Medoševac, Centar i Delta–Lidl imaju **0,0 sati senke** u prozoru 12–17 h.
  - Vrh nije u podne nego u **15 h**: kad je Sunce visoko, na uspravno telo
    pada manji deo snopa.
  - Scenario je vruć vedar dan (77 najtoplijih od 310 dana oko solsticija,
    2016–2025), a ne prosek leta — kišni dani bi razblažili ono što se meri.
- **9.3.1 Mesta predaha** — potezi od bar 30 m koji ostaju u senci bar 5 od
  6 sati. Biciklistička staza ih ima 10 (4,8 % dužine), gornji bedem 6,
  donji bedem 26 (14,9 %). Najduži potez bez ijednog na biciklističkoj stazi
  je **8,84 km**.
  - **33 od 36 mapiranih klupa nema nijedan sat senke**, prosečan UTCI na
    klupi je 36,3 °C. Senka se računa na koordinati same klupe, ne u najbližoj
    tački staze.
- **Kvalitet predela** na istoj stranici, od ranije izračunatog pogleda na
  reku koji do sada nije imao gde da stoji. Spoj dva dela daje nalaz koji
  nijedan ne daje sam: zapadne deonice vide reku sa ~100 % trase i imaju
  0,0 sati senke, istočne je vide sa 28 % i imaju 0,9 sati. Pošto je
  geometrijski reka vidljiva sa cele trase, sav gubitak pogleda otpada na
  zelenilo — isto ono koje pravi hlad.
- **`utci.py`** — UTCI polinom (211 članova) bez ijedne spoljne biblioteke,
  jer numba nema wheel za Python 3.14. Programski izvučen iz
  `pythermalcomfort` 4.6.0 (MIT), ne prekucan. Nosi samoproveru
  (`python utci.py`) i proveren je protiv originala na 840 kombinacija —
  najveće odstupanje 0,000 °C.
- **`termalni.py` + `make termalni`** → `data/termalni.json` (191 KB).
- **Termalni komfor u tabeli pokazatelja** na `analize.html`: 36,3 / 36,4 /
  35,7 °C. Tabela sada nosi jedinicu po redu, jer nije sve u procentima.

### Popravljeno
- **Grafikon po satu** je crtao stubiće od tik ispod minimuma, pa je razlika
  od 1,6 °C izgledala petostruko. Sada počinju od granice kategorije, i to
  piše ispod grafikona.
- **Oznaka poslednjeg kilometra** na profilu sekla se o desnu ivicu platna
  (i na 9.2 i na 9.3).

### Izmenjeno
- **Kvalitet vazduha u analizi 9.2 više nije procena nego merenje.** Izvor su
  validirani časovni podaci zvaničnih mernih stanica (SEPA preko EEA, bez
  ključa), umesto CAMS-a preko Open-Meteo. Poređen sa stanicom na istim danima,
  CAMS daje PM2.5 1,58×, PM10 1,98× i NO₂ 4,05× niže, a za NO₂ dnevno nema
  veštinu (r = 0,29). Brojevi na stranici bili su zato pogrešni:
  - PM2.5 godišnje 24,7 umesto 16,9 µg/m³ (smernica SZO je 5), 52 % dana preko
    dnevne smernice umesto 45 %.
  - NO₂ 22,8 umesto 5,7 µg/m³; preko dnevne smernice 28 % dana, a ne 0,1 %.
  - PM10 prelazi zakonsku dnevnu granicu 76 dana godišnje kod keja, uz
    dopuštenih 35. Saobraćajna stanica prekoračuje **svake godine od 2013**,
    između 53 i 106 dana.
  - Polen ostaje na CAMS-u — stanice ga ne mere, a regionalna je pojava.
- **`noise_air.py` → `buka.py`**, `data/noise_air.json` → `data/buka.json`
  (schema 2). Vazduh je izašao iz tog modula čim je dobio sopstvenu prostornu
  logiku, pa je staro ime počelo da laže.

### Dodato
- **Procena NO₂ po deonicama (9.2)**, za maj–septembar: Niška Banja i Brzi Brod
  8,8–9,3, Medoševac 9,5–11,7, Delta–Lidl 11,0–11,5, Centar 14,5–15,5 µg/m³.
  Donji bedem je dosledno najčistiji. Ne interpolira se između stanica — dve
  urbane su 400 m jedna od druge, pa bi svaki gradijent preko 13 km bio
  artefakt njihovog položaja. Umesto toga se izmerena razlika između
  saobraćajne i pozadinske stanice raspoređuje modelom blizine puteva
  (eksponencijalno opadanje, L = 60 m), a regionalni i urbani član su merenja.
  - Sidro je **letnje**, ne godišnje: zimi pozadinska stanica ima viši NO₂ od
    saobraćajne (41,7 prema 25,2 u januaru) jer stoji u naselju sa
    individualnim grejanjem. Godišnja razlika je +2,8 µg/m³, letnja +9,6.
  - Čestice se po deonicama ne prikazuju: letnja razlika između te dve stanice
    je +3,6 za PM2.5 i −3,7 za PM10, pa nije saobraćajna.
- **Mapa mernih stanica** sa isprekidanim potezom do najbliže tačke trase, i
  grafikon prekoračenja zakonske granice po godini.
- **`vazduh.py` + `make vazduh`** → `data/vazduh.json` (10 KB). Pošto pyarrow
  nema wheel za Python 3.14, korak se vrti kroz
  `uv run --python 3.13 --with pyarrow` ako `uv` postoji.
- **Obrazac za teren (`obrazac.pdf`)** — A4 landscape, svih 18 mernih tačaka sa
  koordinatama na jednom listu i praznim kolonama za upis, uputstvo na
  poleđini. U zaglavlju dva QR koda, ka GPX-u i CSV-u na sajtu; provereni
  modul po modul na rasterizaciji od 300 dpi. `make teren-pdf`.
- **Tačke merenja na mapi buke** u analizi 9.2, iz `data/merne_tacke.json`.
- **Kolone `podloga` i `klupe` u `tacke.csv`** — pripadaju analizi 9.3, ali se
  beleže na istom izlasku, da se 13 km ne prelazi dvaput.

### Popravljeno
- **Linija smernice SZO na mesečnom grafikonu nikada se nije prikazivala na
  pravom mestu**: vrednost je prosleđivana kao `--szo: 26%`, pa je
  `calc(dužina × procenat)` nevalidan i linija je padala na dno okvira.
- **Dugački URL-ovi i putanje u dnevniku** razvlačili su stranicu na telefonu
  (`overflow-wrap` na inline `code`).

### Dodato
- **Sadržaj na vrhu `analize.html`** — sekcije i njihove analize sa
  linkovima: sekcija skače na sebe na stranici, objavljene analize otvaraju
  svoju stranicu, a one u pripremi su navedene bez linka. Sadržaj se gradi
  iz kartica na stranici, pa nova sekcija ne traži posebno održavanje.
  Kartice sekcije su sada iznad tabele pokazatelja.
- **Tabela pokazatelja sekcije 9 na `analize.html`** — po jedan broj za svaku
  od tri staze, za pokazatelje iz okvira analize. Najbolja staza je
  podebljana; na telefonu opis mere prelazi ispod naziva da bi brojevi stali
  bez skrolovanja.
  - Kontinuitet senke: % dužine u neprekidnoj *stvarnoj* senci od bar
    30 m, 21. jun 12–16 h — 4.8 / 1.9 / 14.9 %. Prva verzija je brojala
    nizove drvoreda i za donji bedem davala 45 % uz 81 % izloženosti suncu:
    leti u podne stablo od 10 m baca senku od 3,8 m, pa drvored pored staze
    ne zaseni stazu. Prag od 30 m je najniži koji podaci trpe za senku
    (prelom u raspodeli dužina nizova između 20 i 30 m).
  - Krošnje 27.3 / 27.6 / 50.3 %, sunce 21. jun 12–16 h 92.4 / 95.0 /
    81.0 %, pogled na reku 58.7 / 61.5 / 56.3 %, izloženost buci 28.4 /
    30.5 / 22.9 %. Termalni komfor je u pripremi (9.3).
  - Žarišta zagađenja vazduha su namerno izostavljena: CAMS ćelija od
    11 km ne razlučuje prostor, a glavni problem (PM2.5, zima) nije
    saobraćajni.
  - `indikatori.py` + `make indikatori` → `data/indikatori.json` (1,4 KB),
    da stranica ne bi učitavala 500 KB podataka po tački.
- **`river_views.py` + `make views` → `data/river_views.json`** — pogled na
  Nišavu: 72 zraka po tački preko CHM rastera, do 250 m, pogled ako se voda
  vidi u uglu od bar 10°. Voda iz OSM-a: poligoni zapadno od km 5, članovi
  multipoligon relacija istočno (sa adama), linija toka kao osigurač.
  Konzervativna i optimistična granica (vidi li se ispod visokog drveća) se
  razlikuju za 0.3–3.3 poena. Bez rastinja pogled bi imalo 100 % dužine, pa
  je sav gubitak pogleda rastinje: zapad 76–100 %, šumoviti istok 23–35 %.
  Gornji bedem je potcenjen jer teren nije modeliran.
- **`docs/` — materijali za terenski rad** koji ne idu na sajt. Prvi je
  `docs/9.2-kalibracija-buke/`: protokol za jedan izlazak kojim se model
  buke prevodi iz indeksa 0–100 u decibele.
  - **18 tačaka, jedan prolaz od 13 km, 2,5–3 h.** Kalibracija je regresija
    sa dva parametra (`dB(A) = a + b · 10·log10(E)`), pa je bitan raspon
    prediktora a ne količina merenja — tačke su raslojene po indeksu
    (8–100), a ne ravnomerno po kilometraži. Nespojene tačke su međusobno
    udaljene bar 350 m.
  - **Četiri uparene tačke** gornji/donji bedem na istoj kilometraži
    (11–42 m razmaka, sve u zonama indeksa ≥ 40). Njihova razlika meri
    **zaklon nasipa** — jedinu veličinu koja se ne može dobiti doterivanjem
    modela, jer SRTM na 30 m stavlja 88 % parova u istu ćeliju.
  - `izbor_tacaka.py` regeneriše `tacke.gpx` i `tacke.csv` iz
    `data/noise_air.json`; CSV ima prazne kolone za upis na terenu.
  - Preporučena oprema sa ocenama: Class 2 merač (~40 €) + NoiseCapture
    kao provera. Generičke „Sound Meter" aplikacije su izričito odbačene —
    ne traže `UNPROCESSED` audio izvor, pa im AGC izravna signal.
- **Analiza 9.2 „Buka i kvalitet vazduha"**
  (`9.2.noise_and_air_quality_exposure.html` + `noise_air.py`, `make noise`)
  — dva pitanja sa dva izvora, jer se razlikuju po tome šta mogu da kažu.
  - **Buka je prostorna.** Modelirana iz OSM geometrije puteva (Overpass,
    3.831 put / 22.103 segmenta, keširano po bbox-u): svaki segment je niz
    nekoherentnih tačkastih izvora, energija opada sa 1/d², težina je
    dužina × jačina po klasi puta, korigovana `maxspeed` i `lanes`.
    Radijus 300 m, korak 10 m, sve tri staze na zajedničkoj km-osi.
  - **Indeks 0–100, ne decibeli.** Duž keja nema nijednog merenja; skala je
    relativna na sam koridor, sa fiksnim kotvama u log-prostoru da vrednosti
    ne skaču kad se OSM promeni. Rangira deonice, ne tvrdi apsolutni nivo.
  - **Nalaz: Centar je jedina bučna deonica** — prosek 61, *nula* procenata
    tihog. Ostatak koridora je uglavnom van domašaja saobraćaja: 71.7 %
    trase nema nijedan glavni put u krugu od 300 m. Donji bedem je najtiša
    staza (35.6), 13 % tiši od gornjeg — isto rastojanje od ulica koje mu
    daje duplo više hlada.
  - **Vazduh nije prostoran** — CAMS preko Open-Meteo ima ćeliju ~11 km,
    jednu za ceo koridor, pa se prikazuje kao vremenski kontekst.
    PM2.5 prelazi dnevnu smernicu SZO 45 % dana (godišnji prosek 16.9
    naspram 5 µg/m³), ali gotovo isključivo zimi: decembar 31.5, jul 9.8.
    Kej se koristi tačno kada je vazduh najčistiji. Uz polen (breza mart,
    trave jun, ambrozija avgust).
  - Namerno izostavljeno: vegetacija kao akustična barijera (drveće
    zaklanja pogled snažno, zvuk slabo — 1–3 dB na 10 m gustog pojasa) i
    nasip pod donjim bedemom (SRTM 30 m stavlja 88 % parova gornja/donja
    staza u istu ćeliju — nije merljivo). Oboje zapisano u dnevniku.
- **`koridor.py`** — zajednička geometrija koridora (osa, resampling,
  projekcija na km-osu, deonice) izvučena iz `shade_canopy.py` pre pisanja
  `noise_air.py`, dok je postojao samo jedan korisnik. Provera: regenerisan
  `data/shade_canopy.json` je **identičan bajt u bajt** prethodnom.
- **Stranica „Analize podataka" (`analize.html`)** — rasputnica ka svim
  analizama, grupisana po sekcijama okvira. Za sada je popunjena sekcija
  9 („Kvalitet životne sredine"): 9.1 objavljena, 9.2 i 9.3 najavljene.
  Link je u futeru početne strane i u futeru svake analize.
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
- **Stranica „9.1 Senka i pokrivenost krošnjama"
  (`9.1.shade_and_tree_canopy_coverage.html`)** — senka od krošnji izračunata
  sat po sat za 4 referentna dana (solsticiji + ravnodnevnice), na 10 m
  koraku duž trase (1.469 tačaka):
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
  stat kartice i kolona u tabeli na `9.1.shade_and_tree_canopy_coverage.html`. Rupe u samoj stazi
  prekidaju niz, da se odsustvo staze ne bi računalo kao odsustvo drvoreda.
  Najduži deo biciklističke staze bez ijednog drveta uz nju: **3.13 km**
  (gornji bedem 1.01 km, donji 1.46 km).

### Izmenjeno
- **Bazna karta prebačena sa CartoDB Voyager na OpenStreetMap** —
  `basemaps.cartocdn.com` od septembra 2026. utiskuje „API KEY REQUIRED"
  preko pločica. Pogađalo je sve tri mape na sajtu (početna, 9.1, 9.2).
  Sada `tile.openstreetmap.org`, i dalje bez API ključa. Uklonjeni su
  `{s}` poddomeni i `{r}` retina sufiks koje OSM ne servira. Slojevi
  „Mapa (HOT)" i „Satelit" su netaknuti.
- **`analiza.html` → `9.1.shade_and_tree_canopy_coverage.html`** (i prateći
  `analiza.js`). Stranica više nije „ta jedna analiza" nego prva u nizu, pa
  ime nosi broj sekcije iz okvira. Naslov je sada „9.1 Senka i pokrivenost
  krošnjama", a putanja do nje ide preko `analize.html`. Stara adresa vraća
  404 — stranica je bila javna nekoliko dana, bez spoljnih linkova.
- **Sekcija senke na početnoj svedena na traku + link** — dosad su tu stajale
  stat kartice i kartice po deonicama izvedene iz ESA WorldCover klasifikacije
  zemljišta (10 m), pod imenom „senka". To je odgovaralo na drugo pitanje
  („ima li ovde drveća kao klase zemljišta") nego `9.1.shade_and_tree_canopy_coverage.html`
  („da li je staza stvarno u senci u 14h"), a brojevi se nisu slagali.
  Sada na početnoj ostaje traka kao gruba orijentacija, preimenovana u
  „Drvored duž cele trase", a stvarna senka i kontinuitet su na `9.1.shade_and_tree_canopy_coverage.html`.
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
  - `9.1.shade_and_tree_canopy_coverage.html` dobija prekidač staza; heat-mapa i tabela prate izbor.
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
