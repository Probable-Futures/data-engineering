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
from oyaml import safe_load
import logging
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

class Dataset:

    def __init__(self, cdf=None, conn=None, progress=None, mutate=False):
        self.cdf = cdf
        self.dataset_id = cdf.get('dataset')
        self.filename = cdf.get('filename')
        self.conn = conn
        self.mutate = mutate
        self.progress = progress
        self.load_cdf()

    def cdf_has_times(self):
        return "time" in self.da.dims

    warms = [0.5 * x for x in range(1,6)]
    
    def load_cdf(self):
        daa = xarray.open_dataset(self.cdf.get('filename')).to_dict()
        dims = [daa["coords"][x]["data"] for x in self.cdf.get('dimensions')]
        for v in self.cdf.get('variables'):
            var = v.get('name')
            a = itertools.product(*dims) # run it here to get the iterator
            data = daa["data_vars"][var]["data"]
            flat = deepflatten(data)
            zipped = zip(a,flat)
            ds = [[self.dataset_id, var, *ll, d] for ll, d in zipped]
            pprint(ds[0:10])

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
            logging.error(
                "{} has wrong number of fields; skipping.".format(
                    self.filename,
                )
            )
        except psycopg2.errors.ForeignKeyViolation as e:
            logging.error(
                "{} keys don't match; see error; skipping.\n{}".format(
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
            data_baseline_mean,
            data_baseline_pctl10,
            data_baseline_pctl90,
            data_1C_mean,
            data_1C_pctl10,
            data_1C_pctl90,
            data_1_5C_mean,
            data_1_5C_pctl10,
            data_1_5C_pctl90,
            data_2C_mean,
            data_2C_pctl10,
            data_2C_pctl90,
            data_2_5C_mean,
            data_2_5C_pctl10,
            data_2_5C_pctl90,
            data_3C_mean,
            data_3C_pctl10,
            data_3C_pctl90
            ) VALUES (
            'POINT(%s %s)', %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s)"""
        task2 = self.progress.add_task(
            "[blue]{}".format(self.filename), total=len(self.observations)
        )
        for o in self.observations:
            self.progress.update(task2, advance=1)
            # log("[blue][OBSERVATION]{}".format(o))
            self.cursor.execute(query, o)

    def save(self):
        with self.conn:
            self.figure_out_dataset()
            if self.data_id and self.mutate:
                self.db_delete_old_data()
                self.db_do_bulk_insert()


class CoordSet():

    def __init__(self, model, conn=None, progress=None):
        self.model = model
        self.progress = progress
        self.conn = conn
        self.cursor = self.conn.cursor()
        self.coords = self.make_coord_set(model['lon'], model['lat'])
    
    def make_coord_set(self,xct, yct):
        xstep = 360/xct
        ystep = 180/yct
        ll = []
        for x in range(0,xct):
            lon = float(xstep * x - 180)
            for y in range(0,yct):
                lat = float(ystep * y - 90)
                ll.append([lon, lat])
        return ll
        
    def delete_coords(self):
        deletion = """DELETE FROM pf_public.pf_dataset_coordinates WHERE MODEL=%s"""
        self.cursor.execute(deletion, [self.model['model']])
        
    def insert_coords(self):
        task1 = self.progress.add_task("Saving coordinates for {}".format(self.model['model']),
                                              total=len(self.coords))
        query = """INSERT INTO pf_public.pf_dataset_coordinates
             (point, model) VALUES (ST_Point(%s,%s), '{}')""".format(self.model['model'])
        
        for coord in self.coords:
            self.progress.update(task1, advance=1)
            self.cursor.execute(query, coord)
        
    def save(self):
        with self.conn:
            self.delete_coords()
            self.insert_coords()
            


@click.command()
@click.argument("files", type=click.File(), nargs=-1)

@click.option("--mutate", default=False, help="Set to True to write to database")
@click.option("--conf", default="conf.yaml", help="YAML config file")
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
@click.option("--coords", default=False, help="Insert coordinates")
@click.option("--coordsfile", default="models.yaml", help="Name of the models yaml file, typically models.yaml")
def __main__(mutate, conf, files, dbhost, dbname, dbuser, dbpassword, coords, coordsfile):
    cursor = None
    cdfs = safe_load(open(conf))
    try:
        conn = psycopg2.connect(
            host=dbhost, database=dbname, user=dbuser, password=dbpassword
        )
        if coords:
            with Progress() as progress:
                models = safe_load(open(coordsfile))
                for model in models:
                    CoordSet(model, conn=conn, progress=progress).save()

        with Progress() as progress:    
            task1 = progress.add_task("Loading NetCDF files", total=len(cdfs))
            for cdf in cdfs:
                Dataset(cdf=cdf, conn=conn, mutate=mutate, progress=progress)
    except:
        logging.error('[Database] {}'.format(sys.exc_info()[0]))
        traceback.print_exc()        


if __name__ == "__main__":
    __main__()
