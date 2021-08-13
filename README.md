# PFPro Loader

## What is this?

This translates [netCDF](https://www.unidata.ucar.edu/software/netcdf/) files into a somewhat denormalized form of SQL that allows for fast, easy bulk lookups of lat/longs so that they any geographic dataset can be enriched with Probable Futures data about warming scenarios. netCDFs are essentially super-normalized geosciences data where you have different variables (lat, long, day) and then data or arrays at each point.

What we're doing--converting netCDF to SQL--is unusual for the geosciences, because in general netCDF and the associated tools are appropriate for preparing diagrams for publication, or for exploration of datasets. There's some prior art but not as much as you might expect. The world of "standard API development" and "standard geosciences data analysis" are quite different.

## Important cultural note

We are working with scientific data and the standards around precision are extremely well-defined, and we need to meet the standards of the science.

We are using the `xarray` module to load data. Then we convert `xarray` DataSets to `pandas` DataFrames; we export these into SQL. In development, the number one challenge we faced was type conversion as we went from netCDF types to pandas types to native Python types to SQL types. Floats were exposed at different levels of precision, TimeDeltas became huge integers, and so forth.

There's a section below, entitled [Datatypes and conversion](#Datatypes and conversions), which serves as a kind of pseudocontract between Postlight and Probable Futures/Woodwell. The basic idea is that:

1) We will be on the lookout for new *units* in data. Degrees celsius, total days, percentage, are examples of units.
2) When we find a new kind of unit, we will document the unit in our code and be extremely explicit about the type conversion.
3) We'll share that with Probable Futures and Woodwell for their review.

In reality this isn't a ton of work, it's just way more explicit than we usually are, in the interest of creating code that is observable and can be validated.

## Instructions for use

### What's in the repo?

- `pfimport.py` creates the coordinates table via `--load-coordinates` and loads CDFs with `--load-cdfs`.
- `util/` is miscellany that was used to build things and create development environments.
- `util/temp.sql` is the SQL you need to bootstrap. In production this is handled by postgraphile.
- `bin/` contains scripts that are useful; currently there's only a downloader script for CDF data.
- `pyproject.toml` and `poetry.lock` files, which are used by the poetry environment manager.

### Setup

#### Postgres

You need a Postgresql 13+ instance you can target to store the data we produce. 

If you're testing this out on your local machine you should also install postgis (`brew install postgis`).

- Create a database called `probable_futures`.
- Run `psql probable_futures -f util/temp.sql`

That should give you all the database you need.

#### Google Cloud SDK

