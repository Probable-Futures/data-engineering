import * as _ from "lodash";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import mbxStyles from "@mapbox/mapbox-sdk/services/styles";

import { Unit, Recipe, ParsedDataset } from "./types";

import { formatName, parseDataset } from "./utils";

const debug = require("debug")("fetchMapStyles");

const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const stylesService = mbxStyles(baseClient);

const mapboxUser = "probablefutures";

const debugListStyles = debug.extend("listStyles");
async function listStyles() {
  const { body, statusCode } = await stylesService.listStyles({ ownerId: mapboxUser }).send();
  debugListStyles("response %O", { body, statusCode });
  return body;
}

const datasets = [
  // { id: 10101, name: "Human niche", unit: Unit.Class },
  // { id: 10102, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 10103, name: "Maximum Temperature", unit: Unit.Temperature },
  // { id: 10104, name: "10 hottest days", unit: Unit.Temperature },
  // { id: 10105, name: "Days above 32°C (90°f)", unit: Unit.Days },
  // { id: 10106, name: "Days above 35°C (95°f)", unit: Unit.Days },
  // { id: 10107, name: "Days above 38°C (100°f)", unit: Unit.Days },
  // { id: 10108, name: "Hot days", unit: Unit.Days },
  // { id: 10201, name: "Minimum Temperature", unit: Unit.Temperature },
  // { id: 10202, name: "Frost nights", unit: Unit.Days },
  // { id: 10203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  // { id: 10204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 10205, name: "Freezing days", unit: Unit.Days },
  // { id: 10206, name: "Days above 15°C (59°F)", unit: Unit.Days },
  // { id: 10301, name: "Likelihood of surpassing 30°c wet-bulb", unit: Unit.Days },
  // { id: 10302, name: "Days above 26°C wet-bulb", unit: Unit.Days },
  // { id: 10303, name: "Days above 28°C wet-bulb", unit: Unit.Days },
  // { id: 10304, name: "Days above 30°C wet-bulb", unit: Unit.Days },
  // { id: 10305, name: "Days above 32°C wet-bulb", unit: Unit.Days },
  // { id: 10306, name: "10 hottest wet-bulb days", unit: Unit.Temperature },
  // { id: 10307, name: "Hot wet-bulb days", unit: Unit.Days },

  // { id: 20101, name: "Average Temperature", unit: Unit.Temperature },
  // { id: 20103, name: "10 hottest days", unit: Unit.Temperature },
  // { id: 20104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  // { id: 20201, name: "Days above 35°C (95°F)", unit: Unit.Days },
  // { id: 20202, name: "Frost nights", unit: Unit.Days },
  // { id: 20203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  // { id: 20204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  // { id: 20205, name: "Freezing days", unit: Unit.Days },

  { id: 40101, name: "Average Temperature", unit: Unit.Temperature },
  { id: 40102, name: "Average daytime temperature", unit: Unit.Temperature },
  { id: 40103, name: "10 hottest days", unit: Unit.Temperature },
  { id: 40104, name: "Days above 32°C (90°F)", unit: Unit.Days },
  { id: 40105, name: "Days above 35°C (95°F)", unit: Unit.Days },
  { id: 40106, name: "Days above 38°C (100°F)", unit: Unit.Days },
  { id: 40201, name: "Average nighttime temperature", unit: Unit.Days },
  { id: 40202, name: "Frost nights", unit: Unit.Days },
  { id: 40203, name: "Nights above 20°C (68°F)", unit: Unit.Days },
  { id: 40204, name: "Nights above 25°C (77°F)", unit: Unit.Days },
  { id: 40205, name: "Freezing days", unit: Unit.Days },
  { id: 40301, name: "Days above 26°C wet-bulb", unit: Unit.Days },
  { id: 40302, name: "Days above 28°C wet-bulb", unit: Unit.Days },
  { id: 40303, name: "Days above 30°C wet-bulb", unit: Unit.Days },
  { id: 40304, name: "Days above 32°C wet-bulb", unit: Unit.Days },
  { id: 40305, name: "10 hottest wet-bulb days", unit: Unit.Temperature },
].map(parseDataset);

(async function main() {
  const styles = await listStyles();

  const maps = datasets
    .map(({ id, category, name, unit, model }) => ({
      datasetId: id,
      category: category,
      unit,
      ...styles.find(function (style) {
        return style.name === formatName({ name, model });
      }),
      name,
    }))
    .map(({ datasetId, id, name, unit }) => ({
      datasetId: parseInt(datasetId),
      mapStyleId: `'${id}'`,
      name: `'${name}'`,
      bins: unit === Unit.Temperature ? `'{1, 8, 15, 26, 32, 60}'` : `'{1, 4, 8, 15, 29, 365}'`,
      bin_hex_colors: `'{"#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"}'`,
      status: "'published'",
    }))
    .map((pfMap) => `(${Object.values(pfMap).join(", ")}),`);

  console.log(maps);
})();
