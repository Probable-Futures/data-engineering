from geoalchemy2 import Geometry  # noqa: F401
from citext import CIText  # noqa: F401
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey  # noqa: F401
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from numpy import array
from helpers import to_hash, stat_fmt, NoDatasetWithThatIDError

import click
from rich.progress import Progress
from rich import print
from tqdm.contrib.concurrent import process_map
from oyaml import safe_load
import itertools
import math

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
        new_mid = stat_fmt(stats[i], unit)
        stat_dict = {
            "dataset_id": int(
                dataset_id
            ),  # Because we inserted it into the numpy array
            "coordinate_hash": hashed,
            "warming_scenario": str(scenario),
            "low_value": None,
            "high_value": None,
            "mid_value": new_mid,
        }
        return stat_dict

    new_stats = [to_stats(i, scenario) for i, scenario in enumerate(scenarios)]
    return new_stats


def to_remo_stat(row):
    """Make a stat from the output of our dataframe."""
    (
        lon,
        lat,
        warming_levels,
        low_value,
        mid_value,
        high_value,
        dataset_id,
        grid,
        unit,
    ) = row
    lon = lon + 0  # +0 incase we have lon = -0 so it becomes 0
    lat = lat + 0  # +0 incase we have lat = -0 so it becomes 0
    hashed = to_hash(grid, lon, lat)

    if math.isnan(low_value):
        new_low = None
    else:
        new_low = stat_fmt(low_value, unit)

    if math.isnan(mid_value):
        new_mid = None
    else:
        new_mid = stat_fmt(mid_value, unit)

    if math.isnan(high_value):
        new_high = None
    else:
        new_high = stat_fmt(high_value, unit)

    stat_dict = {
        "dataset_id": int(dataset_id),  # Because we inserted it into the numpy array
        "coordinate_hash": hashed,
        "warming_scenario": str(warming_levels),
        "low_value": new_low,
        "mid_value": new_mid,
        "high_value": new_high,
    }

    return stat_dict


# The command starts here
@click.command()
@click.option(
    "--load-coordinates",
    is_flag=True,
    default=False,
    help="Insert coordinates (lon/lats). You need to do this first, after database initialization;"
    + "if you don't, CDFs won't load because they refer to this table. It won't work after you've"
    + " loaded other data because to delete it would violate referential integrity; you likely need"
    + "to reset the database by dropping tables.",
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
    help="This script will only write to the database if this variable is set."
    + "Each CDF is loaded within an atomic transaction.",
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
            pool_size=20,
        )
    except Exception:
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
                parent_category=cdf["parent_category"],
                sub_category=cdf["sub_category"],
                model=cdf["model"],
                unit=cdf["unit"],
            )
            print("[Notice] Adding dataset '{}'".format(cdf["dataset"]))
            session.add(d)
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
                        .dropna(how="all")
                        .assign(
                            dataset_id=cdf["dataset"],
                            grid=cdf["grid"],
                            unit=cdf["unit"],
                        )
                    )

                    if sample_data:
                        df = df.head(100)

                    # We need to flatten our dataframe and the resulting rows
                    # need to be in this structure:
                    #
                    # lon, lat, time, low, mid, high, dataset_id, grid, unit = row
                    #
                    # We use the variables from the yaml file and rename those
                    # columns to the method.
                    #
                    renames = {}
                    for var in cdf["variables"]:
                        renames[var["name"]] = var["method"]

                    df = df.rename(columns=renames)

                    # Then we put everything in the order you would expect.
                    # Empty columns will be added in case low_value or high_value
                    # are not present in the netcdf file.
                    df = df.reindex(
                        columns=[
                            "low_value",
                            "mid_value",
                            "high_value",
                            "dataset_id",
                            "grid",
                            "unit",
                        ]
                    )

                    # And now we transform to records
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
