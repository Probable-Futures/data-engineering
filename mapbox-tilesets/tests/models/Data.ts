import { Feature, FeatureMap } from "../types";

abstract class Data {
  allFeaturesSortedAndGroupedByLatitude: FeatureMap = {};
  tileConf: number[];

  sortAndSetFeaturesMap(featuresMap: FeatureMap) {
    // convert to float in order to sort the map by latitude.
    const lats = Object.keys(featuresMap).map((k) => parseFloat(k));
    lats.sort((a, b) => a - b);

    // push the sorted lat and lon values to latFeaturesMap
    lats.forEach((lat) => {
      const latStr = lat.toFixed(1).toString();
      this.allFeaturesSortedAndGroupedByLatitude[latStr] = featuresMap[latStr].sort(
        (feature1, feature2) => parseFloat(feature1.lon) - parseFloat(feature2.lon),
      );
    });
  }

  getAverageDataPerLatitude() {
    const meanAveragePerLatitude = Object.keys(this.allFeaturesSortedAndGroupedByLatitude).map(
      (lat) => {
        const sameLatFeatures = this.allFeaturesSortedAndGroupedByLatitude[lat] as Feature[];
        const featuresDataSumPerLat = sameLatFeatures.reduce(
          (prev, feature) => {
            prev["data_baseline_mid_sum"] =
              prev["data_baseline_mid_sum"] + feature.data_baseline_mid;
            prev["data_1c_mid_sum"] = prev["data_1c_mid_sum"] + feature.data_1c_mid;
            prev["data_1_5c_mid_sum"] = prev["data_1_5c_mid_sum"] + feature.data_1_5c_mid;
            prev["data_2c_mid_sum"] = prev["data_2c_mid_sum"] + feature.data_2c_mid;
            prev["data_2_5c_mid_sum"] = prev["data_2_5c_mid_sum"] + feature.data_2_5c_mid;
            prev["data_3c_mid_sum"] = prev["data_3c_mid_sum"] + feature.data_3c_mid;

            return prev;
          },
          {
            data_baseline_mid_sum: 0.0,
            data_1c_mid_sum: 0.0,
            data_1_5c_mid_sum: 0.0,
            data_2c_mid_sum: 0.0,
            data_2_5c_mid_sum: 0.0,
            data_3c_mid_sum: 0.0,
          },
        );

        return {
          lat: parseFloat(lat),
          data_baseline_mid_average:
            featuresDataSumPerLat.data_baseline_mid_sum / sameLatFeatures.length,
          data_1c_mid_average: featuresDataSumPerLat.data_1c_mid_sum / sameLatFeatures.length,
          data_1_5c_mid_average: featuresDataSumPerLat.data_1_5c_mid_sum / sameLatFeatures.length,
          data_2c_mid_average: featuresDataSumPerLat.data_2c_mid_sum / sameLatFeatures.length,
          data_2_5c_mid_average: featuresDataSumPerLat.data_2_5c_mid_sum / sameLatFeatures.length,
          data_3c_mid_average: featuresDataSumPerLat.data_3c_mid_sum / sameLatFeatures.length,
          numberOfPointsAtThisLat: sameLatFeatures.length,
        };
      },
    );

    return meanAveragePerLatitude;
  }
}

export default Data;
