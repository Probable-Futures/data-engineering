from geoalchemy2 import Geometry
from geoalchemy2 import WKTElement
from citext import CIText
from sqlalchemy import create_engine, MetaData, Table, Column, ForeignKey
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker 

import xarray
from hashlib import md5

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

WARMS = [0.5 * x for x in range(1,6)]
    
@click.command()

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
@click.option("--cdfs", default=False, help="Insert CDFs")
@click.option("--coordsfile", default="models.yaml", help="Name of the models yaml file, typically models.yaml")


def __main__(mutate, conf, dbhost, dbname, dbuser, dbpassword, coords, cdfs, coordsfile):

    # Load YAML file
    conf = safe_load(open(conf))
    engine = create_engine('postgresql://' + dbuser + ':' + dbpassword + '@' + dbhost + '/' + dbname, echo=True)
    metadata = MetaData(schema='pf_public')
    metadata.reflect(engine)
    Base = automap_base(metadata=metadata)
    Base.prepare()
    Dataset, Coordinates, Statistics, DatasetData = \
        Base.classes.pf_datasets, \
        Base.classes.pf_dataset_coordinates, \
        Base.classes.pf_dataset_statistics, \
        Base.classes.pf_dataset_data

    Session = sessionmaker(bind=engine)

    # We make a table of all possible coordinates
    if coords is True and mutate is True:
        
        with Progress() as progress:
            with Session() as session:
                
                task1 = progress.add_task("Loading coords", total=len(conf.get('models')))

                for model in conf.get('models'):
                    name = model.get('model')
                    coords = list(itertools.product(model.get('lon'), model.get('lat')))

                    session.query(Coordinates).filter(Coordinates.model==name).delete()

                    def save_record(coord, name):
                        pt = 'POINT({} {})'.format(*coord)
                        return (Coordinates(model=name, point=pt))

                    records = [save_record(coord, name) for coord in coords]
                    session.bulk_save_objects(records)                
                    session.commit()
                    progress.update(task1, advance=1)                    

    if cdfs is True and mutate is True:    
        with Progress() as progress:

            task1 = progress.add_task("Loading NetCDF files", total=len(conf.get('datasets')))

            for cdf in conf.get('datasets'):


                progress.update(task1, advance=1)
                daa = xarray.open_dataset(cdf.get('filename')).to_dict()
                dims = [daa["coords"][x]["data"] for x in cdf.get('dimensions')]

                for v in cdf.get('variables'):
                    var = v.get('name')
                    a = itertools.product(*dims) # run it here to get the iterator
                    data = daa["data_vars"][var]["data"]
                    flat = deepflatten(data)
                    zipped = zip(a,flat)
                    ds = [[cdf.get('dataset'), var,
                           'POINT({} {})'.format(*coord), [d]]
                           for coord, d in zipped]
                    task2 = progress.add_task("Saving {}".format(cdf.get('name')), total=len(ds))
                    pprint(ds[0:10])
                    with Session() as session:
                        
                        d = Dataset(id = cdf['dataset'],
                                    name = cdf['name'],
                                    slug = cdf['slug'],
                                    description = cdf['description'],
                                    resolution = None,
                                    category = cdf['category'],
                                    model = cdf['model'],
                                    unit = cdf['unit'])
                        session.add(d)


                        def save_record(dataset_id, var, coord, val):
                            s = '{}{}'.format(cdf['model'], coord)
                            # pprint(s)
                            hashed = md5(s.encode()).hexdigest()
                            dd = DatasetData(dataset_id=dataset_id,
                                             warming_scenario=var,
                                             coordinate_hash=hashed,
                                             data_values=val)

                            progress.update(task2, advance=1)                        
                            session.add(dd)

                        for rec in ds:
                            save_record(*rec)

                        session.commit()




if __name__ == "__main__":
    __main__()
