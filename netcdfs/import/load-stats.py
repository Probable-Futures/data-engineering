from geoalchemy2 import Geometry  # noqa: F401
from citext import CIText  # noqa: F401
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey  # noqa: F401
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from hashlib import md5

import click
from rich.progress import Progress
from rich import print
from tqdm.contrib.concurrent import process_map
from oyaml import safe_load


"""
CDF is a hierarchical format that allows you to have lots of
dimensions to your data. This does the bare minimum to convert CDF
files from Woodwell into a format that can go into the Probable
Futures database schema.

"""


class NoMatchingUnitError(Exception):
    def __init__(self, unit):
        self.unit = unit


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


def to_remo_stat(row):
    """Make a stat from the output of our dataframe."""
    (
        lon,
        lat,
        warming_levels,
        dataset_id,
        grid,
        unit,
        values_x_axis,
        likelihood_y_axis,
    ) = row
    lon = lon + 0  # +0 incase we have lon = -0 so it becomes 0
    lat = lat + 0  # +0 incase we have lat = -0 so it becomes 0
    hashed = to_hash(grid, lon, lat)

    stat_dict = {
        "dataset_id": int(dataset_id),  # Because we inserted it into the numpy array
        "coordinate_hash": hashed,
        "warming_scenario": str(warming_levels),
        "values_x_axis": values_x_axis,
        "likelihood_y_axis": likelihood_y_axis,
    }

    return stat_dict


# The command starts here
@click.command()
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
    conf,
    dbhost,
    dbname,
    dbuser,
    dbpassword,
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

    DatasetStatistic = Base.classes.pf_dataset_statistics

    Session = sessionmaker(bind=engine)

    # Load YAML file and do some very basic checking around provided conditions.
    conf = safe_load(open(conf))

    if load_cdfs is False and load_one_cdf is None:
        print(
            "[Error] You need to provide one of '--load-coordinates' or '--load-cdfs or --load-one-cdf [DATASET_ID]'"
        )
        exit(0)

    def update_cdf(cdf, stats):
        with Session() as session:
            print("[Notice] Updating {:,} stats".format(len(stats)))
            task_stats = progress.add_task(
                "Updating stats for {}".format(cdf["dataset"]), total=len(stats)
            )

            print("[Notice] Updating the database.")
            for stat in stats:
                print(stat["coordinate_hash"])
                # Update the values_x_axis and likelihood_y_axis columns based on the coordinate_hash
                session.query(DatasetStatistic).filter(
                    DatasetStatistic.coordinate_hash == stat["coordinate_hash"]
                ).update(
                    {
                        "values_x_axis": stat["values_x_axis"],
                        "likelihood_y_axis": stat["likelihood_y_axis"],
                    }
                )
                progress.update(task_stats, advance=1)
            print("[Notice] Committing to the database.")
            session.commit()

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
                        cdf.get("filename_new")
                    )
                )
                ds = xarray.open_dataset(cdf.get("filename_new"))

                def make_stats():

                    print("[Notice] Converting CDF file to list.")

                    df = (
                        ds.to_dataframe()
                        .dropna(how="all")
                        .assign(
                            dataset_id=cdf["dataset"],
                            grid=cdf["grid"],
                            unit=cdf["unit"],
                        )
                    )

                    # Combine values from columns x1 to x30 into a single
                    # array column
                    df["values_x_axis"] = df.filter(regex=r"^x\d{1,2}$").apply(
                        lambda row: row.dropna().tolist(), axis=1
                    )

                    # Drop individual x1 to x30 columns
                    df = df.drop(columns=["x" + str(i) for i in range(1, 31)])

                    # Combine values from columns y1 to y30 into a single
                    # array column
                    df["likelihood_y_axis"] = df.filter(regex=r"^y\d{1,2}$").apply(
                        lambda row: row.dropna().tolist(), axis=1
                    )

                    # Drop individual y1 to y30 columns
                    df = df.drop(columns=["y" + str(i) for i in range(1, 31)])

                    if sample_data:
                        df = df.head(100)

                    df = df.reindex(
                        columns=[
                            "dataset_id",
                            "grid",
                            "unit",
                            "values_x_axis",
                            "likelihood_y_axis",
                        ]
                    )

                    # And now we transform to records
                    recs = df.to_records()

                    print(
                        "[Notice] Using lots of processors to convert data to SQL-friendly data."
                    )

                    stats = process_map(to_remo_stat, recs, chunksize=10000)
                    return stats

                    return None

                stats = make_stats()

                # Finally, let's do the real work and step through
                update_cdf(cdf, stats)
                progress.update(task_loading, advance=1)


if __name__ == "__main__":
    __main__()
