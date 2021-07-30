from geoalchemy2 import Geometry
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
from multiprocessing import Pool

import xarray
from hashlib import md5
from pandas import Timedelta

from pprint import pprint
from glob import glob
import click
import re
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

`python pfimport.py --help`

`python pfimport.py --mutate True --dbname probable_futures --dbuser ford --dbpassword ford data/*.nc`

"""

WARMS = [0.5 * x for x in range(1, 6)]


# The following global defs allow us to use multiprocessing to churn
# through records, which speeds import up quite a bit.

# EWKT is wild but basically it's POINT(X Y), where X and Y are
# arbitrary precision numbers with signed negative but unsigned
# positive and have no trailing zeroes. The decimal formatting is
# key and if PF gives us data with 5 degrees of precision we'll
# need to revisit this. The {:.4g} says turn the float into a
# numeral with precision 4 and the 'g' gets rid of trailing
# zeroes. So -179.0 becomes -179 while 20.1 is unchanged.


# This is boilerplate SQLAlchemy introspection; it makes classes
# that behave about how you'd expect for the tables in the current
# schema. These objects aren't smart about PostGIS but that's
# okay.


def to_hash(model, lon, lat):
    s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(model, lon, lat)
    hashed = md5(s.encode()).hexdigest()
    return hashed


def to_stat(zrow):
    _locals, coords, val = zrow
    dataset_id, vmethod, vname, model = _locals
    warming_scenario, lat, lon = coords
    hashed = to_hash(model, lon, lat)
    final_value = pytype_to_sqltype(val)
    stat_dict = {
        "dataset_id": dataset_id,
        "coordinate_hash": hashed,
        "warming_scenario": str(warming_scenario),
        "variable_method": vmethod,
        "variable_name": vname,
        "variable_value": final_value,
    }
    return stat_dict


def pytype_to_sqltype(val):
    final_value = None
    if str(val) != "NaT":
        if type(val) == Timedelta:
            final_value = val.days
        else:
            final_value = val
    return final_value


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
):

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

            print("[Notice] Deleting, then adding variables".format(cdf["dataset"]))
            session.query(StatisticalVariableName).filter(
                StatisticalVariableName.dataset_id == cdf["dataset"]
            ).delete()

            vns = []
            for v in cdf["variables"]:
                vn = StatisticalVariableName(
                    slug=v["name"],
                    name=v["long_name"],
                    dataset_id=cdf["dataset"],
                    description=None,
                )
                print("[Notice] Adding variable '{}' [{}]".format(v["name"], vn))
                vns.append(vn)

            session.add_all(vns)
            print("[Notice] Inserting {:,} stats".format(len(stats)))
            task_stats = progress.add_task(
                "Loading stats for {}".format(cdf["dataset"]), total=len(stats)
            )

            object_stats = []
            for stat in stats:
                ds = DatasetStatistic(**stat)
                session.add(ds)
                progress.update(task_stats, advance=1)
            # session.bulk_insert_mappings(DatasetStatistic, stats)
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
                # Step through each variable and write it to the
                # database. We do a naive deletion before we
                # insert. We don't have to since our referential
                # integrity is via the external database_id
                # instead of the postgres-provided one but it
                # doesn't do any harm to clean things up instead
                # of figuring out upserts.

                print("[Notice] Loading and converting CDF file.")
                da = xarray.open_dataset(cdf.get("filename"))

                # We make a list of all dimensions as we define
                # them for this file in our conf file and then
                # make the product of them, leading to a very
                # large list (6 * 1800 * 901) = 9,730,800 of
                # tuples like (0.5, -179.8, -90),...

                dims = [list(da.coords[x].data) for x in cdf["dimensions"]]
                product = itertools.product(*dims)
                all_coords = list(product)

                dataset_id = cdf["dataset"]
                model = cdf["model"]

                def make_stats():
                    stats = []
                    for v in cdf["variables"]:
                        values = da[v["name"]].to_series().tolist()
                        # Now we glue together the generated coords
                        # and the generated values.
                        print("[Notice] Zipping together data.")
                        r = itertools.repeat(
                            [dataset_id, v["method"], v["name"], model]
                        )
                        zipped = list(zip(r, all_coords, values))
                        print(
                            "[Notice] Churning through the zipped data using lots of processors."
                        )
                        all_stats = process_map(to_stat, zipped, chunksize=100000)
                        print("[Notice] Filtering out null values from the stats.")
                        filtered_stats = [x for x in all_stats if x["variable_value"]]
                        stats += filtered_stats
                    return stats

                stats = make_stats()
                # stats = []

                if mutate:
                    save_cdf(cdf, stats)
                progress.update(task_loading, advance=1)

                # This is the main event. It's for REMO files with one value per row.


if __name__ == "__main__":
    __main__()
