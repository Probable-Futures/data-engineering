from geoalchemy2 import Geometry
from geoalchemy2 import WKTElement
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

import xarray
from hashlib import md5
from pandas import Timedelta

from pprint import pprint
from glob import glob
import click
import re
from rich.progress import Progress
from rich import print
from decimal import *
import decimal
from oyaml import safe_load
import sys
import traceback
import itertools
from iteration_utilities import deepflatten

"""

CDF is a hierarchical format that allows you to have lots of
dimensions to your data. This does the bare minimum to convert CDF
files from Woodwell into a format that can go into the Probable
Futures database schema.

`python pfimport.py --help`

`python pfimport.py --mutate True --dbname probable_futures --dbuser ford --dbpassword ford data/*.nc`

"""

WARMS = [0.5 * x for x in range(1, 6)]


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
@click.option("--log-sql", default=False, help="Log SQLAlchemy SQL calls")
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

    # Load YAML file
    conf = safe_load(open(conf))

    if load_coordinates is False and load_cdfs is False:
        print(
            "[Error] You need to provide one of '--load-coordinates True' or '--load-cdfs True'"
        )
        exit(0)

    if mutate is False:
        print("[Notice] Since --mutate was not invoked I will not change the database")
    else:
        print("[Notice] Since --mutate was invoked I WILL change the database")

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
    DatasetStatistic = Base.classes.pf_dataset_statistics
    Unit = Base.classes.pf_dataset_units
    VariableName = Base.classes.pf_statistical_variable_names
    VariableMethod = Base.classes.pf_statistical_variable_methods
    WarmingScenario = Base.classes.pf_warming_scenarios
    DatasetData = Base.classes.pf_dataset_data

    Session = sessionmaker(bind=engine)

    # ['RCM, global REMOSRID=4326;POINT(-179.8 -90)',
    # 'bafa02a38b49f1b3b25b84cfbfb57bc1']

    def to_hash(model, lon, lat):
        s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(model, lon, lat)
        hashed = md5(s.encode()).hexdigest()
        return hashed

    # We make a table of all possible coordinates
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
                with Session() as session:

                    progress.update(task_loading, advance=1)

                    print("[Notice] Deleting old data from {}".format(cdf["dataset"]))
                    # Delete old
                    if mutate:
                        session.query(DatasetData).filter(
                            DatasetData.dataset_id == cdf["dataset"]
                        ).delete()
                        session.query(Dataset).filter(
                            Dataset.id == cdf["dataset"]
                        ).delete()

                    # Add
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
                    if mutate:
                        session.add(d)

                    # Add variables
                    for v in cdf["variables"]:
                        print("[Notice] Adding variable '{}'".format(v["name"]))

                        vn = VariableName(
                            slug=v["name"],
                            name=v["long_name"],
                            dataset_id=cdf["dataset"],
                            description=None,
                        )
                        if mutate:
                            session.query(VariableName).filter(
                                VariableName.slug == v["name"],
                                VariableName.dataset_id == cdf["dataset"],
                            ).delete()
                            session.add(vn)
                            session.commit()

                    # THE MAIN EVENT
                    print("[Notice] Loading and converting CDF file.")
                    da = xarray.open_dataset(cdf.get("filename"))
                    dims = [list(da.coords[x].data) for x in cdf["dimensions"]]
                    product = itertools.product(*dims)
                    all_coords = list(product)

                    dataset_id = cdf["dataset"]
                    model = cdf["model"]

                    for v in cdf.get("variables"):
                        stats = []
                        print("[Notice] Processing variable '{}'".format(v["name"]))

                        # Grab all the stats for this variable and
                        # make them into one big list, which will
                        # align exactly with all_coords

                        values = da[v["name"]].to_series().tolist()
                        record_ct = len(values)
                        task_add_rows = progress.add_task(
                            "{}/{}".format(cdf["name"], v["name"]), total=record_ct
                        )
                        i = 0
                        for coords, val in zip(all_coords, values):
                            warming_scenario, lat, lon = coords
                            hashed = to_hash(model, lon, lat)
                            final_value = None
                            if str(val) != "NaT":
                                if type(val) == Timedelta:
                                    final_value = val.days
                                else:
                                    final_value = val
                            if i % 100000 == 0:
                                print(
                                    "[Notice] {:,}/{:,} rows processed".format(
                                        i, record_ct
                                    )
                                )
                            i = i + 1
                            stat_dict = {
                                "dataset_id": dataset_id,
                                "coordinate_hash": hashed,
                                "warming_scenario": str(warming_scenario),
                                "variable_method": v["method"],
                                "variable_name": v["name"],
                                "variable_value": final_value,
                            }
                            if final_value is not None:
                                stats.append(stat_dict)
                            progress.update(task_add_rows, advance=1)
                            # pprint([cdf['dimensions'], coords, val, stat_dict])
                            # ds = DatasetStatistic(**stat_dict)
                        if mutate:
                            print(
                                "[Notice] Inserting {:,} records into database...".format(
                                    len(stats)
                                )
                            )
                            session.bulk_insert_mappings(DatasetStatistic, stats)
                            print("[Notice] Inserted (not committed)")

                    if mutate:
                        print("[Notice] Committing to database")
                        session.commit()
                        progress.update(task_loading, advance=1)


if __name__ == "__main__":
    __main__()
