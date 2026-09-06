import { Unit, Map } from "./types";

export const ERROR_VALUE = -99999;
export const BARREN_LAND_VALUE = -88888;
export const DATA_LAYER_ID_PREFIX = "region-";

export type MethodUsedForMid = "mean" | "median";

/**
 * Diverging red/blue palette for the comparison maps (`--diff`), which show the new hi-res data
 * minus the currently-live map.
 *
 * A comparison map is signed around a meaningful zero — zero means "the two datasets agree" — so it
 * needs a *diverging* ramp rather than the sequential climate ramps below: hue carries the sign,
 * saturation carries the magnitude, and the neutral middle band is a real reading rather than a gap.
 * Blue = the new data is LOWER than live, red = HIGHER, following the climate convention (and
 * `RdBu_r`, which `analysis/lib.py` already uses for every static difference plot).
 *
 * Three rules, each of which a previous version of this palette broke:
 *
 * 1. **No hex here may appear in any climate ramp below.** A comparison map answers a different
 *    question from a climate map and must not be mistakable for one at a glance. The earlier ramp
 *    was assembled *deliberately* out of hexes reused from this file — it drew from the
 *    precipitation ramp (40601) and the drought ramp (40701) — and the result read as an ordinary
 *    PF map: teal on one side, orange on the other, rather than blue against red.
 * 2. **Lightest in the middle, darkest at both ends.** The neutral band is the value a good
 *    comparison map should let you skip over; if it is the darkest colour on the map (the earlier
 *    ramp put `#515866` there) then "the two datasets agree" is what dominates the view.
 * 3. **The neutral band must not resemble `#f5f5f5` or `#e6e6e6`** — `getFillColorExpresion` in
 *    `utils.ts` reserves those for the `step` default (which also catches null / outside-the-
 *    intersection cells) and for barren land. *No data* looking like *no difference* is the one
 *    confusion a comparison map must never cause, and it is why the textbook ColorBrewer `RdBu_r`
 *    centre (`#f7f7f7`) is not used here despite the sign convention following `RdBu_r`.
 *
 * Stops must stay SYMMETRIC about zero or the eye reads a bias that is not there.
 */
export const DIFF_COLORS = [
  "#08519c", // much lower than live
  "#4292c6",
  "#9ecae1",
  "#b9bfc7", // the two agree
  "#fcae91",
  "#ef3b2c",
  "#a50f15", // much higher than live
];

export const DIFF_STOPS = {
  temperature: [-2, -1, -0.3, 0.3, 1, 2], // °C
  days: [-20, -8, -2, 2, 8, 20], // days
  millimeters: [-100, -40, -10, 10, 40, 100], // mm
  percent: [-20, -8, -2, 2, 8, 20], // % points
  zScore: [-1, -0.5, -0.15, 0.15, 0.5, 1], // SPEI z-score
};

const diffMap = (stops: number[]): Map => ({ stops, binHexColors: DIFF_COLORS });

