# @probable-futures/mapbox-tilesets

This package contains the code for validating mapbox vector tiles against Woodwell data (the original data).

## Environment Secrets

`MAPBOX_ACCESS_TOKEN` is required by this package to access the required tileset and fetch it from mapbox. Make sure to set it inside `mapbox-tilesets/.env`

## Running the App

Make sure to fill the required configurations [here](tests/utils/configs.ts). This includes specifying the `id` of the dataset to validate, the tile coordinates and the method to use during validation (read below the different ways we use for validation).

To start the app, first you need to run `yarn install`, and then run `yarn dev` inside `mapbox-tilesets` directory.

## Techincal notes

The app consists of two ways to validate the tiles:

#### 1. Using [vtquery](https://github.com/mapbox/vtquery):

Vtquery is used to get the closest features from a longitude/latitude in a set of vector tile buffers. This way of validation is slow since it works by searching for each point in the tileset and then getting the features at this point. Below are the setps used during this process:

- Use [mapbox-sdk](https://github.com/mapbox/mapbox-sdk-js) to fetch and write the tileset to a file.
- Use [tilebelt](https://github.com/mapbox/tilebelt) to get the bounding box of the tileset.
- Parse and read the CSV file (Woodwell data). Skip all points that fall outside the bounding box that we got in the step above.
- For every point in the CSV file that belongs to the bounding box, call `vtquery` to get the features at this point.
- Compare the data in the CSV row with the feature's data obtained from calling `vtquery`
- Save all rows that does not match to log at the end of the process.

#### 2. Parse through all features in every layer in the VT (Without using vtquery):

This is a much faster way for validation, and it does not rely on vtquery. It works by parsing through all features in all layers in the vector tile. Below are the steps used during this process:

- Use [mapbox-sdk](https://github.com/mapbox/mapbox-sdk-js) to fetch and write the tileset to a file.
- Read the tileset data and parse it to a [VectorTile](https://github.com/mapbox/vector-tile-js).
- Loop through all the features in all the layers in the VectorTile
- Construct a map object that maps each latitude to all points at this latitude.
- Calculate the average of all data at a specific latitude.

Now do the same for the CSV file:

- Parse and read the CSV file (Woodwell data).
- Loop through all the rows in the CSV file
- Construct a map object that maps each latitude to all points at this latitude
- Calculate the average of all data at a specific latitude
- Finally, compare the data obtained upon parsing both the vector tile and the CSV files at each latitude.
