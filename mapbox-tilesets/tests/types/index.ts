export type Feature = {
  lon: string;
  lat: string;
  data_baseline_mean: number;
  data_1c_mean: number;
  data_1_5c_mean: number;
  data_2c_mean: number;
  data_2_5c_mean: number;
  data_3c_mean: number;
};

export type FeatureMap = {
  [lat: string]: Feature[];
};

export const dataAttributeNames = [
  "data_baseline_pctl10",
  "data_baseline_mean",
  "data_baseline_pctl90",
  "data_1c_pctl10",
  "data_1c_mean",
  "data_1c_pctl90",
  "data_1_5c_pctl10",
  "data_1_5c_mean",
  "data_1_5c_pctl90",
  "data_2c_pctl10",
  "data_2c_mean",
  "data_2c_pctl90",
  "data_2_5c_pctl10",
  "data_2_5c_mean",
  "data_2_5c_pctl90",
  "data_3c_pctl10",
  "data_3c_mean",
  "data_3c_pctl90",
];

export type ValidationMethod = "using-vtquery" | "using-checksums";

export type AvergageDataByLat = {
  lat: number;
  data_baseline_mean_average: number;
  data_1c_mean_average: number;
  data_1_5c_mean_average: number;
  data_2c_mean_average: number;
  data_2_5c_mean_average: number;
  data_3c_mean_average: number;
};

export type Point = {
  lon: string | number;
  lat: string | number;
};
