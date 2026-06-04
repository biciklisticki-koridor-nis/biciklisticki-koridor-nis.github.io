# Biciklistički koridor na keju Nišave – kontekst projekta

## Ko smo

Inicijativa zajednice u Nišu koja radi na uspostavljanju biciklističkog koridora duž keja reke Nišave.

## Faza projekta

Završeno mapiranje postojećeg stanja u Google MyMaps. Sledeći koraci su GIS analiza i izrada web sajta koji vizuelizuje podatke za širu zajednicu.

## Šta je mapirano (slojevi u MyMaps)

- Ulično osvetljenje
- Klupe
- Betonske staze
- Zemljane staze
- Prekidi u kretanju
- Visoka vegetacija
- Niska vegetacija
- (ostali slojevi po potrebi)

## Fajlovi u ovom folderu

- `*.kml` – eksportovani slojevi iz Google MyMaps (jedan KML po sloju, ili sve zajedno)
- `CONTEXT.md` – ovaj fajl

## Cilj

Napraviti **web sajt (jedna HTML stranica)** koja vizuelizuje podatke iz KML fajlova. Sajt je namenjen zajednici, ne tehničarima.

### Struktura sajta (već osmišljena)

1. **Hero sekcija** – naziv inicijative, kratki opis, CTA dugmad
2. **Pregled** – ključni brojevi (dužina trase, % osvetljenosti, broj prekida...)
3. **Mapa** – interaktivna, sa slojevima (embed ili Leaflet.js sa GeoJSON)
4. **Analiza** – bar chart po tipu podloge, pokrivenost osvetljenjem, itd.
5. **Uključi se** – poziv zajednici

### Tehnički stack (predlog)

- Čist HTML/CSS/JS, bez framework-a
- **Leaflet.js** za interaktivnu mapu (besplatan, open-source)
- KML → GeoJSON konverzija za Leaflet (ili direktno učitavanje KML pluginom)

## Zadaci za Claude Code sesiju

1. Pročitaj KML fajlove i izvuci podatke po sloju
2. Izračunaj statistike:
   - Ukupna dužina staza (betonska, zemljana, bez staze)
   - Broj tačaka po tipu (klupe, svetiljke, prekidi...)
   - Procenat trase pokriven osvetljenjem
3. Konvertuj KML u GeoJSON za Leaflet mapu
4. Napravi `index.html` sa svim sekcijama i stvarnim podacima

## Napomene

- Prototip sajta već postoji (napravljen u Claude.ai chat sesiji) – može da posluži kao vizuelna referenca
- Podaci su placeholder; treba ih zameniti stvarnim vrednostima iz KML-a
- Sajt treba da bude deljiv (GitHub Pages ili Netlify su opcija za hosting)
