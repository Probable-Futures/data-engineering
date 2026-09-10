# ERA5 — what it is and how we process it

## What it is

**Reanalysis: the closest thing to observed reality on a grid.** Real measurements — weather
stations, satellites, buoys — fed through a weather model that fills the gaps between them,
producing a best estimate of what actually happened. Not a forecast, not a climate simulation.

That makes it the only dataset here that can tell us whether our published maps are *right*. v3 and
v4 are both models: comparing them shows they disagree, not which one is closer to the truth.

**Only two warming levels (0.5 and 1.0).** A warming level is "the world when global temperature was
X°C above pre-industrial". Observations only reach ~1.2 °C, so there is no observed 2 °C or 3 °C
world to aggregate.

## What we have

`~/work/pf-downscaled-data/era5/` — 24 netCDF files, one per indicator, `era5_{slug}_wls.nc`.

| | |
|---|---|
| Grid | 721 × 1440 at **0.25°**, longitude on the **0–360** convention |
| Warming levels | 0.5 and 1.0 only |
| Statistics | `mean` + percentiles (two different naming schemes — see gotchas) |
| Coverage | 57.1% of the globe. All land **except Antarctica**, plus some ocean |
| Covers | 24 PF maps, including 40607 (dry hot days), which v4 lacks |
| Does not cover | drought (40701/40702), water balance (40703), wildfire (40704), climate zones (40901), storm frequency (40612) |

## How we process it

[`era5.py`](../hires-maps/src/hires_maps/era5.py) reads the files and normalises the four ways they
differ from our Zarr data:

1. **netCDF, not Zarr** — the only netCDF this package reads.
2. **Longitude rolled** from 0–360 to −180…180, and re-sorted.
3. **Kelvin → °C** on the six temperature files.
4. **Statistic names resolved** per file, since there are two schemes.

[`era5_builder.py`](../hires-maps/src/hires_maps/geojson/era5_builder.py) then writes the map. No
transform and no change-from-baseline step: ERA5 values are absolute and already in map units. Six
properties per cell (2 levels × low/mid/high), truncated to integers exactly as the live maps are, so
an ERA5 popup is directly comparable to a published one.

Output: `data/mapbox/mts/era5-geojson/{live_id}-era5[-pNN].geojsonld`, ~593k features per map.

```
hires-maps era5-coverage          # what can be built, and what blocks the rest
hires-maps era5-map <slug>        # one map, native 0.25°
hires-maps era5-map-pyramid <slug>   # 0.25° + 0.5° + 1.0°
hires-maps era5-map-all
```

## Gotchas

- **`ten-hottest-wb-days` is already in °C** while the other five temperature files are Kelvin. Every
  naming heuristic gets this wrong; `era5.KELVIN_SLUGS` lists the six explicitly.
- **`perc05` vs `perc_5`.** The 19 heat files use `perc05`/`perc50`/`perc95`; the five water files use
  `perc_5`/`perc_50`/`perc_95`. Same meaning, different spelling — detected per file.
- **Slugs differ from v4's** for the five wet-bulb maps (`days-above-26c-wb` vs
  `days-above-26c-wbmax`). `era5.file_slug()` translates.
- **0.25° divides into neither 0.2° nor 0.1°**, so the integer-tenths lookup in `livemaps.py` does not
  apply. ERA5 uses its own exact lookup in units of 0.025°.
- **Antarctica is blank** on every ERA5 map — 30% of v4's land cells.
- **The ocean gaps are ~5° rectangles**, which looks like tile-wise processing rather than a real
  mask. Harmless for maps, but unconfirmed with Carlos.

## The comparison maps

ERA5 is also the yardstick for two comparison families, both built —
[`era5_diff_builder.py`](../hires-maps/src/hires_maps/geojson/era5_diff_builder.py):

| Variant | Value | Grid | Question |
|---|---|---|---|
| `era5v3` | `v3 − ERA5` | v3's 0.2°, one rung | how wrong is the map we publish today |
| `era5v4` | `v4 − ERA5` | v4's 0.1°, three rungs | is the new data closer to reality |

Positive (red) means **we** read higher than was observed, matching the `diff` family's convention.
Run both and the migration argument becomes a number rather than an assertion.

## See also

- [commands.md](commands.md) — every ERA5 build and publish command, with the batches actually run.
- [era5-and-gcm-maps.md](era5-and-gcm-maps.md) — the plan these were built from, what is in the raw
  files, and why the GCM data is deferred.
