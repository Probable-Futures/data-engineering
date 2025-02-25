import { Unit, Map } from "./types";

export const ERROR_VALUE = -99999;
export const BARREN_LAND_VALUE = -88888;
export const DATA_LAYER_ID_PREFIX = "region-";

// Update the version of the dataset before creation. Versions should be integers only.
export const DATASETS: {
  id: number;
  name: string;
  unit: Unit;
  version: string;
  map?: Map;
}[] = [
  {
    id: 10105,
    name: "GCM: Number of Days above 32°C (90°F) -- For About Maps comparison map (Behind the maps page)",
    unit: Unit.Days,
    version: "1",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40901,
    name: "Climate zones",
    unit: Unit.Class,
    version: "3",
    map: {
      stops: [
        2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
        27,
      ],
      binHexColors: [
        "#1e8245",
        "#58b368",
        "#81d895",
        "#422d1e",
        "#7f5539",
        "#947b73",
        "#c9a47e",
        "#86b9fe",
        "#007dff",
        "#0009ff",
        "#00009f",
        "#1b4965",
        "#0081a7",
        "#27adbf",
        "#74d2df",
        "#a7fafa",
        "#ffc500",
        "#ff9200",
        "#e85d04",
        "#ff0a0a",
        "#f559ba",
        "#9b2226",
        "#d14553",
        "#f67f6f",
        "#ffc7c2",
        "#5e548e",
        "#be95c4",
      ],
    },
  },
  {
    id: 40101,
    name: "Average Temperature",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40102,
    name: "Average daytime temperature",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40103,
    name: "10 hottest days",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40104,
    name: "Days above 32°C (90°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40105,
    name: "Days above 35°C (95°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40106,
    name: "Days above 38°C (100°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40107,
    name: "Days above 45°C (113°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40201,
    name: "Average nighttime temperature",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40202,
    name: "Frost nights",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40203,
    name: "Nights above 20°C (68°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40204,
    name: "Nights above 25°C (77°F)",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40205,
    name: "Freezing days",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40301,
    name: "Days above 26°C wet-bulb",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40302,
    name: "Days above 28°C wet-bulb",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40303,
    name: "Days above 30°C wet-bulb",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40304,
    name: "Days above 32°C wet-bulb",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40305,
    name: "10 hottest wet-bulb days",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40206,
    name: "10 hottest nights",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [11, 21, 34, 51, 67],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40207,
    name: "Average winter temperature",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [-20, -8, 0, 5, 20],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40601,
    name: "Change in total annual precipitation",
    unit: Unit.Millimeters,
    version: "3",
    map: {
      stops: [-100, -50, -25, 25, 50, 101],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40607,
    name: "Change in dry hot days",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [0, 8, 31, 61],
      binHexColors: ["#25a8b7", "#515866", "#ffab24", "#d98600", "#a36440"],
    },
  },
  {
    id: 40612,
    name: 'Change in frequency of "1-in-100 year" storm',
    unit: Unit.Frequency,
    version: "3",
    map: {
      stops: [1, 2, 3, 5],
      binHexColors: ["#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40613,
    name: 'Change in precipitation "1-in-100 year" storm',
    unit: Unit.Millimeters,
    version: "3",
    map: {
      stops: [-1, 12, 25, 51],
      binHexColors: ["#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40614,
    name: "Change in snowy days",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [-22, -7, -2, 1],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7"],
    },
  },
  {
    id: 40616,
    name: "Change in wettest 90 days",
    unit: Unit.Millimeters,
    version: "3",
    map: {
      stops: [-50, -25, -12, 12, 25, 51],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  // climate zones v1
  // {
  //   id: 40901,
  //   name: "Climate zones",
  //   unit: Unit.Class,
  //   version: "3",
  //   map: {
  //     stops: [12, 13, 21, 22, 31, 32, 33, 41, 42, 43, 51, 52],
  //     binHexColors: [
  //       "#1e8245",
  //       "#58b368",
  //       "#81d895",
  //       "#7f5539",
  //       "#c9a47e",
  //       "#1b4965",
  //       "#0081a7",
  //       "#74d2df",
  //       "#9b2226",
  //       "#e85d04",
  //       "#ffc7c2",
  //       "#5e548e",
  //       "#be95c4",
  //     ],
  //   },
  // },
  {
    id: 40701,
    name: "Likelihood of year-plus extreme drought",
    unit: Unit.Likelihood,
    version: "3",
    map: {
      stops: [11, 21, 34, 51, 67],
      binHexColors: ["#515866", "#baaf51", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
  },
  {
    id: 40702,
    name: "Likelihood of year-plus drought",
    unit: Unit.Likelihood,
    version: "3",
    map: {
      stops: [11, 34, 51, 68, 91],
      binHexColors: ["#515866", "#baaf51", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
  },
  {
    id: 40703,
    name: "Water balance",
    unit: Unit.ZScore,
    version: "3",
    map: {
      stops: [-1, -0.5, 0.6, 1.1],
      binHexColors: ["#ec8a00", "#ffcd29", "#515866", "#baaf51", "#66a853"],
    },
  },
  {
    id: 40704,
    name: "Change in wildfire danger days",
    unit: Unit.Days,
    version: "3",
    map: {
      stops: [-6, 7, 14, 30, 60],
      binHexColors: ["#baaf51", "#515866", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
  },
  {
    id: 40108,
    name: "Three hottest days - consecutive, ensemble maxmin",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [25, 30, 35, 40, 45],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40208,
    name: "Three coldest days - consecutive, ensemble maxmin",
    unit: Unit.Temperature,
    version: "3",
    map: {
      stops: [-45, -30, -15, 0, 15],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
];
