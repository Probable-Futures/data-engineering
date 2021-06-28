# Hacking NetCDF into Postgres

## What is this?

It takes a dir of NetCDF files (currently `./data/`) and loads them into a Postgres database table of the form:

- dataset id
- lat
- long
- data pt [1..6]

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

I wrote this in Python because I wanted to be as close to the Rho logic as possible. However there's just not that much logic around the conversion itself. You load the NetCDF and convert it to arrays, then save that to the database. There are NetCDF libraries in JavaScript too, although xarray in Python is as close to a "standard" for the geo.

`xarray` and NetCDF have conventions (or settings) about the precision at which they display floating-point numbers. When you convert out you lose that precision and have a raw float to work with. By modifying the `pf_climate_data` table columns that represent PF data to be numbers of form `NUMERIC(4,1)` everything basically does what you'd expect: it handles values from -999.9 to 999.9 and returns them at that level of precision.


## TODO Get a working environment
```
$ brew install python3
$ pip3 install virtualenvwrapper
# you need virtualenv/pipenv, document that
$ mkvirtualenv pfpro-loader
$ workon pfpro-loader
$ pip install -f requirements.txt (or maybe pipenv)
```

## TODO Download

To download all the files in the Google dir
```
$ ./download.sh
```

## TODO Run the importer
```
(pfpro-loader) $ python pfimport.py --help
(pfpro-loader) $ python pfimport.py --help
(pfpro-loader) $ python pfimport.py --mutate=True --dbuser ford --dbpassword ford

```

Then watch terminal log for errors -- some data [at least one file] has weird shapes so we skip it.


# TODOs
- error catching on arguments (i.e. needs db password)
- ability to pass glob as argument so that you can work on/load/debug one file at a time
- any kind of validation at all