You need the Google Cloud SDK to download data. Read the [installation instructions](https://cloud.google.com/sdk/docs/install); basically you need to install it and run `gcloud init` to authenticate. You won't be able to download data unless you're approved; talk to an admin at Probable Futures to get the requisite credentials.

#### Python

You need a working Python 3 environment. We use poetry as a package manager. On a typical mac you can try this:

```
brew install python
pip3 install poetry

git clone [pfpro-loader github repo]
cd pfpro-loader
poetry install
poetry shell
```

There's a non-trivial chance you will be in an environment in which everything will work.

### Running the Process

We have one script that orchestrates everything, called `pfimport.py`. Some care has been taken to make it into a robust, easily-understood command line application, and it's self-documenting through `--help`.

```
$ python pfimport.py --help
Usage: pfimport.py [OPTIONS]

Options:
  --load-coordinates      Insert coordinates (lon/lats). You need to do this
                          first, after database initialization; if you don't,
                          CDFs won't load because they refer to this table.
  --load-one-cdf INTEGER  Insert one CDF by dataset ID, i.e. 20104. That
                          integer ID must appear in "conf.yaml"
  --load-cdfs             Insert CDFs as listed in "conf.yaml"
  --mutate                This script will only write to the database if this
                          variable is set. Each CDF is loaded within an atomic
                          transaction.
  --conf TEXT             YAML config file, default "conf.yaml"
  --dbhost TEXT           Postgresql host/server name, default "localhost"
  --dbname TEXT           Postgresql database name, default "probable_futures"
  --dbuser TEXT           Postgresql username
  --dbpassword TEXT       Postgresql password
  --sample-data           Load just 10,000 rows per dataset for testing
  --log-sql               Log SQLAlchemy SQL calls to screen for debugging
  --help                  Show this message and exit.
```

### Building the dataset from scratch

```sh
$ psql
ford=# create database probable_futures;
CREATE DATABASE
ford=# quit

# You can run this next command as often as you like, but every time you do it blows away the coordinates table so you need to start over.
$ pgsql probable_futures -f util/temp.sql

# Log into Google cloud
$ gcloud-sdk init

$ ./bin/download.sh

$ python pfimport.py --mutate --dbname probable_futures --dbuser ford --dbpassword ford --load-coordinates

[output elided]

$ python pfimport.py --mutate --dbname probable_futures --dbuser ford --dbpassword ford --load-cdfs

[output elided]
```

### Loading a new dataset

First, add the dataset to `conf.yaml`

Second, load it using the `--load-one-cdf` option.

```
$ python pfimport.py --mutate --dbname probable_futures --dbuser ford --dbpassword ford --load-one-cdf 20101

[output elided]
```


## Datatypes and conversions

### Conversion risks

Our goal is to take the multi-axis data inside a netCDF and to
"flatten" it into the relational model. This makes it easier to treat
climate data as we'd treat any data we wanted to make accessible on
the web, via web APIs.

While it's possible to just make a netCDF file available online as
geoJSON, they get big, then bigger, then ridiculously big, and there
are many of them, and there's no single well-understood way to create
a web API to access them.

So we should use...a database; in particular, we should use PostGIS on
top of Postgres, which truly is widely understood. This too is a
little novel, but there is [helpful prior art from
2016](https://newtraell.cs.uchicago.edu/files/ms_paper/sthaler.pdf),
and PostGIS has strong opinions about what constitutes a coordinate
system.

At the same time it introduces points of possible failure, namely:

- It is easy to mix up lats and lons and the PostgGIS `POINT` geometry
  type doesn't yell at you if you do it wrong, but wraps around the
  coordinate system. But ultimately this comes down to keeping track
  of your variables, and it breaks catastrophically, which is
  good--catastrophic breakage is easy to find.
- There are countless, subtle opportunities for failure in type
  conversion because netCDF represents values as floats and xarray
  (the python multidimensional array library that is the standard for
  netCDF loading) displays them at sensible levels of precision when
  one is exploring the data, but converts them to floats when one is
  exporting.
- Different data types (i.e. units) expect different precision/scales;
  a number of days is obviously an integer; a temperature increase
  could be 2.5.

### Our pipeline

This is the pipeline we're currently using. It's open to revision but
the goal is to create a transparent process that documents how we are
converting data from CDF-native types into Postgres-native types, in
order to avoid a lot of long Slack conversations about data types.

1. Load Woodwell-created netCDF (metadata and units described by the
   `conf.yaml` file) into memory using python `xarray`
2. Export the netCDF to 2D pandas dataframe using `.to_dataframe()`
3. Add columns and cut out `NA` (`Null`) values
4. **Step through each lat/lon combination and prepare the data values
   for insertion into the database**
5. Save each row to Postgres database

Steps 4 and 5 are where the greatest opportunity for error come in,
due to floating point being floating point. We address this in three
ways:

1. We explicitly name the "units" for each dataset. Right now we have
   two "units"; they are: `days` and `temp_C`. We put them in our
   config file.
2. We write very blatant type conversion code in exactly one place
   that is easy to share and validate. (See below.)
3. We set our PostgreSQL data type to `numeric(4,1)` meaning four
   digits of precisions and scale of 1, which means all values must be
   within [-9999.9 ... 9999.9]. This is imperfect because it doesn't
   correlate exactly with the precision or scale of the input data,
   but it's very flexible and lets us have one table for all CDF data
   instead of one table per CDF.

In general for type conversion we'll:

1. Attempt to do exactly what the CDF tells us to do; i.e. we'll open
   the CDF in Panoply and determine how the CDF is displaying values,
   then mirror that in Python.
2. Then we'll ask Woodwell if that looks right.

In every case we should have a strategy for conversion, i.e. don't
just wrap something in `float` and assume it works. See how it's
documented below.

When there is a new data type (say "precipitation in mm per year")
we'll add the CDF to our conf file and set the unit (`precip_mm`),
then write a conversion function for that unit. We'll share that
conversion function with sample conversion data with our partners for
feedback.


### Sample YAML
```yaml
datasets:
  - dataset: 20104
    filename: data/wcdi_production/heat_module/rcm_globalremo/globalREMO_tasmax_days_ge32.nc
    slug: globalREMO_tasmax_days_ge32
    dimensions: [time, lat, lon]
    name: Number of days maximum temperature above 32°C (90°F)
    description: ''
    category: increasing heat
    model: RCM, global REMO
    unit: days
    variables:
    - name: mean_days_above_32C_
      method: mean
      map_to: null
      long_name: mean - number of days maximum temperature above 32°C (90°F)
    - name: pctl10_days_above_32C_
      method: pct10
      map_to: null
      long_name: 10th percentile - number of days maximum temperature above 32°C (90°F)
    - name: pctl90_days_above_32C_
      method: pct90
      map_to: null
      long_name: 90th percentile - number of days maximum temperature above 32°C (90°F)
```

### Type conversion code
```python

def stat_fmt(pandas_value, unit):

    if unit == "days":
        # netCDF internal format: Timedelta as float
        #
        # typical value: 172800000000000
        #
        # expected database value: 2.0
        #
        # desired precision, scale: 3,0 (i.e. an int)
        #
        # strategy: these come out of pandas in nanoseconds; we use
        #    pandas Timedelta(x).days to turn them back into integers
        #
        # >>> from pandas import Timedelta, i.e.
        # >>> Timedelta(24 * 60 * 60 * 1000000000 * 28).days
        # 28

        days_int = Timedelta(pandas_value).days
        return days_int

    elif unit == "temp_C":
        # netCDF internal format: float
        #
        # typical value: 28.00000011920928955078125
        #
        # expected database value: 28.0
        #
        # desired precision, scale: 4, 1
        #
        # strategy: use numpy's format_float_positional and convert it
        # to a string, which will go into Postgres fine.
        #
        # https://numpy.org/doc/stable/reference/generated/numpy.format_float_positional.html
        #
        # "Uses and assumes IEEE unbiased rounding. Uses the 'Dragon4'
        # algorithm."
        #
        # >>> from numpy import format_float_positional
        # >>> format_float_positional(28.00000011920928955078125, precision=1)
        # '28.0'

        formatted_value = format_float_positional(pandas_value, precision=1)
        return formatted_value

    # If we have a unit we don't recognize that's a fatal error
    raise NoMatchingUnitError(unit)
```

## See also:

- [Probable Futures Map & Data Process Detailed Documentation](https://docs.google.com/document/d/1WWrtJeQmJ53Wa7OjqiZ_xZWI2pHH39zJtSBaEHE_CIA/edit) by Peter Croce, in Google Docs
- [netCDF](https://www.unidata.ucar.edu/software/netcdf/) by UCAR.
- [xarray](http://xarray.pydata.org/en/stable/) docs
- [pandas dataframes](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html)



