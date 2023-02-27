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

export type DatasetUnit =
  | "days"
  | "°C"
  | "likelihood"
  | "%"
  | "cm"
  | "mm"
  | "x as frequent"
  | "z-score"
  | "class";
