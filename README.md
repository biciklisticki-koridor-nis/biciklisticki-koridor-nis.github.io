# Nišavski biciklistički koridor

Web sajt koji vizuelizuje trenutno stanje na terenu duž keja reke Nišave, kao osnova za uspostavljanje biciklističkog koridora od Medoševca do Niške Banje.

## O projektu

Inicijativa zajednice u Nišu mapirala je stanje keja u Google MyMaps — staze, prekide u kretanju, urbanu opremu, vegetaciju i stanja očuvanosti. Ovaj repozitorijum pretvara te mape u jednu HTML stranicu sa interaktivnom mapom i statistikom, namenjenu široj zajednici (ne tehničarima).

**Ciljevi sajta:**
- Pokazati šta sve postoji (i ne postoji) na trasi budućeg koridora
- Pružiti konkretne brojke kao osnovu za razgovore sa gradskim strukturama
- Pozvati žitelje, bicikliste i urbaniste da se uključe u inicijativu

## Šta je mapirano

Ukupno **447 placemark-ova** u 7 slojeva:

| Sloj | Šta sadrži |
|---|---|
| Glavna trasa | 14.67 km linija od Medoševca do Niške Banje |
| Zelena infrastruktura | Visoka/niska vegetacija, izvori, česme |
| Prekidi u kretanju | 52 lokacije gde je kretanje prekinuto |
| Stepenice i rampe | 80 stepenica, 12 rampa, segmenti staza po podlozi |
| Urbana oprema | 130 svetiljki, 36 klupa, kante, letnjikovci, sport. sadržaji |
| Stanja očuvanosti | Ocene loše/srednje/dobro, deponije |
| Urbani džepovi | Amfiteatar, javno plato |

## Struktura repozitorijuma

```
.
├── index.html, style.css, app.js   # sajt (vanilla + Leaflet.js)
├── my_maps.kml                     # NetworkLink stub (izvor URL-a)
├── convert.py                      # KML → GeoJSON pipeline
├── analyze.py                      # pregled KML strukture
├── Makefile                        # orkestracija
├── data/                           # generisani GeoJSON-ovi + stats.json
└── CONTEXT.md                      # kontekst i ciljevi projekta
```

## Korišćenje

```sh
make fetch     # preuzima sveže podatke sa Google MyMaps
make convert   # KML → GeoJSON + stats.json u data/
make serve     # pokreće lokalni HTTP server (port 8000)
make all       # fetch + convert
make analyze   # pregled strukture KML-a
make clean     # briše data/ i preuzeti KML
```

Tipičan workflow nakon promene mape u MyMaps:
```sh
make all && make serve
```
Zatim otvori `http://localhost:8000`.

## Tehnologija

- **Vanilla HTML/CSS/JS** — bez framework-a, lako za održavanje
- **Leaflet.js** (CDN) — interaktivna mapa
- **Python 3** (standardna biblioteka) — KML parsing i konverzija
- **OpenStreetMap** — bazna mapa; opciono Esri satelit

## Hosting

Sajt je statičan i može se hostovati besplatno na GitHub Pages, Netlify ili sličnim servisima. `data/` folder mora biti commit-ovan (sajt učitava GeoJSON-ove preko `fetch()`).

## Doprinos

Vidiš nešto pogrešno mapirano, novi prekid na terenu, ili želiš da se pridružiš inicijativi? Otvori issue ili pull request.

## Licenca

Otvoreni podaci — slobodno korišćenje uz navođenje izvora.
