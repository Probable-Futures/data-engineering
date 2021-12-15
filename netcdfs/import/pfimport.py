from geoalchemy2 import Geometry
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from hashlib import md5
from pandas import Timedelta
import numpy
from numpy import format_float_positional, array


from pprint import pprint
import click
from rich.progress import Progress
from rich import print
from tqdm.contrib.concurrent import process_map
from oyaml import safe_load
import itertools

"""
CDF is a hierarchical format that allows you to have lots of
dimensions to your data. This does the bare minimum to convert CDF
files from Woodwell into a format that can go into the Probable
Futures database schema.

"""

# Defining functions in the global scope allows us to use
# multiprocessing to churn through records, which speeds import up
# quite a bit. So these functions are up top.

# EWKT is wild but basically it's POINT(X Y), where X and Y are
# arbitrary precision numbers with signed negative but unsigned
# positive and have no trailing zeroes. The decimal formatting is
# key and if PF gives us data with 5 degrees of precision we'll
# need to revisit this. The {:.4g} says turn the float into a
# numeral with precision 4 and the 'g' gets rid of trailing
# zeroes. So -179.0 becomes -179 while 20.1 is unchanged.


class NoMatchingUnitError(Exception):
    def __init__(self, unit):
        self.unit = unit


class NoMatchingGridError(Exception):
    def __init__(self, grid):
        self.grid = grid


class NoDatasetWithThatIDError(Exception):
    def __init__(self, ident):
        self.ident = ident


def to_hash(grid, lon, lat):

    """Create a hash of values to connect this value to the coordinate
    table."""
    s = ""
    if grid == "GCM":
        s = "{}SRID=4326;POINT({:.2f} {:.2f})".format(grid, lon, lat)
    elif grid == "RCM":
        s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(grid, lon, lat)
    else:
        raise NoMatchingUnitError(grid)
    hashed = md5(s.encode()).hexdigest()

    return hashed


# This should be the most obvious, blatant, unclever code possible.


def stat_fmt(pandas_value, unit):

    if unit == "days":
        # netCDF internal format: Days as float
        #
        # typical value: 12.0
        #
        # expected database value: 12.0
        #
        # desired precision, scale: 3,0 (i.e. an int, max 366)
        #
        # strategy: these emerge as simple floats with
        # precision 1, and the mantissa is always 0,
        # so we turn them into ints
        #
        # >>> int(28.0)
        # 28
        days_int = int(pandas_value)
        return days_int

    elif unit == "°C" or unit == "likelihood":
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

    elif unit == "cm":
        # netCDF internal format: float
        #
        # typical value: 1912.9
        #
        # expected database value: 1912.9
        #
        # desired precision, scale: 4,0 (i.e. an int, max 9999.9)
        #
        # strategy: pass them right on through
        #
        # >>> int(28.0)
        # 28
        cm = pandas_value
        return cm

    elif unit == "percent" or unit == "likelihood":
        # netCDF internal format: float
        #
        # typical value: 12.9
        #
        # expected database value: 12.9
        #
        # desired precision, scale: 4,0 (i.e. an int, min -999.9, max 999.9)
        #
        # strategy: these emerge as simple floats and work essentially as you'd
        # expect percentages to work.
        #
        percent = pandas_value
        return percent

    # If we have a unit we don't recognize that's a fatal error
    raise NoMatchingUnitError(unit)


def to_cmip_stats(row):
    """Make a stat from the output of our dataframe."""
    (
        lon,
        lat,
        deg_baseline,
        deg_1,
        deg_1_5,
        deg_2,
        deg_2_5,
        deg_3,
        dataset_id,
        grid,
        unit,
    ) = row
    hashed = to_hash(grid, lon, lat)
    scenarios = ["0.5", "1.0", "1.5", "2.0", "2.5", "3.0"]
    stats = [deg_baseline, deg_1, deg_1_5, deg_2, deg_2_5, deg_3]

    def to_stats(i, scenario):
        new_mean = stat_fmt(stats[i], unit)
        stat_dict = {
            "dataset_id": int(
                dataset_id
            ),  # Because we inserted it into the numpy array
            "coordinate_hash": hashed,
            "warming_scenario": str(scenario),
            "pctl10": None,
            "pctl90": None,
            "mean": new_mean,
        }
        return stat_dict

    new_stats = [to_stats(i, scenario) for i, scenario in enumerate(scenarios)]
    return new_stats


