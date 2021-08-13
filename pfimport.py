from geoalchemy2 import Geometry
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from hashlib import md5
from pandas import Timedelta
from numpy import format_float_positional

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


def to_hash(model, lon, lat):

    """Create a hash of values to connect this value to the coordinate
    table."""

    s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(model, lon, lat)
    hashed = md5(s.encode()).hexdigest()
    return hashed


class NoMatchingUnitError(Exception):
    def __init__(self, unit):
        self.unit = unit

class NoDatasetWithThatIDError(Exception):
    def __init__(self, ident):
        self.ident = ident


# This should be the most obvious, blatant, unclever code possible.


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


def to_stat(row):

    """Make a stat from the output of our dataframe."""

    lon, lat, time, mean, pctl10, pctl90, dataset_id, model, unit = row
    hashed = to_hash(model, lon, lat)

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
    "--load-coordinates", is_flag=True, default=False, help="Insert coordinates (lon/lats). You need to do this first, after database initialization; if you don't, CDFs won't load because they refer to this table. It won't work after you've loaded other data because to delete it would violate referential integrity; you likely need to reset the database by dropping tables."
)
@click.option("--load-one-cdf", is_flag=False, nargs=1, type=int, default=None, help='Insert one CDF by dataset ID, i.e. 20104. That integer ID must appear in "conf.yaml"')
@click.option("--load-cdfs", is_flag=True, default=False, help='Insert CDFs as listed in "conf.yaml"')

@click.option(
    "--mutate", is_flag=True, default=False, help="This script will only write to the database if this variable is set. Each CDF is loaded within an atomic transaction."
)
@click.option("--conf", default="conf.yaml", help='YAML config file, default "conf.yaml"')
@click.option(
    "--dbhost", default="localhost", help='Postgresql host/server name, default "localhost"'
)
@click.option(
    "--dbname",
    default="probable_futures",
    help='Postgresql database name, default "probable_futures"',
)
@click.option("--dbuser", nargs=1, default="", help="Postgresql username")
@click.option("--dbpassword", nargs=1, default="", help="Postgresql password")
@click.option(
    "--sample-data",
    is_flag=True,
    default=False,
    help="Load just 10,000 rows per dataset for testing",
)
@click.option("--log-sql", is_flag=True, default=False, help="Log SQLAlchemy SQL calls to screen for debugging")
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
    Coordinates = Base.classes.pf_dataset_coordinates
    StatisticalVariableName = Base.classes.pf_statistical_variable_names
    DatasetStatistic = Base.classes.pf_dataset_statistics

    Session = sessionmaker(bind=engine)

    # Load YAML file and do some very basic checking around provided conditions.
    conf = safe_load(open(conf))

    if load_coordinates is False \
       and load_cdfs is False \
       and load_one_cdf is None:
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
                resolution=None,
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
                    "Loading coords", total=len(conf.get("models"))
                )

                for model in conf["models"]:
                    print("[Notice] Loading coordinates for {}.".format(model["model"]))
                    name = model["model"]
                    coords = list(itertools.product(model["lon"], model["lat"]))

                    if mutate:
                        session.query(Coordinates).filter(
                            Coordinates.model == name
                        ).delete()

                    def to_record(coord, name):
                        pt = "POINT({} {})".format(*coord)
                        return Coordinates(model=name, point=pt)

                    records = [to_record(coord, name) for coord in coords]
                    if mutate:
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
                print("[Notice] Loading and converting CDF file.")
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
                            model=cdf["model"],
                            unit=cdf["unit"],
                        )
                    )
                    if sample_data:
                        df = df.head(10000)

                    recs = df.to_records()

                    print(
                        "[Notice] Using lots of processors to convert data to SQL-friendly data."
                    )
                    stats = process_map(to_stat, recs, chunksize=10000)
                    return stats

                stats = make_stats()

                # Finally, let's do the real work and step through
                # REMO files
                if mutate:
                    save_cdf(cdf, stats)
                progress.update(task_loading, advance=1)


if __name__ == "__main__":
    __main__()
