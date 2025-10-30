from geoalchemy2 import Geometry  # noqa: F401
from citext import CIText  # noqa: F401
from sqlalchemy import (  # noqa: F401
    create_engine,
    MetaData,
    Table,
    Column,
    ForeignKey,
    text,
)
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
from helpers import (
    load_netcdf_file,
    to_remo_stat,
    to_remo_stat_new,
    NoDatasetWithThatIDError,
)
import os

import xarray

import click
from rich.progress import Progress
from rich import print
from tqdm.contrib.concurrent import process_map, thread_map
from oyaml import safe_load


"""
CDF is a hierarchical format that allows you to have lots of
dimensions to your data. This does the bare minimum to convert CDF
files from Woodwell into a format that can go into the Probable
Futures database schema.

"""


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
@click.option(
    "--batch",
    is_flag=False,
    nargs=1,
    type=int,
    help="Batch number to process (used for splitting datasets into chunks)",
)
@click.option(
    "--batch-size",
    is_flag=False,
    nargs=1,
    type=int,
    default=1500000,
    help="Number of records to process per batch",
)
@click.option(
    "--netcdf-object-key",
    default="",
    help='Provide the s3 key if deploying on AWS Lambda, default ""',
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
    batch,
    batch_size,
    netcdf_object_key,
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

    Session = sessionmaker(bind=engine)

    # Load YAML file and do some very basic checking around provided conditions.
    conf = safe_load(open(conf))
    run_env = os.environ.get("RUN_ENV")

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

            insert_batch_size = 200000
            total_records = len(stats)

            print("[Notice] Delete temp_stats if exists..")
            session.execute(text("DROP TABLE IF EXISTS temp_stats"))

            print("[Notice] Creating temp table..")
            session.execute(
                text(
                    """
                    CREATE TEMPORARY TABLE temp_stats (
                        dataset_id int,
                        coordinate_hash text,
                        warming_scenario text,
                        mean_value double precision,
                        median_value double precision
                    )
                    """
                )
            )

            for i in range(0, total_records, insert_batch_size):
                batch_stats = stats[i : i + insert_batch_size]
                print(
                    "[Notice] Inserting batch of size {:,}..".format(len(batch_stats))
                )
                session.execute(
                    text(
                        """
                            insert into temp_stats (
                                dataset_id, coordinate_hash, warming_scenario,
                                mean_value, median_value)
                            values (:dataset_id, :coordinate_hash, :warming_scenario, :mean_value, :median_value)
                        """
                    ),
                    batch_stats,
                )
                print("[Notice] Updating main table from temp table..")
                session.execute(
                    text(
                        """
                            UPDATE pf_public.pf_dataset_statistics ds
                            SET mean_value = ts.mean_value,
                                median_value = ts.median_value
                            FROM temp_stats ts
                            WHERE ds.dataset_id = ts.dataset_id
                            AND ds.coordinate_hash = ts.coordinate_hash
                            AND ds.warming_scenario = ts.warming_scenario
                        """
                    )
                )

                print(
                    f"[Notice] Committing to the database: "
                    f"Batch {i / insert_batch_size} "
                    f"out of {round(total_records / insert_batch_size)}"
                )

                session.commit()
                print("[Notice] Truncating temp table..")
                session.execute(text("TRUNCATE temp_stats"))
                progress.update(task_stats, advance=len(batch_stats))

            print("[Notice] Dropping temp table..")
            session.execute(text("DROP TABLE temp_stats"))

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
                file_path = (
                    load_netcdf_file(netcdf_object_key)
                    if run_env == "development" or run_env == "production"
                    else cdf.get("filename")
                )

                ds = xarray.open_dataset(file_path)

                def make_stats():

                    print("[Notice] Converting CDF file to list.")

                    df = (
                        ds.to_dataframe()
                        .dropna(how="all")
                        .assign(
                            dataset_id=cdf["dataset"],
                            grid=cdf["grid"],
                            unit=cdf["unit"],
                            use_mean_for_mid=cdf["use_mean_for_mid"],
                        )
                    )

                    if sample_data:
                        df = df.head(100)

                    if batch is not None and batch_size is not None:
                        batch_size_to_int = int(batch_size)
                        batch_to_int = int(batch)
                        print(f"[Notice] Processing batch {batch}")
                        print(f"[Notice] Batch size {batch_size_to_int}")
                        total_records = len(df)
                        total_batches = (
                            total_records + batch_size_to_int - 1
                        ) // batch_size_to_int  # Round up
                        start_idx = (batch_to_int - 1) * batch_size_to_int
                        end_idx = min(batch_to_int * batch_size_to_int, total_records)

                        if batch_to_int > total_batches:
                            print(
                                f"[Notice] No data left to process for batch {batch}."
                            )
                            return None

                        print(
                            f"[Notice] Processing batch {batch_to_int}/{total_batches}."
                        )
                        df = df.iloc[start_idx:end_idx]

                    renames = {}
                    for var in cdf["variables"]:
                        renames[var["name"]] = var["method"]

                    df = df.rename(columns=renames)

                    df = df.reindex(
                        columns=[
                            "low_value",
                            "mean_value",
                            "median_value",
                            "high_value",
                            "dataset_id",
                            "grid",
                            "unit",
                            "use_mean_for_mid",
                        ]
                    )

                    # And now we transform to records
                    recs = df.to_records()

                    print(
                        "[Notice] Using lots of processors to convert data to SQL-friendly data."
                    )

                    if run_env == "development" or run_env == "production":
                        print("[Notice] Using thread_map for development environment.")
                        max_workers = 4
                        stats = thread_map(to_remo_stat, recs, max_workers=max_workers)
                        return stats
                    else:
                        print("[Notice] Using process_map for local environment.")
                        stats = process_map(to_remo_stat, recs, chunksize=10000)
                        return stats

                stats = make_stats()

                # Finally, let's do the real work and step through
                update_cdf(cdf, stats)
                progress.update(task_loading, advance=1)


if __name__ == "__main__":
    __main__()
