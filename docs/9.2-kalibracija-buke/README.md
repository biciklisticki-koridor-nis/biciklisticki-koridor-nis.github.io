# Kalibracija modela buke — terenska merenja

Uputstvo za jedan terenski izlazak koji model buke iz analize 9.2 prevodi iz
relativnog indeksa 0–100 u decibele, i proverava da li uopšte ispravno rangira
deonice.

**Fajlovi:** [`tacke.gpx`](tacke.gpx) (18 waypoint-a + redosled obilaska) ·
[`tacke.csv`](tacke.csv) (tabela za popunjavanje na terenu) ·
[`izbor_tacaka.py`](izbor_tacaka.py) (regeneriše oba iz `data/noise_air.json`)

```
.venv/bin/python docs/9.2-kalibracija-buke/izbor_tacaka.py
```

---

## Zašto je dovoljno 18 tačaka

Model već daje ispravan *oblik* profila; nepoznati su samo nula i nagib.
Fizika kaže da je nivo linearan po `10·log10(energija)`, pa je kalibracija
regresija sa **dva slobodna parametra**:

```
dB(A) = a + b · 10·log10(E_model)
```

Dva parametra znače da je bitan **raspon prediktora**, a ne količina merenja.
Zato tačke nisu ravnomerno raspoređene po kilometraži nego **raslojene po
indeksu** — od 8 do 100, sa po nekoliko iz svakog pojasa i naglaskom na
krajevima skale, koji nose najviše informacije za nagib.

Sve nespojene tačke su međusobno udaljene bar 350 m, da budu nezavisne.

## Uparene tačke — jedino merenje koje daje nešto novo

Četiri para (**T04–T05, T06–T07, T08–T09, T11–T12**) su gornji i donji bedem
na *istoj kilometraži*, razmaknuti 11–42 m.

Njihova izmerena razlika direktno daje **zaklon nasipa** — član koji model
nema, jer SRTM na 30 m stavlja 88 % parova te dve staze u istu ćeliju i
vraća im identičnu visinu. To je jedina veličina iz ovog izlaska koja se ne
može dobiti nikakvim doterivanjem modela.

Sva četiri para su namerno u bučnim zonama (indeks ≥ 40): u tišini bi šum
Nišave nadjačao razliku.

**Obe tačke para meriti u razmaku od par minuta**, da saobraćaj bude isti.

## Tačke

Obilazak redom **T01 → T18 je 13,0 km**, jedan prolaz bez vraćanja.
Sa 3–5 minuta po tački, ukupno **2,5–3 sata**.

| ID | km | Staza | Deonica | Koordinate | Indeks | Uloga |
|---|---:|---|---|---|---:|---|
| T01 | 0.00 | Biciklistička | Medoševac | `43.32186, 21.86763` | 78 | raspon skale |
| T02 | 0.53 | Biciklistička | Medoševac | `43.32414, 21.87327` | 24 | raspon skale |
| T03 | 1.54 | Biciklistička | Medoševac | `43.32314, 21.88441` | 63 | raspon skale |
| T04 | 2.17 | Gornji bedem | Centar | `43.32111, 21.89090` | 89 | **par 4** (11 m) |
| T05 | 2.18 | Donji bedem | Centar | `43.32115, 21.89103` | 82 | **par 4** (11 m) |
| T06 | 3.31 | Gornji bedem | Centar | `43.32667, 21.90281` | 90 | **par 3** (42 m) |
| T07 | 3.32 | Donji bedem | Centar | `43.32630, 21.90272` | 89 | **par 3** (42 m) |
| T08 | 3.88 | Donji bedem | Delta – Lidl | `43.32633, 21.90885` | 88 | **par 2** (31 m) |
| T09 | 3.89 | Gornji bedem | Delta – Lidl | `43.32606, 21.90876` | 93 | **par 2** (31 m) |
| T10 | 5.29 | Biciklistička | Delta – Lidl | `43.32470, 21.92444` | 50 | raspon skale |
| T11 | 6.46 | Gornji bedem | Delta – Lidl | `43.32198, 21.93700` | 99 | **par 1** (32 m) |
| T12 | 6.46 | Donji bedem | Delta – Lidl | `43.32223, 21.93720` | 100 | **par 1** (32 m) |
| T13 | 7.78 | Biciklistička | Brzi Brod | `43.32037, 21.95177` | 29 | raspon skale |
| T14 | 8.99 | Biciklistička | Brzi Brod | `43.31579, 21.96516` | 11 | raspon skale |
| T15 | 10.54 | Biciklistička | Niška Banja | `43.31161, 21.98208` | 36 | raspon skale |
| T16 | 11.08 | Biciklistička | Niška Banja | `43.30762, 21.98552` | 82 | raspon skale |
| T17 | 12.10 | Biciklistička | Niška Banja | `43.30477, 21.99727` | 8 | raspon skale |
| T18 | 13.81 | Biciklistička | Niška Banja | `43.30261, 22.01609` | 49 | raspon skale |

## Protokol

