# Hacking NetCDF into Postgres

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

## What is this?



It takes a config file describing REMO NetCDF files and loads them into Postgres

```
psql probable_futures -f temp.sql

python pfimport.py --dbuser ford --dbpassword ford --load-coordinates --mutate

python pfimport.py --dbuser ford --dbpassword ford --load-cdfs --mutate


```

## The rest of the docs have not been edited


## How do I use it?

- Clone it from github
- Run `./download.sh` to download all the CDF files that were present as off last weekend. You may need to auth through Google Cloud using the `gcloud` tool (`gcloud init`). This uses the `gsutil` tool. (This all is part of the [Google Cloud SDK](https://cloud.google.com/sdk/docs))
- Get a working python3 environment (see below)
- Tweak your database (see below)

## What's going on?
Rho built a relatively robust framework that looks for changed files in Google Cloud buckets, downloads them, and makes them available via an API, at which point Postlight can fetch that data and store it in Postgres. It's designed to have very few humans in the loop.

It made sense to do this at the time but now it introduces some failure points, esp. around who maintains what. It's also a lot of infrastructure at the scale where we ended up; you're looking at 38 files today that change periodically, but this solution would scale to thousands changing daily. There's a long time between now and that future state.

The "hard part" of the Rho code is mostly around the piping for that infrastructure, not around the data.  The data is a NetCDF export; that's handled by a simple pipeline that's of this form:

- Load NetCDF from file using `xarray` module.
- Transform the `pandas` dataframe object.
- Convert all pandas `nan`s to python `None` type
- Convert dataframe to records and list
- Save the metadata to the database if we've never seen that dataset before.
- Step through each resulting row and save it to the database.

I wrote this in Python because I wanted to be as close to the Rho logic as possible. However there's just not that much logic around the conversion itself. You load the NetCDF and convert it to arrays, then save that to the database. There are NetCDF libraries in JavaScript too, although xarray in Python is as close to a "standard" for the geo world as you'll get.

`xarray` and NetCDF have conventions (or settings) about the precision at which they display floating-point numbers. When you convert out you lose that precision and have a raw float to work with. By modifying the `pf_climate_data` table columns that represent PF data to be numbers of form `NUMERIC(4,1)` everything basically does what you'd expect: it handles values from -999.9 to 999.9 and returns them at that level of precision.


## TODO Get a working environment

```
$ brew install python3
$ pip3 install pipenv
$ pipenv install
$ pipenv shell
```

That should just work, but if it doesn't let me help.

## TODO Download

To download all the files in the Google dir
```
$ ./download.sh
```

You may neet to install `gcloud` and `gsutil`

## TODO Run the importer
```
(pfpro-loader) $ python pfimport.py
# Currently breaks, needs database password

(pfpro-loader) $ python pfimport.py --help
# Lists help

(pfpro-loader) $ python pfimport.py --pattern="data/*.nc" --dbuser ford --dbpassword ford
# Does a dry run, spits out some errors for files, 
# converts NetCDF files to in-memory structures (which
# takes a while for REMO files.

(pfpro-loader) $ python pfimport.py --mutate=True --dbuser ford --dbpassword ford --pattern="data/*.nc"
# This will write to the database 
# and let me be clear it will mess
# your stuff up. 

```

You can watch the terminal log for errors -- some data [at least one file] has weird shapes so we skip it.

The CMIP5 files load quickly. The REMO files take about 2 minutes each. So it loads the first set quickly, then slows way down.

# TODOs
- error catching on arguments (i.e. needs db password)
- ability to pass glob as argument so that you can work on/load/debug one file at a time
- any kind of validation at all
- figure out what's weird about files
- God help us it's hard to get a working Python environment, maybe dockerize
- Can speed up the DB a lot with batches.
