from geoalchemy2 import Geometry
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from hashlib import md5
from pandas import Timedelta

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


# Convert -1.504 to -1.5
def rounder(n):
    return round(float(n), 2)


# Turns a gigantic integer into a number of days, but still a pandas
# value, so you'll still need to round it.
def timedelta_to_decimalish(td):
    return Timedelta(td).days


def to_stat(row):

    """Make a stat from the output of our dataframe."""

    lon, lat, time, mean, pctl10, pctl90, dataset_id, model, unit = row
    hashed = to_hash(model, lon, lat)
    if unit == "days":
        pctl10 = timedelta_to_decimalish(pctl10)
        pctl90 = timedelta_to_decimalish(pctl90)
        mean = timedelta_to_decimalish(pctl90)

    # No matter what format we need to get things out of floats
    pctl10 = rounder(pctl10)
    pctl90 = rounder(pctl90)
    mean = rounder(mean)

    stat_dict = {
        "dataset_id": int(dataset_id),  # Because we inserted it into the numpy array
        "coordinate_hash": hashed,
        "warming_scenario": str(time),
        "pctl10": pctl10,
        "pctl90": pctl90,
        "mean": mean,
    }
    return stat_dict


# The command starts here
@click.command()
@click.option(
    "--mutate", is_flag=True, default=False, help="Set to True to write to database"
)
@click.option("--conf", default="conf.yaml", help="YAML config file")
@click.option(
    "--dbhost", default="localhost", help='Database servername, default "localhost"'
)
@click.option(
    "--dbname",
    default="probable_futures",
    help='Database name, default "probable_futures"',
)
@click.option("--dbuser", nargs=1, default="", help="Database username")
@click.option("--dbpassword", nargs=1, default="", help="Database password")
@click.option(
    "--load-coordinates", is_flag=True, default=False, help="Insert coordinates"
)
@click.option("--load-cdfs", is_flag=True, default=False, help="Insert CDFs")
@click.option(
    "--sample-data",
    is_flag=True,
    default=False,
    help="Load just 10,000 rows per dataset for testing",
)
@click.option("--log-sql", is_flag=True, default=False, help="Log SQLAlchemy SQL calls")
def __main__(
    mutate,
    conf,
    dbhost,
    dbname,
    dbuser,
    dbpassword,
    load_coordinates,
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

    if load_coordinates is False and load_cdfs is False:
        print(
            "[Error] You need to provide one of '--load-coordinates True' or '--load-cdfs True'"
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

    if load_cdfs is True:
        with Progress() as progress:
            # Add units
            task_loading = progress.add_task(
                "Loading NetCDF files", total=len(conf["datasets"])
            )
            for cdf in conf.get("datasets"):
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
