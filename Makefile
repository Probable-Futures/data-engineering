SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:

OGR2OGR := /usr/local/bin/ogr2ogr

# All data lives here
DATA_DIR := ./data

# Mirror of Woodwell GCP Bucket
WOODWELL_DATA := ${DATA_DIR}/woodwell

# Directory for storing mapbox related data assets
MAPBOX_DATA := ${DATA_DIR}/mapbox
MVT_DATA := ${MAPBOX_DATA}/mvt # Vector Tiles from Mapbox
MTS_DATA := ${MAPBOX_DATA}/mts # GeoJSON Sources for Mapbox Tiling Service

include env

PG_CONNECTION := PG:"host=${PG_HOST} user=${PG_USER} dbname=${PG_DBNAME} password=${PG_PASSWORD}"
LAYER_CREATION_OPTS := -lco GEOM_TYPE=geography -lco GEOMETRY_NAME=coordinates -lco FID=id
MAPBOX_USERNAME := probablefutures

define EXPORT_QUERY
select cell, $\
data_baseline_pctl10, data_baseline_mean, data_baseline_pctl90, $\
data_1c_pctl10, data_1c_mean, data_1c_pctl90, $\
data_1_5c_pctl10, data_1_5c_mean, data_1_5c_pctl90, $\
data_2c_pctl10, data_2c_mean, data_2c_pctl90, $\
data_2_5c_pctl10, data_2_5c_mean, data_2_5c_pctl90, $\
data_3c_pctl10, data_3c_mean, data_3c_pctl90 $\
from pf_private.aggregate_pf_dataset_statistic_cells where dataset_id = ${*}
endef

PHONY: install
install: bundle ## Install all dependencies

.PHONY: bundle
bundle: ## Install dependencies from Brewfile
	brew bundle

${MTS_DATA}/%.geojsonld: ## Export GeoJSONSeq from Database
	echo "Begining export of dataset ${*}"
	ogr2ogr -wrapdateline -f GeoJSONSeq $@ ${PG_CONNECTION} -sql "${EXPORT_QUERY}"
	echo "Dataset ${*} export complete.\n"
	touch $@

${PG_SCHEMA_DATA}/%.sql: ## Dump schema from Database
	pg_dump ${PG_URL} --disable-triggers --clean --if-exists --schema-only --no-privileges --table '${*}' -f $@
	touch $@

${PG_COPY_DATA}/%.copy: ## Copy data from database table
	psql ${PG_URL} -e --command "copy ${*} to '${CURDIR}/${PG_COPY_DATA}/${*}.copy'"
	touch $@

postgres/%.load: ${PG_COPY_DATA}/%.copy ${PG_SCHEMA_DATA}/%.sql ## Load table with pgloader
	${PG_LOADER_VARS} pgloader ./postgres/table.load

.PHONY: help
help:
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
