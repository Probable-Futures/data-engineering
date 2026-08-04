# One-command runners for the downscaled-data analysis toolkit.
# All Python runs inside ./venv so it never touches the netcdfs/import poetry env.

PY := venv/bin/python
INDICATOR ?= days-above-35c
YEAR      ?=
PERIOD    ?=
PLACES    ?= Beirut,Cairo,Delhi
STORE     ?=
WL        ?= 0.5

.PHONY: help setup inspect quicklook timeseries compare validate warming-levels report clean

help:
	@echo "Targets:"
	@echo "  make setup                          create venv + install requirements"
	@echo "  make inspect STORE=<path>           summarize any .zarr/.nc store"
	@echo "  make inspect INDICATOR=days-above-35c"
	@echo "  make quicklook INDICATOR=.. YEAR=2050 [PERIOD=1971-2000]"
	@echo "  make timeseries INDICATOR=.. PLACES=Beirut,Cairo"
	@echo "  make compare  INDICATOR=days-above-35c    (old vs new, baseline)"
	@echo "  make compare  INDICATOR=days-above-35c WL=1.5 PERIOD=2024-2040   (warming level)"
	@echo "  make validate                       new data vs ERA5-Land observations"
	@echo "  make warming-levels                 estimate breaching years / windows"
	@echo "  make report   INDICATOR=days-above-35c    (client-ready HTML)"
	@echo "  make clean                          remove out/"
	@echo ""
	@echo "Point at the new data with PF_DOWNSCALED_DATA=<path> if not in the default location."

setup:
	python3 -m venv venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	@echo "venv ready."

inspect:
ifeq ($(STORE),)
	$(PY) inspect_store.py --indicator $(INDICATOR)
else
	$(PY) inspect_store.py "$(STORE)"
endif

quicklook:
	$(PY) quicklook.py --indicator $(INDICATOR) \
		$(if $(YEAR),--year $(YEAR),) $(if $(PERIOD),--period $(PERIOD),)

timeseries:
	$(PY) timeseries.py --indicator $(INDICATOR) --places $(PLACES)

compare:
	$(PY) compare_baseline.py --indicator $(INDICATOR) --wl $(WL) \
		$(if $(PERIOD),--period $(PERIOD),)

validate:
	$(PY) validate_era5land.py

warming-levels:
	$(PY) warming_levels.py

report:
	$(PY) report.py --indicator $(INDICATOR) --places $(PLACES)

clean:
	rm -rf out
