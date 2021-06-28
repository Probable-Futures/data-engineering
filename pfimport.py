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

"""

CDF is a hierarchical format that allows you to have lots of dimensions to your data.

Data has axes: lat, long.

Data has variables, which are arrays: temp at 1 degree, temp at 2 degree

Axes by convention include variables to describe themselves--i.e. we have values for lat long.

"""

def log(s):
    print("[Log] {}".format(s))
    
class Dataset():
    metadata = None
    observations = None
    variables = None
    data_id = None
    conn = None
    cursor = None
    mutate = False
    progress = None
    filename = None
    
    def __init__(self, filename, conn, mutate, progress):
        self.filename = filename
        self.conn = conn
        self.cursor = conn.cursor()
        self.load_cdf(filename)
        self.mutate = mutate
        self.progress = progress
        
    def load_cdf(self, filename):
        """I have a lot of side effects."""
        log("Working with [green]{}".format(filename))
        da = xarray.open_dataset(filename)
        self.metadata = da.attrs
        self.data_id = self.db_has_id()
        varnames = []
        for v in list(da.data_vars.keys()):
            varnames.append(da.variables[v].attrs['long_name'])
            varnames.append(da.variables[v].attrs['units'])            
        self.variables = varnames
        if self.data_id:
            pass
        else:
            self.db_create_dataset()

        # Once we get into pandas dataframe we have a lot of flexibility
        # print(da.data_vars)
        log("[{}] Converting to dataframe.".format(self.metadata.get('id')))        
        df = da.to_dataframe()
        df = df.where(df.notnull(), None)
        # Add a column in the front of the data (will come after lat long) with the `db_id` value
        df.insert(0,'dataset_id', int(da.attrs.get('id')))
        # Now we can turn the whole thing into a big python list that is easy to feed to Postgres
        self.observations = df.to_records().tolist()
        # print(self.observations)
        # print("Here is the data inside the dataframe")
        # a = df.query('lon==-26.4 & lat==-57.4')
        # print(a)
        # print("Here is the data after it's converted to Python native types")
        # a.round()
        # for f in a.itertuples():
        #    x = list(f)
        #    print(x)

    def norm_model(self,t):
        return re.sub('globalREMO', 'global REMO', t)
            
    def db_create_dataset(self):

        query = """INSERT INTO pf_datasets (
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
            self.metadata.get('id'),
            self.metadata.get('title'),
         self.filename,
         self.metadata.get('description'),
         self.metadata.get('resolution'),
         self.metadata.get('category'),
            self.norm_model(self.metadata.get('model')),
         ] + self.variables
        self.cursor.execute(query, values)

        
    def db_has_id(self):
        self.data_id = self.metadata.get('id')
        query = "SELECT id FROM pf_datasets WHERE id = %s"
        self.cursor.execute(query, (self.data_id,))
        dataset = self.cursor.fetchone()
        if dataset is not None:
            return True
        else:
            return False
    
    def db_delete_old_data(self):
        log("[{}] Deleting climate observations from database.".format(self.metadata.get('id')))
        query = "delete from pf_climate_data where dataset_id = %s"
        if self.mutate:
            self.cursor.execute(query, (self.metadata.get('id'),))


    def db_do_bulk_insert(self):
        log("[{}] Inserting climate observations into database.".format(self.metadata.get('id')))
        query = """INSERT INTO pf_climate_data (coordinates,dataset_id,data_baseline,data_1C,data_1_5C,data_2C,data_2_5C,data_3C) VALUES (ST_GeomFromText('POINT(%s %s)', 4326), %s,%s,%s,%s,%s,%s,%s)"""
        task2 = self.progress.add_task("[cyan][{}] {}".format(
            self.metadata.get('id'),
            self.metadata.get('title')), total=len(self.observations))
        for o in self.observations:
            #if o[1]==-57.4:
            #    print(o)


            self.progress.update(task2, advance=1)                
            if self.mutate:
                self.cursor.execute(query, o)
            else:
                pass
                
    def save(self):
        with self.conn:
            self.db_delete_old_data()
            self.db_do_bulk_insert()

@click.command()
@click.option('--mutate', default=False, help='Set to True to write to database')
@click.option('--files', default=None, help='Files to process')
@click.option('--dbhost', default='localhost', help='Database servername, default "localhost"')
@click.option('--dbname', default='pf_public', help='Database name, default "pf_public"')
@click.option('--dbuser', default=None, help='Database username')
@click.option('--dbpassword', default=None, help='Database password')
def __main__(mutate, files, dbhost, dbname, dbuser, dbpassword):
    conn = psycopg2.connect(host=dbhost,
                            database=dbname,
                            user=dbuser,
                            password=dbpassword)
    files = glob('data/*.nc')
    with Progress() as progress:
        task1 = progress.add_task("[red]Loading NetCDF files", total=len(files))
        for f in files:
            progress.update(task1, advance=1)
            Dataset(f, conn, mutate, progress).save()


        

if __name__ == '__main__':
    __main__()
