import { Expression } from "mapbox-gl";

export enum ModelGrid {
  RCM = "RCM",
  GCM = "GCM",
}

export enum ModelSource {
  CMIP5 = "CMIP5",
  Ensemble = "global RCM RegCM-REMO ensemble",
  RegCM = "global RegCM",
  REMO = "global REMO",
}

export enum Category {
  Heat = "Increasing Heat",
  Cold = "Decreasing cold",
  Humidity = "Heat and humidity",
  Drought = "Drought",
  Precipitation = "Precipitation",
  Fire = "Fire",
  Storm = "Tropical Storm",
}

export enum Unit {
  Days = "Count (days)",
  Temperature = "Quantity (°C)",
  Meters = "Quantity (m)",
  Millimeters = "Quantity (mm)",
  Probability = "Probability (%)",
  Likelihood = "Likelihood",
  ReturnPeriod = "Return period (1-in-X)",
  Class = "Class",
  Centimeters = "Quantity (cm)",
  Frequency = "Frequency change (X more likely/frequent)"
}

export interface DatasetToken {
  id: string;
  name: string;
  model: string;
  category: string;
  unit: Unit;
  dataset: string;
}

export interface ParsedDataset {
  id: string;
  name: string;
  model: Model;
  category: Category;
  unit: Unit;
  dataset: string;
}

export interface Model {
  source: ModelSource;
  grid: ModelGrid;
}

export type RecipeLayers = Record<string, RecipeLayer>;

export interface Recipe {
  version: number;
  layers: RecipeLayers;
}

type RecipeSimplification =
  | Expression
  | {
      distance: Expression;
      outward_only: Expression;
    };
interface RecipeUnion {
  where?: Expression;
  group_by?: string[];
  aggregate?: Record<string, string>;
  maintain_direction?: boolean;
  simplification?: RecipeSimplification;
}

export interface RecipeLayer {
  source: string;
  minzoom: number;
  maxzoom: number;
  features?: {
    id?: any;
    bbox?: [number, number, number, number];
    attributes?: {
      zoom_element?: string[];
      set?: Record<string, Expression>;
      allowed_output?: string[];
    };
    filter?: Expression;
    simplification?: RecipeSimplification;
  };
  tiles: {
    bbox?: [number, number, number, number];
    extent?: Expression;
    buffer_size?: Expression;
    limit?: [string, Expression, number, string][];
    union?: RecipeUnion[];
    filter?: Expression;
    attributes?: {
      set?: Record<string, Expression>;
    };
    order?: string;
    remove_filled?: Expression;
    id?: Expression;
    layer_size?: number;
  };
}
