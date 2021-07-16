from pprint import pprint
from glob import glob
import xarray
import psycopg2
from psycopg2.extras import execute_batch
import click
import re
from rich.progress import Progress
from rich import print
from decimal import *
import sys

"""
CDF is a hierarchical format that allows you to have lots of
dimensions to your data. This does the bare minimum to convert CDF
files from Woodwell into a format that can go into the Probable
Futures database schema.

`python pfimport.py --help`

`python pfimport.py --mutate True --dbname probable_futures --dbuser ford --dbpassword ford data/*.nc`

"""


def log(s):
    print("[Log] {}".format(s))


class Dataset:
    metadata = None
    observations = None
    variables = None
    has_data_id = None
    data_id = None
    conn = None
    cursor = None
    mutate = False
    progress = None
    filename = None
    da = None

    def __init__(self, filename, conn, mutate, progress):
        self.filename = filename
        self.conn = conn
        self.cursor = conn.cursor()
        self.load_cdf(filename)
        self.mutate = mutate
        self.progress = progress

    def cdf_has_times(self):
        return "time" in self.da.dims

    def load_cdf(self, filename):
        """I have a lot of side effects."""
        log("[NetCDF] [green]{}".format(filename))
        self.da = xarray.open_dataset(filename)
        self.metadata = self.da.attrs
        self.has_data_id = self.db_has_id()
        self.data_id = self.da.attrs.get("id")

        varnames = []
        for v in list(self.da.data_vars.keys()):
            varnames.append(self.da.variables[v].attrs["long_name"])
            # okay if none
            varnames.append(self.da.variables[v].attrs.get("units"))
        self.variables = varnames

        
        if self.cdf_has_times():
            self.load_cdf_stacked()
        else:
            self.load_cdf_unstacked()

    def load_cdf_stacked(self):
        
        # We do this differently than before and skip pandas; it's
        # getting too complicated. In this case we turn it into a big
        # dict and then step through bit by bit.

        daa = self.da.to_dict()

        # We only want one variable for now. The data is a list of lists of the form:
        # `data[time][lat][lon]`

        # I.e. one "time" per point

        data = daa["data_vars"]["mean_days_maxtemp_over_32C_"]["data"]

        # We want to flatten those six times and add some other data so it's of the form
        # lat, lon, dataset_id, value1, value2, value3, value4, value5, value6

        times = daa["coords"]["time"]["data"]
        lats = daa["coords"]["lat"]["data"]
        lons = daa["coords"]["lon"]["data"]

        # ***IMPORTANT*** our data is time > lat > lon, but postgis
        # expects points to be lon, lat so we switch it around
        
        obvs = []  # list of lists of observations

        for lat in range(0, len(lats)):
            for lon in range(0, len(lons)):
                # Start our row with lat, lon
                obv = [lons[lon], lats[lat], self.data_id]
                for time in range(0, len(times)):
                    time_at_pt = data[time][lat][lon]
                    if time_at_pt is None:
                        obv.append(None)
                    else:
                        obv.append(time_at_pt.days)
                obvs.append(obv)
        self.observations = obvs

    def load_cdf_unstacked(self):

        # Once we get into pandas dataframe we have a lot of flexibility
        # print(da.data_vars)
        # pprint(da)

        df = self.da.to_dataframe()
        df = df.where(df.notnull(), None)

        # Add a column in the front of the data (will come after lat long) with the `db_id` value
        df.insert(0, "dataset_id", int(self.da.attrs.get("id")))

        # Now we can turn the whole thing into a big python list that is easy to feed to Postgres
        self.observations = df.to_records().tolist()

    def figure_out_dataset(self):
        if self.has_data_id:
            pass
        else:
            self.db_create_dataset()

    def norm_model(self, t):
        return re.sub("globalREMO", "global REMO", t)

    def db_create_dataset(self):
        query = """INSERT INTO pf_public.pf_datasets (
            id,
            name,
            slug,
            description,
            resolution,
            category,
            model,
            description_baseline,
            field_name_baseline,
            description_1c,
            field_name_1c,
            description_1_5c,
            field_name_1_5c,
            description_2c,
            field_name_2c,
            description_2_5c,
            field_name_2_5c, 
            description_3c,
            field_name_3c
            ) VALUES 
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        values = [
            self.metadata.get("id"),
            self.metadata.get("title"),
            self.filename,
            self.metadata.get("description"),
            self.metadata.get("resolution"),
            self.metadata.get("category"),
            self.norm_model(self.metadata.get("model")),
        ] + self.variables
        try:
            self.cursor.execute(query, values)
            self.data_id = self.metadata.get("id")
        except IndexError as e:
            log(
                "[red][ERROR] [bold]{}[/bold] has wrong number of fields; skipping.".format(
                    self.filename,
                )
            )
        except psycopg2.errors.ForeignKeyViolation as e:
            log(
                "[red][ERROR] [bold]{}[/bold] keys don't match; see error; skipping.\n{}".format(
                    self.filename, e
                )
            )

    def db_has_id(self):
        self.data_id = self.metadata.get("id")
        query = "SELECT id FROM pf_public.pf_datasets WHERE id = %s"
        self.cursor.execute(query, (self.data_id,))
        dataset = self.cursor.fetchone()
        if dataset is not None:
            return True
        else:
            return False

    def db_delete_old_data(self):
        query = "delete from pf_public.pf_climate_data where dataset_id = %s"
        self.cursor.execute(query, (self.metadata.get("id"),))

    def db_do_bulk_insert(self):
        query = """INSERT INTO pf_public.pf_climate_data (
            coordinates,
            dataset_id,
            data_baseline,
            data_1C,
            data_1_5C,
            data_2C,
            data_2_5C,
            data_3C) VALUES (ST_GeomFromText('POINT(%s %s)', 4326), %s, %s, %s, %s, %s, %s, %s)"""
        task2 = self.progress.add_task(
            "[blue]{}".format(self.filename), total=len(self.observations)
        )
        for o in self.observations:
            self.progress.update(task2, advance=1)
            self.cursor.execute(query, o)

    def save(self):
        with self.conn:
            self.figure_out_dataset()
            if self.data_id and self.mutate:
                self.db_delete_old_data()
                self.db_do_bulk_insert()


@click.command()
@click.argument("files", type=click.File(), nargs=-1)
@click.option("--mutate", default=False, help="Set to True to write to database")
@click.option(
    "--dbhost", default="localhost", help='Database servername, default "localhost"'
)
@click.option(
    "--dbname",
    default="probable_futures",
    help='Database name, default "probable_futures"',
)
@click.option("--dbuser", nargs=1, default=None, help="Database username")
@click.option("--dbpassword", nargs=1, default=None, help="Database password")
def __main__(mutate, files, dbhost, dbname, dbuser, dbpassword):
    conn = psycopg2.connect(
        host=dbhost, database=dbname, user=dbuser, password=dbpassword
    )
    with Progress() as progress:
        task1 = progress.add_task("[red]Loading NetCDF files", total=len(files))
        for f in files:
            progress.update(task1, advance=1)
            try:
                Dataset(f.name, conn, mutate, progress).save()
            except IndexError as e:
                log('[red][Exception IndexError] {}'.format(e))
            except:
                log('[red][Failed w/exception] {}'.format(sys.exc_info()[0]))


if __name__ == "__main__":
    __main__()
