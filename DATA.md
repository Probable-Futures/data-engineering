# Data-Related S3 Buckets

## global-pf-data-engineering bucket

This bucket contains climate data in different forms and structured across multiple folders

- `climate-data-full-model-raw/`: This forlder contains the raw climate data as collected by the climate models and shared with us by the data scientists at woodwell. All files in this folder are in a form of CSV. The naming convention we follow is `var-{nameOfTheVariable}_dom-{DOMAIN}_wl-{valueOfTheWarmingScenario}_tile-{tileNumber}.csv`
- `climate-data-full-model-raw-parquet/`: This folder contains the same data as in climate-data-full-model-raw/ but in parquet format. This data was transformed from CSV to parquet to optimize for faster querying and reduced storage size. We used a custom ETL job in glue to make this transformation
- `climate-data-geojson/`: This folder contains the data about each dataset in geojson format. These files are strucutured inside folders based on the version of the data. These json files are created during the map creation process as described in the [README](/README.md) file.
- `climate-data/`: This folder contains the processed climate data received from woodwell. This contains the datasets for each map in NetCDF format. The scientists has already processed the raw data and calculated the required statistics before it with us. There are multiple versions of the data stored here. Each version is stored inside its own folder. The `mosaicked` folder contains the actual netcdf files we use to create the maps in each version. We use the code in the data engineering repo to parse the data, save it in postgres and finally create and host visual maps in Mapbox. Check the full process here [README](/README.md). The `mosaicked_csv`, is another format of the same data but in CSV format. This is used only used by the data-engineering team for testing and validation purposes, check the [mapbox-tileset-validation](/mapbox-tileset-validation/README.md) for more details.
- `climate-data-with-all-stats/`: This is an experimental folder. It is similar to the climate-data/ folder but contains more statistics. For instance, the data in the climate-data folder contains 3 values for each location: mean or median, 5th percentile and 95th percentile. However, the data in this folder contains more percentiles 0 to 100. This folder is not used in production yet, and was just an experiment. In order to see this data visually, you can navigate to the PF Factbook at factbook.probablefutures.org, and check the "Likelihood chart" under each map.
- `development/, staging/, production/`: These folders contain the data exports from the respective environments' databases. Each folder contains multiple CSV files representing different tables in the database. These files can be used to seed the databases when setting up new environments or refreshing existing ones. Additionally, the data under copies/geo-places/ contains geographical data about places used in the PF Pro application. We've added it to enable users to download map data specific to certain places. Check `https://pro.probablefutures.org/dashboard/climate-data` for more details about how these places are used in the application. Note that staging is not actively used at the moment. The folder climate-data-csvs-with-coordinates/ contains CSV files where each file includes all locations with their respective latitude, longitude, cell and climate data statistics. These files are exported from the database by the postgres function `pf_hidden.export_dataset_statistics_with_coordinates`. 
- `glue/`: contains the glue jobs scripts we use to transform the raw data to parquet. 
- `local/`: not used anymore, but can stay for historical purposes.

## production-partner-upload and development-partner-upload buckets

- For PF Pro users, the "uploads" folder contains the files the users upload to the platform. Normally these files are CSV or GeoJSON files containing custom locations the users want to visualize the climate data on. 
The files that get uploaded here are processed and enriched and then stored in the respective user's S3 folder name by their user id.

Additionally, these buckets contain the following folder:

- `images`: normally we store screenshots of the map from the PF Pro platform taken automatically after a user creates a project and uploads their data on top of the climate data map.
- `samples`: contains sample datasets that new users can use to test the platform before uploading their own data.
- `climate-data`: contains data in different formats that gets stored when the user request climate data donwloads from the platform (e.g. CSV, GeoJSON, NetCDF). Note that `full-data-netcdf/` and `full-data/` data is copied from the global-pf-data-engineering bucket, while the other formats are created on-demand when the user requests them.
