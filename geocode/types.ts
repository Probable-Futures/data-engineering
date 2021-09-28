import * as csv from "fast-csv";

export type City = string;
export type Country = string;
export type GeocodeRequest = {
  country: City;
  city: Country;
};
export type GeocodeResults = {
  place_name: string;
  long: number;
  lat: number;
};

export type AddressRow = GeocodeRequest & {
  pf_id: string;
  id: string;
};

export type GeocodedAddressRow = AddressRow & GeocodeResults;

export type CountryCache = Map<City, GeocodeResults>;

export type GeoCache = Map<Country, CountryCache>;