- **3–5 minuta po tački**, mikrofon na oko **1,5 m** visine
- meri se **LAeq** — ekvivalentni kontinuirani nivo, **A-ponderisano, Fast**.
  Ne vršni i ne trenutni nivo.
- ako uređaj daje percentile, zapisati i **LA90** (pozadinski nivo)
- **sve tačke u istom vremenskom prozoru**, radnim danom, 2–3 sata.
  Model nema dnevnu dimenziju, pa se kalibriše na jedno stanje saobraćaja —
  i to se tako i napiše na stranici.
- odmaknuti se od lokalnih izvora: šetača, pasa, dece na igralištu
- **bez kiše, bez vetra jačeg od ~5 m/s**; pena na mikrofonu obavezna
- zapisati vreme svakog merenja u `tacke.csv`

## Oprema

| Alat | Cena | Android | iPhone | CSV izvoz | Kalibracija | GPS-tag | Ocena |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Class 2 merač (hardver) | ~35–60 € | — | — | retko | fabrička | ne | **9** |
| [NoiseCapture](https://f-droid.org/packages/org.noise_planet.noisecapture/) | besplatno | ✓ | ✗ | ✓ | ✓ | ✓ | **8** |
| [NIOSH SLM](https://apps.apple.com/us/app/niosh-sound-level-meter/id1096545820) | besplatno | ✗ | ✓ | ✓ | ✓ | ne | **7** |
| [Decibel X](https://www.skypaw.com/decibelx.html) | free / ~8 € Pro | ✓ | ✓ | Pro | ✓ | ne | **6** |
| Generičke „Sound Meter" aplikacije | besplatno | ✓ | ✓ | retko | retko | ne | **2** |

**Preporuka: jedan Class 2 merač (~40 €) za grupu, plus NoiseCapture na
telefonima kao paralelna provera.**

NoiseCapture je najbolji softverski izbor — otvoren kod, iza njega stoje
Université Gustave Eiffel i CNRS, pravljen baš za građansko mapiranje buke.
GPS-tagovanje znači da se merenja sama vežu za kilometražu bez ručnog
zapisivanja, a daje LA90/LA50/LA10 percentile. Mana: samo Android.

NIOSH je jedina aplikacija sa objavljenom validacijom (±2 dB(A)), ali samo za
iOS — [NIOSH je ispitao 192 aplikacije](https://www.cdc.gov/niosh/bulletin/2017/sound-app.html)
i nijedna Android nije prošla, jer je hardver preraznorodan.

Generičke „Sound Meter" aplikacije nose ocenu 2 jer skoro nijedna ne traži
`UNPROCESSED` audio izvor, pa im automatska kontrola pojačanja (AGC) izravna
upravo ono što se meri. Daju uverljive brojeve bez značenja.

**Nekalibrisan telefon je ipak dovoljan za veći deo posla.** Konstantno
odstupanje mikrofona upada u presek `a` regresije i poništava se — bitna je
linearnost, ne apsolutna tačnost. Merač treba tek ako hoćemo da na stranici
stoje apsolutni decibeli.

**Praktični trik:** pustiti NoiseCapture da snima neprekidno kroz ceo
obilazak. Zaustavljanja ispadaju kao čiste zaravni u GPS tragu i iz njih se
vade vrednosti — jedno snimanje, jedan prolaz, bez ručnog beleženja. Vožnja
između tačaka je zagađena šumom vetra i baca se, ali ništa ne košta.

## Šta očekivati

**Pod od reke.** Na najtišim tačkama (T14, T17) Nišava će verovatno postaviti
donju granicu — tekuća voda je širokopojasni šum. Ako izmereni nivoi prestanu
da padaju ispod neke vrednosti koliko god model išao naniže, **to nije greška
modela nego reka**. Vredi to unapred znati da se ne pročita kao promašaj.
Usput je i dobar nalaz za stranicu: najtiši delovi koridora nisu tihi, nego
zvuče kao reka.

**T11/T12 su predviđeni kao najglasnija tačka koridora** (indeks 99/100, glavni
put na svega par metara). Proveriti pristupačnost i bezbednost pre merenja.

## Obrada

1. Regresija `dB(A) = a + b · 10·log10(E)`; zapisati `R²` i standardnu
   devijaciju reziduala.
2. Spearman-ova korelacija između izmerenog i modeliranog redosleda —
   odgovara na pitanje da li model bar ispravno rangira.
3. Ako je `R²` iznad ~0,7, stranica dobija **dB(A) sa iskazanim intervalom
   nesigurnosti**, a indeks ostaje kao pomoćna skala. Ako je ispod, modelu
   fali struktura — najverovatnije baš zaklon — i zna se šta se sledeće
   popravlja.
4. Razlika unutar parova → empirijska konstanta zaklona nasipa, koja se vraća
   u `noise_air.py`.
5. Objaviti i sam dijagram rasipanja izmereno-naspram-modelirano, u duhu
   ostatka sajta: pokazati gde se slaže i gde ne.
