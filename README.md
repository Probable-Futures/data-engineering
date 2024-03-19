# Probable Futures Data Engineering

This repository contains all the tools needed to import datasets and create maps. It consists of three main projects:

- [Makefile project](Makefile): contains the scripts needed to download datasets and transform/export them from the database
- [Loader](netcdfs/import): loads [netCDF](https://www.unidata.ucar.edu/software/netcdf/) files into PostgreSQL database
- [Vector-tiles](vector-tiles): contains the scripts needed to create/publish tilesets using [MTS](https://www.mapbox.com/mts) and create maps out of them.

## Getting Started

First, ensure that you have GNU Make installed, by running `brew install make`. Next, copy the `env.example` to `env` and fill in the secrets. Then, install the dependencies with `gmake install`.

## Downloading Datasets

Download all datasets from the AWS bucket `global-pf-data-engineering`. The bucket contains folders for different version of the datasets. Each folder contains folders for each volume (such as `heat_module` and `water_module`). These module folders contain the dataset netCDF files that Woodwell team members create.

All of the datasets and the maps we create from the datasets come from netCDF files containing latitude and longitude gridded point data with global coverage, excluding oceans except for areas near the coast and in most cases excluding polar regions. There are two resolutions of datasets that we use: Regionial Climate Model (RCM) and Global Circulation Model (GCM). The regional climate models we use are RegCM and REMO. They have a resolution of approximately 0.22° latitude and longitude (~25km) squared so they have many more data points and are much larger files than the GCM models, which have a resolution of about 2.5° latitude and longitude. The RCM maps are the maps we primarily use because they offer users a much higher resolution which tends to be more useful for most people who use the Probable Futures maps.

## Importing a Dataset

To import a dataset to your local PostgreSQL database, make sure first you set up the loader locally by following the instructions [here](netcdfs/import/README.md).

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

## Updating Existing Tilesets

You can update the tileset data without removing/recreating it. The tileset will keep using the same tileset id, so any map style referencing the tileset will stay functional. It works by uploading a new GeoJson source containing the new data, creating the tileset recipes and using them to update the tileset. You need to follow the below steps to update the tileset:

1. Create the new geojson file and make sure it is under `data/mapbox/mts` (Same as if you are creating a new map)
2. Choose the tileset you want to update inside `updateTilesets.ts`
3. Run the following commands:

```
cd vector-tiles
export MAPBOX_ACCESS_TOKEN='<MAPBOX_ACCESS_TOKEN>'
npm run update-tilesets
```

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

## Testing the tilesets

Refer to the README file inside the [mapbox-tileset-validation](/mapbox-tileset-validation/README.md) folder and read the instructions on how to validate the Mapbox vector tiles against the netCDF files (the original data from Woodwell).

## Post map creation or update

**After deploying a new map, here is what you need to do:**

- Export data from the database as CSV file and place [here](https://s3.console.aws.amazon.com/s3/buckets/global-pf-data-engineering?region=us-west-2&bucketType=general&prefix=production/postgres/copies/pf_public.pf_dataset_statistics/&showversions=false)

- Seed the dev and prod databases with the new map data
- Go to [this folder](https://github.com/Probable-Futures/docs/tree/main/mapStyles) in the docs github repo, and upload the map style of the new map (in json format) to the corresponding folder.
- Upload the netcdf file to the S3 bucket for both the dev and prod buckets. These maps are access by PF Pro users who are interested in downloading the data in all three formats: "csv", "geojson" and "netcdf". The location where this data should be placed within the dev environment can be found [here](https://s3.console.aws.amazon.com/s3/buckets/development-partner-upload-b557bb7?region=us-west-2&bucketType=general&prefix=climate-data/&showversions=false)
- Update the `pf_public.pf_maps.csv` and the `pf_public.pf_datasets.csv` files for each environment in the S3 bucket `global-pf-data-engineering`, eg. `global-pf-data-engineering/development/postgres/copies`.

## Resources

- [What the Tile?](https://labs.mapbox.com/what-the-tile/)
- [Official Docs](https://docs.mapbox.com/mapbox-tiling-service/guides/)
- [Recipe Specification](https://docs.mapbox.com/mapbox-tiling-service/reference/)
- [Style Specification](https://docs.mapbox.com/mapbox-gl-js/style-spec/)
- [Vector Tiles Specification](https://docs.mapbox.com/vector-tiles/specification/)
- [GDAL/Ogr2Ogr Docs](https://gdal.org/)
