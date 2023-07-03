# Probable Futures Data Engineering

This repository contains all the tools needed to import datasets and create maps. It consists of three main projects:

- [Makefile project](Makefile): contains the scripts needed to download datasets and transform/export them from the database
- [Loader](netcdfs/import): loads [netCDF](https://www.unidata.ucar.edu/software/netcdf/) files into PostgreSQL database
- [Vector-tiles](vector-tiles): contains the scripts needed to create/publish tilesets using [MTS](https://www.mapbox.com/mts) and create maps out of them.

## Getting Started

First, ensure that you have GNU Make installed, by running `brew install make`. Next, copy the `env.example` to `env` and fill in the secrets. Then, install the dependencies with `gmake install`.

## Downloading Datasets

To download all datasets from Woodwell Google Cloud Platform (GCP) bucket, run `gmake sync-woodwell-to-local`. This command uses [rclone](https://rclone.org/you) to sync the netCDF files in the bucket to `data/woodwell`. The easiest way to install it is by running `brew install rclone`. You will need to authenticate `rclone` with Google. You can find an example config file [here](conf/rclone.conf).

The GCP bucket link, [wcdi_production](https://console.cloud.google.com/storage/browser/wcdi_production), contains folders for each volume (such as `heat_module` and `water_module`). Each of these module folders contain folders to organize the dataset netCDF files by the type of climate models that Woodwell used to create them. For example, the RCM datasets that use the RegCM plus REMO ensemble of models are in a folder called `rcm_regcm_remo`.

All of the datasets and the maps we create from the datasets come from netCDF files containing latitude and longitude gridded point data with global coverage, excluding oceans except for areas near the coast and in most cases excluding polar regions. There are two resolutions of datasets that we use: Regionial Climate Model (RCM) and Global Circulation Model (GCM). The regional climate models we use are RegCM and REMO. They have a resolution of approximately 0.22° latitude and longitude (~25km) squared so they have many more data points and are much larger files than the GCM models, which have a resolution of about 2.5° latitude and longitude. The RCM maps are the maps we primarily use because they offer users a much higher resolution which tends to be more useful for most people who use the Probable Futures maps.

## Importing a Dataset

To import a dataset to your local PostgreSQL database, make sure first you set up the loader locally by following the instructions [here](netcdfs/import/README.md). Note: you can skip `Google Cloud SDK` section, if you went though the steps of downloading datasets above.

Then, you should be to run the following commands to import a dataset:

```
cd netcdfs/import
poetry shell
python pfimport.py --mutate --dbname probable_futures --dbuser postgres --dbpassword postgres --load-one-cdf $DATASET_ID
```

## Creating Tilesets & Maps

First, export the dataset that you want to create map for as geojson, by running `gmake data/mapbox/mts/$DATASET_ID.geojsonld`.
This will use `ogr2ogr` to fetch the specified dataset and save it to `data/mapbox/mts/`.

Then, add a new entry for it in the list of datasets in [createTilesets.ts](vector-tiles/createTilesets.ts). Make sure to comment out the datasets that you don't want to create maps for, otherwise old tilesets will be replaced by new ones.

Then, run the following commands:

```
cd vector-tiles
export MAPBOX_ACCESS_TOKEN='<MAPBOX_ACCESS_TOKEN>'
npm run createTilesets
```

This script will create/publish the tilesets and then creates new map styles out of them. You can inspect the newly created tilesets in [Mapbox Tilesets page](https://studio.mapbox.com/tilesets/). Make sure there are no errors in `Job history`:

![Mapbox Tileset Page](https://user-images.githubusercontent.com/23698181/150998697-8be12e1a-35a9-4ecb-af27-46de7f15ae49.png)

## Generating Map Styles

The script allows generating Map Styles as Json files. We usually share those in our public Github repo "Probable-Futures/docs".

There are two ways you can generate the styles:

- generateStylesSync: this function reads the style.json file in the directory and overrides its tileset sources and the layers paint properties based on what is defined inside the DATASETS array in the config.ts file. Before using this function, review the DATASETS array, and make sure, that for each map, all properties including colors and bins are up to date.

- generateStylesAsync: instead of creating the styles locally, this function connects to the PF mapbox account and fetches the styles remotely. After that we map each map style to its corresponding dataset and save them as json files.

After choosing which function to use, run the following commands:

```
cd vector-tiles
export MAPBOX_ACCESS_TOKEN='<MAPBOX_ACCESS_TOKEN>'
npm run generate-styles --generate-method sync
```

Note: `generate-method` param can be "sync" or "async" depending on the function you choose. Default is "async".

## Resources

- [What the Tile?](https://labs.mapbox.com/what-the-tile/)
- [Official Docs](https://docs.mapbox.com/mapbox-tiling-service/guides/)
- [Recipe Specification](https://docs.mapbox.com/mapbox-tiling-service/reference/)
- [Style Specification](https://docs.mapbox.com/mapbox-gl-js/style-spec/)
- [Vector Tiles Specification](https://docs.mapbox.com/vector-tiles/specification/)
- [GDAL/Ogr2Ogr Docs](https://gdal.org/)
