VENV    := .venv
PYTHON  := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PORT    ?= 8000
# EEA daje parquet, a pyarrow nema wheel za Python 3.14 koji projekat koristi.
# Ako postoji uv, taj jedan korak se vrti u izolovanom 3.13 okruženju.
UV      := $(shell command -v uv 2>/dev/null)
PY_PARQ := $(if $(UV),uv run --quiet --python 3.13 --with pyarrow python,$(PYTHON))
SOURCE  := my_maps.kml
KML     := koridor_data.kml
# Ekstraktuje href iz NetworkLink-a u $(SOURCE) (radi i sa CDATA wrapperom).
KML_URL  = $(shell grep -oP '<href>\s*(<!\[CDATA\[)?\K[^]<]+' $(SOURCE))

.PHONY: help convert serve fetch analyze clean all venv anketa node-deps shade canopy noise vazduh views termalni indikatori safety teren teren-pdf

help:
	@echo "Dostupni targeti:"
	@echo "  make venv      - kreira .venv/ i instalira Python zavisnosti (Pillow, numpy, rasterio)"
	@echo "  make convert   - KML -> GeoJSON + stats.json + slike + visine + land cover (idempotentno)"
	@echo "  make canopy    - senka od krošnji za sve tri staze (traži convert) -> data/shade_canopy.json"
	@echo "  make noise     - buka iz geometrije puteva (OSM) -> data/buka.json"
	@echo "  make vazduh    - vazduh sa mernih stanica (EEA/SEPA, traži uv) -> data/vazduh.json"
	@echo "  make views     - pogled na reku (OSM voda + krošnje, traži canopy) -> data/river_views.json"
	@echo "  make termalni  - termalni komfor u °C (UTCI, traži canopy) -> data/termalni.json"
	@echo "  make indikatori - tabela pokazatelja sekcije 9 (traži canopy, noise, views, termalni)"
	@echo "  make anketa    - anonimizuje anketa.csv -> data/anketa.json (samo agregati)"
	@echo "  make node-deps - instalira Node zavisnosti za shadeMap pre-compute (Puppeteer)"
	@echo "  make shade     - pre-računa pokrivenost senkom (treba SHADEMAP_API_KEY env)"
	@echo "  make serve     - pokrece lokalni HTTP server na portu $(PORT)"
	@echo "  make fetch     - preuzima sveže podatke sa Google MyMaps (-> $(KML))"
	@echo "  make analyze   - prikazuje pregled KML strukture (analyze.py)"
	@echo "  make safety    - bezbednosni audit: tamne zone, stanja, konflikti -> data/safety.json"
	@echo "  make teren     - merne tačke za kalibraciju buke -> docs/ + data/merne_tacke.json"
	@echo "  make teren-pdf - obrazac za štampu sa QR kodovima -> docs/.../obrazac.pdf"
	@echo "  make all       - ceo lanac svih koraka odozgo, redom"
	@echo "  make clean     - briše data/ (GeoJSON + slike) i preuzeti KML"

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install Pillow numpy rasterio qrcode
	@echo "Venv spreman: 'make convert' automatski koristi $(VENV)/bin/python"

convert:
	$(PYTHON) convert.py

anketa:
	$(PYTHON) anketa.py

serve:
	@echo "Otvori http://localhost:$(PORT) u browseru (Ctrl+C za stop)"
	$(PYTHON) -m http.server $(PORT)

fetch:
	@test -f $(SOURCE) || { echo "Nedostaje $(SOURCE) (sa NetworkLink URL-om)"; exit 1; }
	@test -n "$(KML_URL)" || { echo "Ne mogu da ekstraktujem URL iz $(SOURCE)"; exit 1; }
	@echo "URL: $(KML_URL)"
	curl -sSL "$(KML_URL)" -o $(KML)
	@echo "Preuzeto: $(KML) ($$(wc -l < $(KML)) linija)"

analyze:
	$(PYTHON) analyze.py

node-deps:
	@command -v npm >/dev/null || { echo "npm nije instaliran"; exit 1; }
	npm install
	@echo "Node deps spremni. Pokreni: SHADEMAP_API_KEY=<ključ> make shade"

shade:
	@test -d node_modules || { echo "Prvo: make node-deps"; exit 1; }
	$(PYTHON) shade_real.py

canopy:
	$(PYTHON) shade_canopy.py

noise:
	$(PYTHON) buka.py

vazduh:
	$(PY_PARQ) vazduh.py

views:
	$(PYTHON) river_views.py

termalni:
	$(PYTHON) termalni.py

indikatori:
	$(PYTHON) indikatori.py

safety:
	$(PYTHON) safety.py

teren:
	$(PYTHON) docs/9.2-kalibracija-buke/izbor_tacaka.py

teren-pdf: teren
	@test -d node_modules || { echo "Prvo: make node-deps"; exit 1; }
	node docs/9.2-kalibracija-buke/napravi_pdf.js

all: fetch convert anketa canopy noise vazduh views termalni indikatori safety teren

clean:
	rm -rf data/
	rm -f $(KML)
	@echo "Obrisano: data/, $(KML)"
