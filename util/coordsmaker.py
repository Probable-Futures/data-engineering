from pprint import pprint
import xarray
import yaml
x = xarray.open_dataset("data/wcdi_production/heat_module/rcm_globalremo/globalREMO_tasmax_days_ge32.nc")
# x = xarray.open_dataset("data/wcdi_production/heat_module/gcm_cmip5/CMIP5_maxwetbulb_days_ge26.nc")
# x = xarray.open_dataset("data/wcdi_production/heat_module/gcm_cmip5/CMIP5_tasmin_mean.nc")

d = x.to_dict()
lats = d['coords']['lat']['data']
lons = d['coords']['lon']['data']

x = yaml.dump({'lat':lats, 'lon':lons}, default_flow_style=True)
print(x)
# print(oyaml.dump({'lon':lons}))




