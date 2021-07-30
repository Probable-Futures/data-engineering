from geoalchemy2 import Geometry
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

    # This is boilerplate SQLAlchemy introspection; it makes classes
    # that behave about how you'd expect for the tables in the current
    # schema. These objects aren't smart about PostGIS but that's
    # okay.

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

    # EWKT is wild but basically it's POINT(X Y), where X and Y are
    # arbitrary precision numbers with signed negative but unsigned
    # positive and have no trailing zeroes. The decimal formatting is
    # key and if PF gives us data with 5 degrees of precision we'll
    # need to revisit this. The {:.4g} says turn the float into a
    # numeral with precision 4 and the 'g' gets rid of trailing
    # zeroes. So -179.0 becomes -179 while 20.1 is unchanged.

    def to_hash(model, lon, lat):
        s = "{}SRID=4326;POINT({:.4g} {:.4g})".format(model, lon, lat)
        hashed = md5(s.encode()).hexdigest()
        return hashed

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

                    # Step through each variable and write it to the
                    # database. We do a naive deletion before we
                    # insert. We don't have to since our referential
                    # integrity is via the external database_id
                    # instead of the postgres-provided one but it
                    # doesn't do any harm to clean things up instead
                    # of figuring out upserts.

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

                            # I was commiting here because for some
                            # reason when I don't commit here
                            # SQLAlchemy or Postgres decides the
                            # variables haven't been inserted when I
                            # go to insert the rows. Maybe batches
                            # happen in an unusual context. For right
                            # now I can't make the problem happen
                            # again but I'll leave this here in case
                            # it does.

                            # session.commit()

                    # This is the main event. It's for REMO files with one value per row.

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

                    for v in cdf.get("variables"):
                        stats = []
                        print("[Notice] Processing variable '{}'".format(v["name"]))

                        # Grab all the values for this variable and
                        # make them into one big list, which will
                        # align exactly with all_coords if you put
                        # them next to each other. Under the hood this
                        # goes from xarray to pandas series, then to a
                        # python list.

                        # What I'd prefer to do is figure out how to
                        # "flatten" an xarray from inside the
                        # dataframe and just kind of log that to the
                        # database but every method just reproduces
                        # this logic, i.e. you take arrays of the
                        # coordinates and step through them the way I
                        # am doing.

                        values = da[v["name"]].to_series().tolist()

                        record_ct = len(values)
                        task_add_rows = progress.add_task(
                            "{}/{}".format(cdf["name"], v["name"]), total=record_ct
                        )

                        # Anyway that's kind of it. Now we have two
                        # big honking arrays and all that is left to
                        # do is zip them together and write them to
                        # the database.

                        # Added a dumb counter here to make loading
                        # more explicit

                        i = 0

                        # Now we glue together the generated coords
                        # and the generated values.

                        for coords, val in zip(all_coords, values):
                            warming_scenario, lat, lon = coords
                            hashed = to_hash(model, lon, lat)
                            final_value = None

                            # We could evaluate and convert these
                            # objects at the dataframe level instead
                            # of stepping through but I like the
                            # control of doing it at the very end. We
                            # are looking for NaT which I think means
                            # "not a time" and is equal to none.

                            if str(val) != "NaT":
                                if type(val) == Timedelta:
                                    final_value = val.days
                                else:
                                    final_value = val

                            # Tell us what you're doing every 500000
                            # rows.
                            if i % 500000 == 0:
                                print(
                                    "[Notice] {:,}/{:,} rows processed".format(
                                        i, record_ct
                                    )
                                )
                            i = i + 1

                            # It's probably 100x faster to make dicts
                            # than DatasetStatistic objects, and
                            # SQLAlchemy will let you batch save a
                            # list of dicts into the database if you
                            # use session.bulk_insert_mappings(). So
                            # this is our one big optimization. We do
                            # it once per variable, which works out to
                            # 9 million rows.

                            stat_dict = {
                                "dataset_id": dataset_id,
                                "coordinate_hash": hashed,
                                "warming_scenario": str(warming_scenario),
                                "variable_method": v["method"],
                                "variable_name": v["name"],
                                "variable_value": final_value,
                            }

                            # This is a filter: We don't put null
                            # values into the table. This cuts about
                            # 70% of rows out of the database which is
                            # pretty huge.

                            if final_value is not None:
                                stats.append(stat_dict)

                            progress.update(task_add_rows, advance=1)

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
