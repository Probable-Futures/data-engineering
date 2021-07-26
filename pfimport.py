
from geoalchemy2 import Geometry
from geoalchemy2 import WKTElement
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base

from pprint import pprint
from glob import glob
import xarray
import click
import re
from rich.progress import Progress
from rich import print
from decimal import *
import decimal
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

WARMS = [0.5 * x for x in range(1,6)]
    
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

    def __init__(self, model):
        self.model = model
        self.name = model.get('model')
        self.coords = self.make_coord_set()

# f(0) = -179.25
# f(119) = 0
# f(239) = 179.25

# Coordinates:
#  * lon                                 (lon) float64 -179.2 -177.8 ... 179.2
#  * lat                                 (lat) float64 -89.25 -87.75 ... 89.25

    def make_coord_set(self):
        lon  = self.model.get('lon')
        lat  = self.model.get('lat')
    
        
        if lon == 120:
            lons = [round(x * 360/dimx - (180 - 360/dimx/2), 2) for x in range(dimx)]
        elif lon == 1800:
            lons = [round((1 + x) * 360/dimx - 180, 3) for x in range(dimx)]
            
        if lat == 240:
            lats = [((180/lat) * y) - 90 for y in range(lat)]
        elif lat == 901:
            print("MADE IT")
            lats = [round(((180/900) * y) - 90, 2) for y in range(lat)]            


        # [round(x * 360/dimx - 179.25, 2) for x in range(dimx)]


        
        
        print(lons)
        coords = list(itertools.product(lats, lons))
        return coords

    
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
@click.option("--dbuser",
              nargs=1,
              default=None,
              help="Database username")
@click.option("--dbpassword", nargs=1, default=None, help="Database password")
@click.option("--coords", default=False, help="Insert coordinates")
@click.option("--coordsfile", default="models.yaml", help="Name of the models yaml file, typically models.yaml")

def __main__(mutate, conf, files, dbhost, dbname, dbuser, dbpassword, coords, coordsfile):
    engine = create_engine('postgresql://' + dbuser + ':' + dbpassword + '@' + dbhost + '/' + dbname, echo=False)
    metadata = MetaData(schema='pf_public')
    x = metadata.reflect(engine)
    Base = automap_base(metadata=metadata)
    # calling prepare() just sets up mapped classes and relationships.
    Base.prepare()
    Dataset, Coordinates, Statistics, DatasetData = \
        Base.classes.pf_datasets, \
        Base.classes.pf_dataset_coordinates, \
        Base.classes.pf_dataset_statistics, \
        Base.classes.pf_dataset_data

    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)

    with Progress() as progress:
        with Session() as session:
            conf = safe_load(open(conf))
            
            for model in conf.get('models'):
                cs = CoordSet(model)
                # task1 = progress.add_task("Loading coords for {}".format(cs.name,), total=len(cs.coords))
                #session.query(Coordinates).filter(Coordinates.model==cs.name).delete()
                #
                #for coord in cs.coords:
                #    pprint(coord)
                #    pt = WKTElement('POINT({} {})'.format(*coord))
                #    session.add(Coordinates(model=cs.name, point=pt))
                #    progress.update(task1, advance=1)                
                # session.commit()
    # mapped classes are ready

    
    # cdfs = safe_load(open(conf))
    # conn = psycopg2.connect(
    #     host=dbhost, database=dbname, user=dbuser, password=dbpassword
    # )
    # if coords:
    #     with Progress() as progress:
    #         models = safe_load(open(coordsfile))
    #         for model in models:
    #             CoordSet(model, conn=conn, progress=progress).save()
                
    # with Progress() as progress:    
    #     task1 = progress.add_task("Loading NetCDF files", total=len(cdfs))
    #     for cdf in cdfs:
    #         Dataset(cdf=cdf, conn=conn, mutate=mutate, progress=progress)
    # except:
    #     logging.error('[Database] {}'.format(sys.exc_info()[0]))
    #     traceback.print_exc()        


if __name__ == "__main__":
    __main__()
