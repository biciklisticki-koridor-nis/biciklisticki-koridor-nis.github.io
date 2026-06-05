PYTHON  ?= python3
PORT    ?= 8000
SOURCE  := my_maps.kml
KML     := koridor_data.kml
# Ekstraktuje href iz NetworkLink-a u $(SOURCE) (radi i sa CDATA wrapperom).
KML_URL  = $(shell grep -oP '<href>\s*(<!\[CDATA\[)?\K[^]<]+' $(SOURCE))

.PHONY: help convert serve fetch analyze clean all

help:
	@echo "Dostupni targeti:"
	@echo "  make convert   - KML -> GeoJSON + stats.json + skida slike u data/images/ (idempotentno)"
	@echo "  make serve     - pokrece lokalni HTTP server na portu $(PORT)"
	@echo "  make fetch     - preuzima sveže podatke sa Google MyMaps (-> $(KML))"
	@echo "  make analyze   - prikazuje pregled KML strukture (analyze.py)"
	@echo "  make all       - fetch + convert"
	@echo "  make clean     - briše data/ (GeoJSON + slike) i preuzeti KML"

convert:
	$(PYTHON) convert.py

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

all: fetch convert

clean:
	rm -rf data/
	rm -f $(KML)
	@echo "Obrisano: data/, $(KML)"
