from pprint import pprint
import xarray
import click
import re
import oyaml
import os
from collections import OrderedDict

def load_cdf(_file):
    da = xarray.open_dataset(_file)
    metadata = da.attrs
    varnames = []
    for v in list(da.data_vars.keys()):
        od = OrderedDict([('name',v),
                          ('map_to',None),
                          ('long_name',da.variables[v].attrs["long_name"]),
                          # ('unit',da.variables[v].attrs.get("units"))
                          ])
        varnames.append(od)
    slug = os.path.splitext(os.path.basename(_file))[0]

    d = OrderedDict(
        [('dataset', int(metadata.get('id'))),
         ('filename', _file),
         ('slug', slug),
         ('dimensions', list(da.dims.keys())),
         ('name', metadata.get('title')),
         ('description', metadata.get('description')),
         ('category', metadata.get('category')),
         ('model', metadata.get('model')),
         ('unit', metadata.get('unit')),
         ('variables', varnames)])
    return d
        
@click.command()
@click.argument("files", type=click.File(), nargs=-1)
def __main__(files):
    datasets = [load_cdf(_file.name) for _file in files]
    print(oyaml.dump(datasets, allow_unicode=True))

if __name__ == "__main__":
    __main__()
