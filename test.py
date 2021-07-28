import xarray
daa = xarray.open_dataset('data/wcdi_production/heat_module/rcm_globalremo/globalREMO_tasmax_days_ge32.nc').to_dict()

