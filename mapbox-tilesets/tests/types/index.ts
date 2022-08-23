export type Feature = {
  lon: string;
  lat: string;
  data_baseline_mid: number;
  data_1c_mid: number;
  data_1_5c_mid: number;
  data_2c_mid: number;
  data_2_5c_mid: number;
  data_3c_mid: number;
};

export type FeatureMap = {
  [lat: string]: Feature[];
};

export const dataAttributeNames = [
  "data_baseline_low",
  "data_baseline_mid",
  "data_baseline_high",
  "data_1c_low",
  "data_1c_mid",
  "data_1c_high",
  "data_1_5c_low",
  "data_1_5c_mid",
  "data_1_5c_high",
  "data_2c_low",
  "data_2c_mid",
  "data_2c_high",
  "data_2_5c_low",
  "data_2_5c_mid",
  "data_2_5c_high",
  "data_3c_low",
  "data_3c_mid",
  "data_3c_high",
];

export type ValidationMethod = "using-vtquery" | "using-checksums";

export type AvergageDataByLat = {
  lat: number;
  data_baseline_mid_average: number;
  data_1c_mid_average: number;
  data_1_5c_mid_average: number;
  data_2c_mid_average: number;
  data_2_5c_mid_average: number;
  data_3c_mid_average: number;
};

export type Point = {
  lon: string | number;
  lat: string | number;
};
