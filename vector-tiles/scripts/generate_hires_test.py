"""
Generate synthetic 0.1° resolution GeoJSON data from existing 0.2° data.

Takes the existing 40105.geojsonld (0.2° grid, ~425K features) and splits
each polygon into 4 x 0.1° polygons with the same property values.
Output: ~1.7M features for testing Mapbox tileset limits.

Usage:
    python generate_hires_test.py
"""

import json
import os
import sys
import time

INPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "mapbox", "mts", "40105.geojsonld"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "mapbox", "mts", "40105-hires-test.geojsonld"
)


def split_polygon(coords):
    """Split a 0.2° polygon into 4 x 0.1° polygons.

    Input polygon winding order (from the data):
      top-left -> bottom-left -> bottom-right -> top-right -> top-left

    Example input:
      [[-94.7, 45.3], [-94.7, 45.1], [-94.5, 45.1], [-94.5, 45.3], [-94.7, 45.3]]

    Returns 4 polygons with the same winding order.
    """
    ring = coords[0]  # outer ring

    # Extract bounds from the polygon vertices
    lons = [p[0] for p in ring[:4]]
    lats = [p[1] for p in ring[:4]]
    min_lon = min(lons)
    max_lon = max(lons)
    min_lat = min(lats)
    max_lat = max(lats)

    mid_lon = round((min_lon + max_lon) / 2, 1)
    mid_lat = round((min_lat + max_lat) / 2, 1)

    # 4 sub-polygons, same winding: TL -> BL -> BR -> TR -> TL
    bottom_left = [[
        [min_lon, mid_lat], [min_lon, min_lat], [mid_lon, min_lat],
        [mid_lon, mid_lat], [min_lon, mid_lat]
    ]]
    bottom_right = [[
        [mid_lon, mid_lat], [mid_lon, min_lat], [max_lon, min_lat],
        [max_lon, mid_lat], [mid_lon, mid_lat]
    ]]
    top_left = [[
        [min_lon, max_lat], [min_lon, mid_lat], [mid_lon, mid_lat],
        [mid_lon, max_lat], [min_lon, max_lat]
    ]]
    top_right = [[
        [mid_lon, max_lat], [mid_lon, mid_lat], [max_lon, mid_lat],
        [max_lon, max_lat], [mid_lon, max_lat]
    ]]

    return [bottom_left, bottom_right, top_left, top_right]


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file not found: {INPUT_FILE}")
        sys.exit(1)

    print(f"Reading: {INPUT_FILE}")
    print(f"Writing: {OUTPUT_FILE}")

    start_time = time.time()
    input_count = 0
    output_count = 0

    with open(INPUT_FILE, "r") as infile, open(OUTPUT_FILE, "w") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue

            feature = json.loads(line)
            properties = feature["properties"]
            coords = feature["geometry"]["coordinates"]

            sub_polygons = split_polygon(coords)

            for sub_coords in sub_polygons:
                new_feature = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": sub_coords,
                    },
                }
                outfile.write(json.dumps(new_feature, separators=(",", ":")) + "\n")
                output_count += 1

            input_count += 1

            if input_count % 100000 == 0:
                elapsed = time.time() - start_time
                print(f"  Processed {input_count:,} features ({output_count:,} output) in {elapsed:.1f}s")

    elapsed = time.time() - start_time
    output_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)

    print(f"\nDone!")
    print(f"  Input:  {input_count:,} features")
    print(f"  Output: {output_count:,} features (expected ~{input_count * 4:,})")
    print(f"  File size: {output_size_mb:.1f} MB")
    print(f"  Time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