def to_remo_stat(row):

    """Make a stat from the output of our dataframe."""
    lon, lat, time, mean, pctl10, pctl90, dataset_id, grid, unit = row
    hashed = to_hash(grid, lon, lat)

    new_pctl10 = stat_fmt(pctl10, unit)
    new_mean = stat_fmt(mean, unit)
    new_pctl90 = stat_fmt(pctl90, unit)

    stat_dict = {
        "dataset_id": int(dataset_id),  # Because we inserted it into the numpy array
        "coordinate_hash": hashed,
        "warming_scenario": str(time),
        "pctl10": new_pctl10,
        "pctl90": new_pctl90,
        "mean": new_mean,
    }
    return stat_dict


# The command starts here
@click.command()
@click.option(
    "--load-coordinates",
    is_flag=True,
    default=False,
    help="Insert coordinates (lon/lats). You need to do this first, after database initialization; if you don't, CDFs won't load because they refer to this table. It won't work after you've loaded other data because to delete it would violate referential integrity; you likely need to reset the database by dropping tables.",
)
@click.option(
    "--load-one-cdf",
    is_flag=False,
    nargs=1,
    type=int,
    default=None,
    help='Insert one CDF by dataset ID, i.e. 20104. That integer ID must appear in "conf.yaml"',
)
@click.option(
    "--load-cdfs",
    is_flag=True,
    default=False,
    help='Insert CDFs as listed in "conf.yaml"',
)
@click.option(
    "--mutate",
    is_flag=True,
    default=False,
    help="This script will only write to the database if this variable is set. Each CDF is loaded within an atomic transaction.",
)
@click.option(
    "--conf", default="conf.yaml", help='YAML config file, default "conf.yaml"'
)
@click.option(
    "--dbhost",
    default="localhost",
    help='Postgresql host/server name, default "localhost"',
)
@click.option(
    "--dbname",
    default="probable_futures",
    help='Postgresql database name, default "probable_futures"',
)
@click.option("--dbuser", nargs=1, help="Postgresql username")
@click.option("--dbpassword", nargs=1, help="Postgresql password")
@click.option(
    "--sample-data",
    is_flag=True,
    default=False,
    help="Load just 100 rows per dataset for testing",
)
@click.option(
    "--log-sql",
    is_flag=True,
    default=False,
    help="Log SQLAlchemy SQL calls to screen for debugging",
)
def __main__(
    mutate,
    conf,
    dbhost,
    dbname,
    dbuser,
    dbpassword,
    load_coordinates,
    load_one_cdf,
    load_cdfs,
    log_sql,
    sample_data,
):

    # This is boilerplate SQLAlchemy introspection; it makes classes
    # that behave about how you'd expect for the tables in the current
    # schema. These objects aren't smart about PostGIS but that's
    # okay.

    engine = None
    try:
        engine = create_engine(
            "postgresql://" + dbuser + ":" + dbpassword + "@" + dbhost + "/" + dbname,
            echo=log_sql,
        )
    except:
        print(
            "[Error] Was not able to log in to Postgres. Quitting. Did you provide the right --dbuser and --dbpassword?"
        )
        exit(0)

    metadata = MetaData(schema="pf_public")
    metadata.reflect(engine)
    Base = automap_base(metadata=metadata)
    Base.prepare()

    Dataset = Base.classes.pf_datasets
    Coordinates = Base.classes.pf_grid_coordinates
    StatisticalVariableName = Base.classes.pf_statistical_variable_names
    DatasetStatistic = Base.classes.pf_dataset_statistics

    Session = sessionmaker(bind=engine)

    # Load YAML file and do some very basic checking around provided conditions.
    conf = safe_load(open(conf))

    if load_coordinates is False and load_cdfs is False and load_one_cdf is None:
        print(
            "[Error] You need to provide one of '--load-coordinates' or '--load-cdfs or --load-one-cdf [DATASET_ID]'"
        )
        exit(0)

    if mutate is False:
        print("[Notice] Since --mutate was not invoked I will not change the database")
    else:
        print("[Notice] Since --mutate was invoked I *WILL* change the database")

    def save_cdf(cdf, stats):
        with Session() as session:
            print("[Notice] Deleting old data from {}".format(cdf["dataset"]))
            session.query(DatasetStatistic).filter(
                DatasetStatistic.dataset_id == cdf["dataset"]
            ).delete()

            print("[Notice] Deleting the DataSet record.")
            session.query(Dataset).filter(Dataset.id == cdf["dataset"]).delete()
            d = Dataset(
                id=cdf["dataset"],
                name=cdf["name"],
                slug=cdf["slug"],
                description=cdf["description"],
                category=cdf["category"],
                model=cdf["model"],
                unit=cdf["unit"],
            )
            print("[Notice] Adding dataset '{}'".format(cdf["dataset"]))
            session.add(d)

            # print("[Notice] Deleting, then adding variables".format(cdf["dataset"]))
            # session.query(StatisticalVariableName).filter(
            #     StatisticalVariableName.dataset_id == cdf["dataset"]
            # ).delete()

            # vns = []
            # for v in cdf["variables"]:
            #     vn = StatisticalVariableName(
            #         slug=v["name"],
            #         name=v["long_name"],
            #         dataset_id=cdf["dataset"],
            #         description=None,
            #     )
            #     print("[Notice] Adding variable '{}' [{}]".format(v["name"], vn))
            #     vns.append(vn)

            # session.add_all(vns)
            print("[Notice] Inserting {:,} stats".format(len(stats)))
            task_stats = progress.add_task(
                "Loading stats for {}".format(cdf["dataset"]), total=len(stats)
            )

            print("[Notice] Inserting in the database.")
            for stat in stats:
                ds = DatasetStatistic(**stat)
                session.add(ds)
                progress.update(task_stats, advance=1)
            print("[Notice] Committing to the database.")
            session.commit()

    # We make a table of all possible coordinates and put them into
    # the database. The database will hash them and that will become
    # the key for future lookups.

    if load_coordinates is True:
        print("[Notice] Loading coordinates using data in the config file.")

        with Progress() as progress:
            with Session() as session:
                task_progress = progress.add_task(
                    "Loading coords", total=len(conf.get("grids"))
                )

                def to_record(coord, grid_name):
                    pt = "POINT({} {})".format(*coord)
                    return Coordinates(grid=grid_name, point=pt)

                for grid in conf["grids"]:
                    print("[Notice] Loading coordinates for {}.".format(grid["grid"]))
                    grid_name = grid["grid"]
                    coords = list(itertools.product(grid["lon"], grid["lat"]))
                    records = [to_record(coord, grid_name) for coord in coords]

                    if mutate:
                        session.query(Coordinates).filter(
                            Coordinates.grid == grid_name
                        ).delete()
                        session.bulk_save_objects(records)
                        session.commit()
                    progress.update(task_progress, advance=1)

    if load_cdfs is True or load_one_cdf is not None:
        with Progress() as progress:
            # Add units
            task_loading = progress.add_task(
                "Loading NetCDF files", total=len(conf["datasets"])
            )

            datasets = conf.get("datasets")
            if load_one_cdf is not None:
                datasets = [x for x in datasets if x["dataset"] == int(load_one_cdf)]
                if len(datasets) < 1:
                    print("I could not find a dataset with ID {}".format(load_one_cdf))
                    raise NoDatasetWithThatIDError(load_one_cdf)

            for cdf in datasets:
                print(
                    "[Notice] Loading and converting CDF file {}".format(
                        cdf.get("filename")
                    )
                )
                ds = xarray.open_dataset(cdf.get("filename"))

                def make_stats():
                    print("[Notice] Converting CDF file to list.")
                    # This is really where most of the work is
                    # happening. We take our xarray dataset, drop all
                    # the Na* values, add a few columns using our
                    # existing data (this is verrrrry fast in a
                    # dataframe), and finally make it into records(),
                    # i.e. a list. Worth noting that the values are
                    # all still pandas data types, not native Python,
                    # so they need some love to make them good for
                    # SQLAlchemy.
                    df = (
                        ds.to_dataframe()
                        .dropna()
                        .assign(
                            dataset_id=cdf["dataset"],
                            grid=cdf["grid"],
                            unit=cdf["unit"],
                        )
                    )
                    if sample_data:
                        df = df.head(100)

                    recs = df.to_records()

                    print(
                        "[Notice] Using lots of processors to convert data to SQL-friendly data."
                    )

                    if cdf["model"] == "GCM, CMIP5":
                        stats = process_map(to_cmip_stats, recs, chunksize=10000)
                        flattened = array(stats).flatten()
                        return flattened
                    elif (
                        cdf["model"] == "global RegCM and REMO"
                        or cdf["model"] == "global REMO"
                    ):
                        stats = process_map(to_remo_stat, recs, chunksize=10000)
                        return stats

                    return None

                stats = make_stats()

                # Finally, let's do the real work and step through
                # REMO files
                if mutate:
                    save_cdf(cdf, stats)
                progress.update(task_loading, advance=1)


if __name__ == "__main__":
    __main__()
