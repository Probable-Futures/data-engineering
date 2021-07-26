from pprint import pprint
import xarray
x = xarray.open_dataset("data/wcdi_production/heat_module/rcm_globalremo/globalREMO_tasmax_days_ge32.nc")
# x = xarray.open_dataset("data/wcdi_production/heat_module/gcm_cmip5/CMIP5_maxwetbulb_days_ge26.nc")
x = xarray.open_dataset("data/wcdi_production/heat_module/gcm_cmip5/CMIP5_tasmin_mean.nc")

pprint(x.to_array())


