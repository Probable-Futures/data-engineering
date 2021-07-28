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
@click.option("--load-coordinates", default=False, help="Insert coordinates")
@click.option("--load-cdfs", default=False, help="Insert CDFs")
@click.option("--log-sql", default=False, help="Log SQLAlchemy SQL calls")


def __main__(mutate, conf, dbhost, dbname, dbuser, dbpassword, load_coordinates, load_cdfs, log_sql):

    # Load YAML file
    conf = safe_load(open(conf))
    engine = create_engine('postgresql://' + dbuser + ':' + dbpassword + '@' + dbhost + '/' + dbname, echo=log_sql)
    metadata = MetaData(schema='pf_public')
    metadata.reflect(engine)
    Base = automap_base(metadata=metadata)
    Base.prepare()
    Dataset, Coordinates, DatasetStatistic, WarmingScenario, DatasetData = \
        Base.classes.pf_datasets, \
        Base.classes.pf_dataset_coordinates, \
        Base.classes.pf_dataset_statistics, \
        Base.classes.pf_warming_scenarios, \
        Base.classes.pf_dataset_data

    Session = sessionmaker(bind=engine)

    def to_hash(model, pts):
        s = '{}SRID=4326;POINT({} {})'.format(model, pts[0], pts[1])
        hashed = md5(s.encode()).hexdigest()
        return hashed

    # We make a table of all possible coordinates
    if load_coordinates is True:
        print("Loading coordinates using data in the config file.")
        
        with Progress() as progress:
            with Session() as session:
                task1 = progress.add_task("Loading coords", total=len(conf.get('models')))

                for model in conf.get('models'):
                    name = model.get('model')
                    coords = list(itertools.product(model.get('lon'), model.get('lat')))

                    if mutate:
                        session.query(Coordinates).filter(Coordinates.model==name).delete()

                    def to_record(coord, name):
                        pt = 'POINT({} {})'.format(*coord)
                        return (Coordinates(model=name, point=pt))

                    records = [to_record(coord, name) for coord in coords]
                    if mutate:
                        session.bulk_save_objects(records)                
                        session.commit()
                    progress.update(task1, advance=1)                    

    if load_cdfs is True:
        with Progress() as progress:

            task1 = progress.add_task("Loading NetCDF files", total=len(conf.get('datasets')))

            for cdf in conf.get('datasets'):

                progress.update(task1, advance=1)
                
                task2 = progress.add_task("{}".format(cdf.get('name')),
                                          total=len(cdf.get('variables')))
                    
                with Session() as session:

                    print("Deleting old data from {}".format(cdf['dataset']))
                    # Delete old
                    if mutate:
                        session.query(DatasetData).filter(DatasetData.dataset_id==cdf['dataset']).delete()
                        session.query(Dataset).filter(Dataset.id==cdf['dataset']).delete()

                    # Add
                    d = Dataset(id = cdf['dataset'],
                                name = cdf['name'],
                                slug = cdf['slug'],
                                description = cdf['description'],
                                resolution = None,
                                category = cdf['category'],
                                model = cdf['model'],
                                unit = cdf['unit'])
                    print("Adding dataset {}".format(cdf['dataset']))
                    if mutate:
                        session.add(d)


                    # Add variables
                    for v in cdf['variables']:
                        print("Adding variable {}".format(v['name']))
                        ws = WarmingScenario(slug=v['name'],
                                             name=v['long_name'],
                                             description=None)
                        if mutate:
                            session.query(WarmingScenario).filter(
                                WarmingScenario.slug==v['name']).delete()
                            session.add(ws)

                    # THE MAIN EVENT
                    
                    da = xarray.open_dataset(cdf.get('filename'))
                    dims = [list(da.coords[x].data) for x in cdf.get('dimensions')]
                    product = itertools.product(*dims) # run it here to get the iterator
                    rowvals = [x for x in product]

                    dataset_id = cdf.get('dataset')
                    
                    for v in cdf.get('variables'):
                        model = cdf['model']
                        to_concat = (cdf['dataset'], v['name'],)
                        values = da[v['name']].to_series().tolist()[0:1000]
                        stats = []
                        for coords, val in zip(rowvals, values):
                            pprint("I MADE IT")
                            warming_scenario, lat, lon = coords
                            hashed = to_hash(model, [lon, lat])
                            dd = DatasetStatistic(dataset_id=dataset_id,
                                                  warming_scenario=warming_scenario,
                                                  coordinate_hash=hashed,
                                                  variable_value=val)
                            pprint(dd)
                            return dd

                    

                             
                    records = [to_record(*rec) for rec in ds]
                    if mutate:

                        # Doing this in bulk led to some weird async thing where the variables weren't in the database.
                        for record in records:
                            session.add(record)                                

                    print("Saving data")
                    if mutate:
                        # session.bulk_save_objects(records)  
                        session.commit()
                    progress.update(task1, advance=1)
                            

if __name__ == "__main__":
    __main__()
