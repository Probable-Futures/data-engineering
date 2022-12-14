import mbxStyles from "@mapbox/mapbox-sdk/services/styles";
import mbxClient from "@mapbox/mapbox-sdk/lib/client";
import { URL, URLSearchParams } from "url";
import * as fs from "fs";

import { formatName, getFillColorExpresion, parseDataset, randomBetween } from "./utils";
import { DATASETS, DATA_LAYER_ID_PREFIX } from "./configs";

const env = require("dotenv").config();

if (env.error) {
  throw env.error;
}

const styleTemplate = require("./templates/style.json");
const debug = require("debug")("generateMapStyles");

const debugListStyles = debug.extend("listStyles");
const parsedDatasets = DATASETS.map(parseDataset);
const baseClient = mbxClient({ accessToken: process.env["MAPBOX_ACCESS_TOKEN"] });
const stylesService = mbxStyles(baseClient);
const mapboxUser = "probablefutures";
const dir = __dirname + "/templates/auto-generated-styles";

type Style = {
  version: number;
  bearing: number;
  created: Date;
  visibility: string;
  sources: any;
  name: string;
  protected: boolean;
  center: [];
  pitch: number;
  zoom: number;
  owner: string;
  id: string;
  modified: Date;
};

const listStyles = async (start?: string) => {
  const request = {
    ownerId: mapboxUser,
    start: start || undefined,
  };
  const { body, links } = await stylesService.listStyles(request).send();
  debugListStyles("response %O", { body });
  if (links.next?.url) {
    const url = new URL(links.next.url);
    const searchParams = new URLSearchParams(url.search);
    return body.concat(await listStyles(searchParams.get("start") ?? ""));
  }
  return body;
};

const getStyle = async (styleId: string) => {
  const { body } = await stylesService
    .getStyle({
      styleId,
    })
    .send();
  return body;
};

/**
 * This function fetches the latest styles for PF mapbox account, maps them to each dataset,
 * and saves the styles locally as json files.
 */
const generateStylesAsync = async (isGeneratingStylesForV1: boolean = false) => {
  console.log("The most recent styles will be fetched and saved locally\n");
  const styles = await listStyles();
  const maps = parsedDatasets
    .filter((dataset) => parseInt(dataset.id) > 40000)
    .map((dataset) => ({
      ...dataset,
      style: styles.find(
        (style: Style) =>
          style.name ===
          formatName({
            name: dataset.name,
            model: isGeneratingStylesForV1 ? dataset.model : undefined,
            version: dataset.version,
          }),
      ) as Style,
    }));

  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  fs.mkdirSync(dir);

  for (let i = 0; i < maps.length; i++) {
    const map = maps[i];
    const name = formatName({ name: map.name, version: map.version });
    console.log("Generating the style for %s.", map.style.name);
    const style = await getStyle(map.style.id);
    fs.writeFileSync(`${dir}/${name}.json`, JSON.stringify(style));
    await setTimeout[Object.getOwnPropertySymbols(setTimeout)[0]](randomBetween(2000, 4000));
  }
};

/**
 * This function makes multiple copies of style.json for each dataset.
 * Each copy references different tilesets and has different values for paint.fill-color based on what we are using on production.
 * The latest values for this property can be fetched from the database:
 * select dataset_id, name, stops, bin_hex_colors from pf_public.pf_maps where dataset_id > 40000;
 */
const generateStylesSync = () => {
  console.log("Generating a style file for each map. Files will be saved in %s. \n", dir);
  const datasets = parsedDatasets
    .filter((dataset) => parseInt(dataset.id) > 40000)
    .map((dataset) => ({
      east: `probablefutures.${dataset.id}-east-v${dataset.version}`,
      west: `probablefutures.${dataset.id}-west-v${dataset.version}`,
      ...dataset,
    }));

  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  fs.mkdirSync(dir);

  datasets.forEach((dataset) => {
    let { sources, layers, ...rest } = styleTemplate;
    sources.composite.url = `mapbox://${dataset.east},mapbox.mapbox-streets-v8,${dataset.west},mapbox.mapbox-terrain-v2`;
    layers.forEach((layer) => {
      if (
        dataset.map &&
        dataset.map.binHexColors &&
        dataset.map.stops &&
        layer.id.includes(DATA_LAYER_ID_PREFIX)
      ) {
        layer.paint["fill-color"] = getFillColorExpresion(
          dataset.map.binHexColors,
          dataset.map.stops,
        );
      }
    });
    const name = formatName({
      name: dataset.name,
      version: dataset.version,
    });
    const style = {
      ...rest,
      name,
      sources,
      layers,
    };
    fs.writeFileSync(`${dir}/${name}.json`, JSON.stringify(style));
  });
};

(async () => {
  try {
    await generateStylesAsync(true);
    // generateStylesSync();
    console.log("Finished!");
  } catch (error) {
    console.error("\n=+=+===+=+=+=+=+=+=FAILED=+=+===+=+=+=+=+=+=\n");
    console.error("%O", error);

    process.exit(1);
  } finally {
    process.exit(0);
  }
})();
