import Bottleneck from "bottleneck";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxGeocoding from "@mapbox/mapbox-sdk/services/geocoding";

import * as types from "./types";

const debug = require("debug")("mapbox");

const limiter = new Bottleneck({
  reservoir: 600,
  reservoirRefreshAmount: 500,
  reservoirRefreshInterval: 60 * 1000,
  maxConcurrent: 2,
  minTime: 200,
});

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const geocodingService = mbxGeocoding(baseClient);

let retryCount = 0;

const dbugMbxGeocodeCity = debug.extend("mbxGeocodeCity");
async function mbxGeocodeCity({
  city,
  country,
}: {
  city: types.City;
  country: types.Country;
}): Promise<types.GeocodeResults> {
  try {
    dbugMbxGeocodeCity("%o", { city, country });

    const response = await geocodingService
      .forwardGeocode({
        query: city,
        countries: [country],
        limit: 1,
        types: ["place", "locality"],
      })
      .send();

    if (response.statusCode !== 200) {
      dbugMbxGeocodeCity("FAILED:: %o", { statusCode: response.statusCode, city, country });
      throw response;
    }

    if (response.body?.features.length === 0) {
      dbugMbxGeocodeCity("NO_RESULTS:: %o", { statusCode: response.statusCode, city, country });
      throw response;
    }

    const {
      place_name,
      center: [long, lat],
    } = response.body.features[0];

    return { place_name, long, lat };
  } catch (e) {
    if (e.statusCode === 429) {
      debug("429 count: %i", ++retryCount);
      throw e;
    }
    console.error(e);
    return {
      place_name: "NOT FOUND",
      long: -9999,
      lat: -9999,
    };
  }
}

export const geocodeCity = limiter.wrap(mbxGeocodeCity);
