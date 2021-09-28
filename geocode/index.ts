import * as fs from "fs";
import * as stream from "stream";
import * as path from "path";
import * as csv from "fast-csv";
import * as util from "util";
import * as types from "./types";
import { geocodeCallback } from "./geocode";

const pipeline = util.promisify(stream.pipeline);

function createCsvTransformStream() {
  return csv
    .format<types.AddressRow, types.GeocodedAddressRow>({ headers: true })
    .transform(geocodeCallback);
}

async function main() {
  try {
    const readStream = fs.createReadStream(
      path.resolve(__dirname, "../data/partner/mckinsey/to-geocode.csv"),
    );
    const writeStream = fs.createWriteStream(
      path.resolve(__dirname, "../data/partner/mckinsey/geocoded.csv"),
    );

    const parseStream = csv.parse({ headers: true });
    const transformStream = createCsvTransformStream();
    await pipeline(readStream, parseStream, transformStream, writeStream);
  } catch (e) {
    console.error("Error: %o", e);
  }
}

void (async function () {
  try {
    await main();
    process.exit(0);
  } catch (e) {
    process.exit(1);
  }
})();
