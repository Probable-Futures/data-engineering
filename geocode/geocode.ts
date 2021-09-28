import util from "util";
import * as types from "./types";
import * as mapbox from "./mapbox";

const debug = require("debug")("geocode");

const geoCache: types.GeoCache = new Map<types.Country, types.CountryCache>();

function createCountryCache(city: types.City, results: types.GeocodeResults): types.CountryCache {
  return new Map([[city, results]]);
}

export async function geocode(address: types.AddressRow): Promise<types.GeocodedAddressRow> {
  const { city, country } = address;
  debug("Input: %o", address);
  const cache = geoCache.get(country);
  let results;

  if (!cache) {
    results = await mapbox.geocodeCity({ city, country });
    geoCache.set(country, createCountryCache(city, results));
  } else if (!cache.has(city)) {
    results = await mapbox.geocodeCity({ city, country });
    cache.set(city, results);
  } else {
    debug("cache hit");
    results = cache.get(city) as types.GeocodeResults;
  }
  const geocoded = {
    ...address,
    ...results,
  };
  debug("Output: %o", geocoded);
  return geocoded;
}

export const geocodeCallback = util.callbackify(geocode);