// Update the version of the dataset before creation. Versions should be integers only.
export const DATASETS: {
  id: number;
  name: string;
  unit: Unit;
  version: string;
  map?: Map;
  /** Diverging palette used by `--diff`. Only maps we build comparisons for need one. */
  diffMap?: Map;
  /**
   * Absolute-value palette used by `--absolute` / `--v3-absolute`, for the change indicators
   * republished as absolute maps — the five with an ERA5 counterpart so they can sit beside it
   * (40601, 40607, 40613, 40614, 40616), plus 40703 and 40704 for completeness.
   *
   * A separate field rather than reusing `map`, because `map` is the CHANGE ramp for these datasets
   * and the production/hi-res maps still need it. Sharing one field would break those.
   *
   * 40612 has no entry and cannot get one: its live export ships `data_baseline_mid` as null on
   * every feature, so there is no absolute baseline to add back, and the map is already a ratio
   * ("x as frequent") whose baseline is 1x by definition.
   */
  absoluteMap?: Map;
  methodUsedForMid?: MethodUsedForMid;
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
    version: "4",
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
    name: "Average temperature",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40102,
    name: "Average daytime temperature",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40103,
    name: "10 hottest days",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40104,
    name: "Days above 32°C (90°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
    methodUsedForMid: "mean",
  },
  {
    id: 40105,
    name: "Days above 35°C (95°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40106,
    name: "Days above 38°C (100°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40107,
    name: "Days above 45°C (113°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40110,
    name: "Days above 50°C (122°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40201,
    name: "Average nighttime temperature",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40202,
    name: "Frost nights",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40203,
    name: "Nights above 20°C (68°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40204,
    name: "Nights above 25°C (77°F)",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40205,
    name: "Freezing days",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 8, 31, 91, 181],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40301,
    name: "Days above 26°C (78°F) wet-bulb",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40302,
    name: "Days above 28°C (82°F) wet-bulb",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40303,
    name: "Days above 30°C (86°F) wet-bulb",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40304,
    name: "Days above 32°C (90°F) wet-bulb",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [1, 4, 8, 15, 29],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
  },
  {
    id: 40305,
    name: "10 hottest wet-bulb days",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40206,
    name: "10 hottest nights",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [1, 8, 15, 26, 32],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40207,
    name: "Average winter temperature",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [-20, -8, 0, 5, 20],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
    diffMap: diffMap(DIFF_STOPS.temperature),
  },
  {
    id: 40601,
    name: "Change in total annual precipitation",
    unit: Unit.Millimeters,
    version: "4",
    map: {
      stops: [-100, -50, -25, 25, 50, 101],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
    diffMap: diffMap(DIFF_STOPS.millimeters),
    // Dry -> wet, reusing the change ramp's warm/cool ends but dropping its neutral middle: an
    // absolute total has no meaningful zero to sit either side of. Stops are the 14th-86th
    // percentiles of the combined v3 + ERA5 land distribution, rounded.
    absoluteMap: {
      stops: [250, 450, 600, 900, 1250, 1750],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#8be1ff", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40607,
    name: "Change in dry hot days",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [0, 8, 31, 61],
      binHexColors: ["#25a8b7", "#515866", "#ffab24", "#d98600", "#a36440"],
    },
    // Cool -> hot, reusing the change ramp's own colours but dropping its neutral middle, the same
    // swap 40601 and 40616 make: an absolute count has no zero to sit either side of, and grey at
    // 1-16 days would read as "unchanged". Stops are the 14th-86th percentiles of the combined
    // v3 + ERA5 land distribution. NOTE v3 and ERA5 disagree badly here (medians 34 vs 1 day) —
    // the indicator is defined against each dataset's OWN historic 10th/90th percentiles, so its
    // absolute values are not comparable across datasets. Revisit before publishing this one.
    absoluteMap: {
      stops: [1, 16, 31, 62],
      binHexColors: ["#8be1ff", "#25a8b7", "#ffab24", "#d98600", "#a36440"],
    },
  },
  {
    id: 40612,
    name: "Change in frequency of “1-in-100-year” storm",
    unit: Unit.Frequency,
    version: "4",
    map: {
      stops: [1, 2, 3, 5],
      binHexColors: ["#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40613,
    name: "Change in precipitation “1-in-100-year” storm",
    unit: Unit.Millimeters,
    version: "4",
    map: {
      stops: [-1, 12, 25, 51],
      binHexColors: ["#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
    diffMap: diffMap(DIFF_STOPS.millimeters),
    // Dry -> wet, neutral middle dropped, as 40601 and 40616. Stops are the 14th-86th percentiles
    // of the combined v3 + ERA5 land distribution. NOTE the two halves measure DIFFERENT
    // quantities: the live map is precipitation from the 1-in-100-year 1-day event, while the ERA5
    // file and the v4 store are `wettest-day`, the annual maximum 1-day total (medians 135 vs
    // 29 mm). These stops are a compromise between the two. Revisit before publishing this one.
    absoluteMap: {
      stops: [26, 68, 116, 355],
      binHexColors: ["#ffab24", "#8be1ff", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40614,
    name: "Change in snowy days",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [-22, -7, -2, 1],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7"],
    },
    diffMap: diffMap(DIFF_STOPS.days),
    // NOT equal-count stops: most land has zero snowy days, so percentiles collapse onto 0. These
    // are meaningful thresholds instead — any snow at all, a week, a month, a season.
    absoluteMap: {
      stops: [1, 7, 30, 90],
      binHexColors: ["#515866", "#8be1ff", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  {
    id: 40616,
    name: "Change in wettest 90 days",
    unit: Unit.Millimeters,
    version: "4",
    map: {
      stops: [-50, -25, -12, 12, 25, 51],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#515866", "#25a8b7", "#007ea7", "#003459"],
    },
    diffMap: diffMap(DIFF_STOPS.millimeters),
    // 14th-86th percentiles of the combined v3 + ERA5 land distribution, rounded.
    absoluteMap: {
      stops: [120, 225, 300, 400, 550, 900],
      binHexColors: ["#a36440", "#d98600", "#ffab24", "#8be1ff", "#25a8b7", "#007ea7", "#003459"],
    },
  },
  // climate zones v1
  // {
  //   id: 40901,
  //   name: "Climate zones",
  //   unit: Unit.Class,
  //   version: "4",
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
    version: "4",
    map: {
      stops: [11, 21, 34, 51, 67],
      binHexColors: ["#515866", "#baaf51", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
    diffMap: diffMap(DIFF_STOPS.percent),
  },
  {
    id: 40702,
    name: "Likelihood of year-plus drought",
    unit: Unit.Likelihood,
    version: "4",
    map: {
      stops: [11, 34, 51, 68, 91],
      binHexColors: ["#515866", "#baaf51", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
    diffMap: diffMap(DIFF_STOPS.percent),
  },
  {
    id: 40703,
    name: "Change in water balance",
    unit: Unit.ZScore,
    version: "4",
    map: {
      stops: [-1, -0.5, 0.6, 1.1],
      binHexColors: ["#ec8a00", "#ffcd29", "#515866", "#baaf51", "#66a853"],
    },
    diffMap: diffMap(DIFF_STOPS.zScore),
    // The one absolute republish that KEEPS its neutral middle: a SPEI z-score has a real zero
    // (normal conditions), so grey in the centre is a true reading, not a gap. Stops are the
    // 14th-86th percentiles of the v3 land distribution (no ERA5 for water balance).
    //
    // NOTE this republish barely changes the map. SPEI is normalised to the baseline period, so the
    // live absolute baseline is ~0 everywhere (median 0.0, full range -0.2..0.3) and
    // absolute = change + ~0, i.e. within one bin. Built for completeness, not because it differs.
    absoluteMap: {
      stops: [-0.5, -0.1, 0.1, 0.4],
      binHexColors: ["#ec8a00", "#ffcd29", "#515866", "#baaf51", "#66a853"],
    },
  },
  {
    id: 40704,
    name: "Change in wildfire danger days",
    unit: Unit.Days,
    version: "4",
    map: {
      stops: [-6, 7, 14, 30, 60],
      binHexColors: ["#baaf51", "#515866", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
    absoluteMap: {
      stops: [16, 18, 21, 24, 30],
      binHexColors: ["#baaf51", "#515866", "#ffcd29", "#ec8a00", "#f24822", "#922912"],
    },
  },
  {
    id: 40108,
    name: "Three hottest days - consecutive, ensemble maxmin",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [25, 30, 35, 40, 45],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
  {
    id: 40208,
    name: "Three coldest days - consecutive, ensemble maxmin",
    unit: Unit.Temperature,
    version: "4",
    map: {
      stops: [-45, -30, -15, 0, 15],
      binHexColors: ["#515866", "#0ed5a3", "#0099e4", "#8be1ff", "#ff45d0", "#d70066"],
    },
  },
];
