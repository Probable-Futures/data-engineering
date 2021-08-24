SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:

include .env

# All data lives here
DATA_DIR := data
DATA_ENG_S3 := pf-s3:global-pf-data-engineering
S3_ENV := local

# Mirror of Woodwell GCP Bucket
WOODWELL_DATA := ${DATA_DIR}/woodwell
WOODWELL_GCP := woodwell-gcp:wcdi_production

# Directory for storing mapbox related data assets
MAPBOX_DATA := ${DATA_DIR}/mapbox
# Vector Tiles from Mapbox
MVT_DATA := ${MAPBOX_DATA}/mvt
# GeoJSON Sources for Mapbox Tiling Service
MTS_DATA := ${MAPBOX_DATA}/mts

PG_DATA := ${DATA_DIR}/postgres
PG_COPY_DATA := ${PG_DATA}/copies
PG_DUMP_DATA := ${PG_DATA}/dumps
PG_SCHEMA_DATA := ${PG_DATA}/schemas

PG_URL := pgsql://${PG_USER}:${PG_PASSWORD}@${PG_HOST}:${PG_PORT}/${PG_DBNAME}
PG_LOADERS = ./postgres/loaders
PG_LOADER_VARS = PG_URL=${PG_URL} LOAD_DIR=./${PG_COPY_DATA}

OGR2OGR := /usr/local/bin/ogr2ogr
OGR2OGR_PG_CONNECTION := PG:"host=${PG_HOST} user=${PG_USER} dbname=${PG_DBNAME} password=${PG_PASSWORD}"

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

data/mapbox/mts/%.geojsonld: ## Export GeoJSONSeq from Database
	mkdir -p data/mapbox/mts
	echo "Begining export of dataset ${*}"
	ogr2ogr -wrapdateline -f GeoJSONSeq $@ ${PG_CONNECTION} -sql "${EXPORT_QUERY}"
	echo "Dataset ${*} export complete.\n"
	touch $@

data/postgres/schemas/%.sql: ## Dump schema from Database
	mkdir -p data/postgres/schemas
	pg_dump ${PG_URL} --disable-triggers --clean --if-exists --schema-only --no-privileges --table '${*}' -f $@
	touch $@

data/postgres/copies/%.copy: ## Copy data from database table
	mkdir -p data/postgres/copies
	psql ${PG_URL} -e --command "copy ${*} to '${CURDIR}/${PG_COPY_DATA}/${*}.copy'"
	touch $@

.PHONY: pgloader-coordinates
pgloader-coordinates: ## Load coordinates with pgloader
	${PG_LOADER_VARS} pgloader ${PG_LOADERS}/pf_grid_coordinates.load

.PHONY: pgloader-datasets
pgloader-datasets: ## Load datasets with pgloader
	${PG_LOADER_VARS} pgloader ${PG_LOADERS}/pf_datasets.load

.PHONY: pgloader-stats
pgloader-stats: ## Load statistics with pgloader
	${PG_LOADER_VARS} pgloader ${PG_LOADERS}/pf_dataset_statistics.load

.PHONY: sync-woodwell-to-local
sync-woodwell-to-local: ## Sync Woodwell GCP bucket of NetCDFs to data/woodwell
	mkdir -p data/woodwell
	rclone sync -P ${WOODWELL_GCP} data/woodwell

.PHONY: sync-woodwell-to-s3
sync-woodwell-to-s3: ## Sync Woodwell GCP bucket to s3://global-pf-data-engineering/${S3_ENV}/woodwell
	rclone sync -P ${WOODWELL_GCP} ${DATA_ENG_S3}/${S3_ENV}/woodwell

.PHONY: sync-postgres-to-s3
sync-postgres-to-s3: ## Sync local postgres data to s3://global-pf-data-engineering/${S3_ENV}/postgres
	rclone sync -P data/postgres ${DATA_ENG_S3}/${S3_ENV}/postgres

.PHONY: sync-postgres-from-s3
sync-postgres-from-s3: ## Sync local postgres data from s3://global-pf-data-engineering/${S3_ENV}/postgres
	mkdir -p data/postgres
	rclone sync -P ${DATA_ENG_S3}/${S3_ENV}/postgres data/postgres

.PHONY: sync-mapbox-to-s3
sync-mapbox-to-s3: ## Sync local mapbox data to s3://global-pf-data-engineering/${S3_ENV}/mapbox
	rclone sync -P data/mapbox ${DATA_ENG_S3}/${S3_ENV}/mapbox

.PHONY: sync-mapbox-from-s3
sync-mapbox-from-s3: ## Sync local mapbox data from s3://global-pf-data-engineering/${S3_ENV}/mapbox
	mkdir -p data/mapbox
	rclone sync -P ${DATA_ENG_S3}/${S3_ENV}/mapbox data/mapbox


.PHONY: help
help:
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
