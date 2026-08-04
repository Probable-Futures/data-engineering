# Understanding the New Downscaled Climate Data

Status: **research notes** (branch `feat-hi-res-maps-experiment`).

**Who this is for:** someone who works with data but has *never* worked with climate/weather
data before. Every term is explained the first time it shows up. If a sentence uses a word
you don't know, that's a bug in this doc — tell me.

**What this document answers:** "The science team gave me 37 GB of files. What is it, what's
inside, and what do I do with it?"

Companion docs: [HI-RES-TILES.md](HI-RES-TILES.md) (how we turn map data into web-map tiles)
and the [meeting notes](downscaled-data-meeting-notes.md) (why this project exists).

---

## 1. The big picture, in everyday words

Think of a **weather map** you've seen on TV: a map of the world with a temperature at every
spot. Now imagine you have that, but:

- **not just today** — you have one value for *every year from 1961 to 2099* (past and a
  predicted future), and
- **very fine detail** — the world is chopped into a grid of tiny squares, each about
  **11 km** wide (roughly the size of a small city).

That's what this data is: **predicted weather/climate numbers, for every ~11 km square of
land on Earth, across ~140 years.**

Two things make it look strange when you first open it:

1. **The numbers aren't in units you'd expect.** Temperatures are stored in **Kelvin** (a
   scientist's temperature scale — more in §7), so a normal spring day shows up as `285`, not
   `12`. Rain is stored as a tiny decimal like `0.00002`. You have to convert. (§7 shows how.)
2. **The ocean is blank.** Every square over the sea is empty ("no data"). Only *land* has
   numbers, because the science team deliberately skipped the ocean. So ~⅔ of the map is empty.

That's really it. The rest of this doc is: where these numbers come from (§2), what format
they're in (§3), the exact grid (§4), how to read the file names (§5), a tour of the actual
folders (§6), how to convert the units (§7), how to open a file yourself (§8), and how this
connects to our maps project (§9).

---

## 2. Where these numbers come from (the climate part, slowly)

You don't need to know climate science, but three ideas make everything else click.

**Idea 1 — A "climate model" is a giant weather simulation.**
Scientists run huge physics simulations of the whole planet's atmosphere to estimate weather
far into the future. The specific simulation used here is nicknamed **`MPI-ESM1-2-HR`** —
just treat that as the brand name of the model. (It's one of many; the team picked this one.)

**Idea 2 — These simulations are "blurry," and "downscaling" sharpens them.**
The raw simulation splits the world into *big* squares (~25 km or larger). One number has to
describe a whole big area — so a square covering both a mountain and a valley gets a single
blurry average. **Downscaling** is the process of sharpening that blurry data into *smaller*
squares (here, ~11 km) so mountains, coasts, and cities show up distinctly. This whole
project *is* that sharpening exercise. ("Downscaled" in the folder name = "the sharpened
version.")

**Idea 3 — "A specific future" is baked in.**
The future isn't one fixed thing; it depends on how much greenhouse gas humanity emits.
Scientists model a few named scenarios. This data uses the high-emissions one, labeled
**`ssp585`** (read it as "the pessimistic, high-pollution future"). Everything here assumes
that scenario.

That's the whole background. From the [meeting notes](downscaled-data-meeting-notes.md):
Probable Futures wants to see whether these sharper 11 km maps are good enough to eventually
publish. This 37 GB is the first batch of that sharpened data for us to look at.

---

## 3. What format the files are in (and why it's not what you're used to)

### What our *current* maps use
Today's Probable Futures maps are stored as **GeoJSON** — a familiar format where the file
literally contains a list of **shapes** (little squares), and each square carries its
values attached to it. Geometry + values, bundled together. Easy to feed to a map.

### What this *new* data uses: "Zarr"
This new data is in a format called **Zarr**. Forget maps for a second — Zarr is just a way
to store **a big grid of raw numbers**, like an enormous spreadsheet (or a stack of
spreadsheets). It contains:

- **the numbers themselves** (e.g. a grid of 1801 × 3601 temperatures), and
- **little "ruler" lists** that say what each row and column *means* — a list of latitudes
  (`lat`), a list of longitudes (`lon`), and sometimes a list of years (`time`).

There are **no shapes and no map** inside — just numbers plus rulers telling you where each
number belongs on Earth. You rebuild the map yourself from the rulers.

**A "`.zarr`" is a folder, not a single file.** If you open one you'll see:

```
tasmax_..._1971-2010.zarr/       ← the whole thing (a folder)
├── zarr.json                    ← "table of contents": what's inside, how big
├── tasmax/                      ← the actual grid of numbers (temperatures)
├── lat/                         ← the latitude ruler  (1801 numbers)
└── lon/                         ← the longitude ruler (3601 numbers)
```

The numbers are **compressed** (squeezed to save space), which is why you can't just open
them in a text editor — you need a small bit of Python to read them (§8).

**The one-line takeaway:** this new data is *raw material* for making maps, not a map itself.
Somewhere down the line these numbers get turned back into little squares (like our current
GeoJSON) before they become a web map. That conversion is our job (or the scientist's), not
something the mapping tool does automatically.

> Small technical note for later: these are "Zarr version 3" folders. If you use a tool to
> open them, it must support Zarr v3. Old tools that expect the older "Zarr v2" layout will
> fail. (§8 uses a version that works.)

---

## 4. The grid: how the world is chopped up

Almost every file here uses the **same grid** — the same way of dicing up the planet:

- The world is cut into squares **0.1 degrees** of latitude/longitude on a side. At the
  equator that's about **11 km** — hence "11 km maps."
- Going **north-to-south** there are **1801** rows (from the North Pole `+90°` down to the
  South Pole `−90°`).
- Going **west-to-east** there are **3601** columns (from `−180°` to `+180°`).
- Multiply: **1801 × 3601 ≈ 6.5 million squares** covering the globe.

**But the ocean squares are empty.** When I measured, **about 66% of the squares are blank**
("no data" — stored as a special marker called `NaN`, short for "not a number"). Only the ~34%
that are land (~2.2 million squares) actually have numbers. The science team skipped the
ocean on purpose (it's expensive and not the point of these maps).

Why you'll care later: our [tiling plan](HI-RES-TILES.md) worries about "too many squares to
fit in a zoomed-out map tile." The good news is that two-thirds of the squares are empty, so
the real counts are lower than the worst case that plan assumes. The stress cases are
coastlines and islands, not open ocean.

---

## 5. Reading the file names

The file names look like a barcode, but each piece means something. Example:

```
tasmax_MPI-ESM1-2-HR_ww-isimip_ssp585_mean_1971-2010.zarr
```

Broken apart:

| Piece | Plain meaning |
|---|---|
| `tasmax` | **what** it measures — here, the daily **high** temperature. (The full name list is in §6.) |
| `MPI-ESM1-2-HR` | **which** climate simulation produced it (the "brand name" from §2). |
| `ww-isimip` | **how** it was processed — the recipe/method the science team used. You can ignore it. |
| `ssp585` | **which future scenario** — the high-emissions one (§2). |
| `mean_1971-2010` | this file is an **average over the years 1971–2010** (a "typical recent conditions" snapshot). |
| `day` (in other files) | this file was built from **daily** data. |

So `tasmax_..._mean_1971-2010.zarr` = "average daily-high temperature for typical recent
conditions (1971–2010), from the MPI simulation, high-emissions future."

Two words you'll keep seeing:

- **"climatology"** = a **long-term average** (e.g. the 1971–2010 average). Think "the normal,"
  like "the average July temperature in Beirut." One number per spot, no time axis.
- **"aggregate"** = a **summary number computed from lots of daily values**, e.g. "how many
  days this year were hotter than 32 °C." One number per spot *per year*.

---

## 6. A tour of the four folders

The download has four top-level folders. Here's each in plain terms, with real numbers I
pulled from the files.

### 6a. `climatologies/` — the basic ingredients, averaged

Each folder here is **one measurement, averaged over 1971–2010** → a single map (one number
per land square, no years). These are the raw building blocks.

| Folder | What it measures | Example values I measured | Units (and how to read them) |
|---|---|---|---|
| `tasmax` | daily **high** temperature | 221 to 336 | **Kelvin** — subtract 273 to get °C (so 221 K ≈ −52 °C, 336 K ≈ 63 °C) |
| `tasmin` | daily **low** temperature | 216 to 301 | Kelvin |
| `tas` | daily **average** temperature | 219 to 307 | Kelvin |
| `pr` | **precipitation** (rain/snow rate) | 0.00000002 to 0.001 | a per-second rate — multiply by 86,400 to get **mm/day** (max ≈ 91 mm/day) |
| `hurs` | **humidity** (how moist the air is) | 16 to 94 | **percent** (0–100) |
| `sfcwind` | **wind speed** | 0.1 to 15 | **metres per second** (×3.6 → km/h) |
| `rsds` | **sunshine** hitting the ground | 71 to 309 | watts per square metre (a sunlight-intensity unit) |
| `pr_bil`, `pr_con2` | precipitation, computed two different ways | — | **experiments** — the team is comparing two methods of shrinking the squares. Not new info; compare them to `pr`. |
| `temperature` | *(nothing new)* | — | I checked: this is an **exact copy of `tas`**. A convenience alias. |
| `precipitation` | *(nothing new)* | — | a copy of `pr`. |

These seven real measurements (temperature high/low/avg, rain, humidity, wind, sunshine) are
the same "raw variables" the meeting notes list.

### 6b. `annual_aggregates/` — **the actual maps we care about**

This is the important folder. Each sub-folder is **one Probable Futures map** (the heat and
water maps you know), and unlike the averages above, each one has a **value for every year
from 1961 to 2099** (140 years). So it's a stack of 140 maps — one per year — showing how
things change over time.

To show the trend, here's the **land-average value in the first year (1961) vs the last
(2099)** for each map. Watch how heat goes up and cold goes down — a good sign the data is
sensible:

| Map (folder) | 1961 | 2099 | What the number means |
|---|---|---|---|
| `average-temperature` | −5.5 | 0.0 | average temp, in **°C** (this folder is already in Celsius, unlike §6a!) |
| `average-daytime-temperature` | −1.6 | 3.7 | °C |
| `average-nighttime-temperature` | −9.2 | −3.5 | °C |
| `days-above-32c` | 31 | 69 | **how many days per year** hotter than 32 °C |
| `days-above-35c` | 17 | 41 | days/year over 35 °C |
| `days-above-38c` | 8 | 24 | days/year over 38 °C |
| `days-above-45c` | 0.2 | 4.4 | days/year over 45 °C |
| `nights-above-20c` | 51 | 88 | warm nights per year (hard to sleep) |
| `nights-above-25c` | 7 | 51 | very warm nights per year |
| `days-above-26c-wbmax` … `-32c-wbmax` | ~0–1 | rising | days/year of dangerous **humid** heat ("wet-bulb" = heat + humidity combined) |
| `ten-hottest-days` | 16 | 20 | avg temperature (°C) of the year's 10 hottest days |
| `ten-hottest-nights` | 7 | 12 | °C |
| `frost-nights` | 199 | 176 | freezing nights per year — **goes down** as it warms ✓ |
| `freezing-days` | 173 | 156 | freezing days per year — **goes down** ✓ |
| `snowy-days` | 25 | 26 | snowy days per year |
| `wettest-90-days` | 274 | 334 | rainfall total over the year's wettest 90-day stretch |

**20 maps are here so far**; the notes mention ~30 total, so expect more.

> ⚠️ Notice: temperatures in *this* folder are already in **°C**, but temperatures in the
> `climatologies/` folder (§6a) are in **Kelvin**. Same project, different units per folder.
> Always check — don't assume. (§7)

### 6c. `climatologies_diff_era5land/` — a "did we get it right?" check

Two files here (`temperature` and `precipitation`). Each is a map of the **difference between
the model's numbers and real-world observations**. ("ERA5-Land" is just the name of a
trusted real-world weather dataset — think of it as "the answer key.")

- If the model were perfect, this difference would be **zero everywhere**.
- I measured the temperature difference: **average +0.008 °C** — essentially zero. That's
  great: it means the sharpened data matches reality very closely, with no systematic
  "always too hot" or "always too cold" error.

This folder is for validation/confidence, not for making maps.

### 6d. `daily/` — the raw day-by-day data (⚠️ still downloading)

This is the biggest, most detailed folder: the **individual daily values** before they get
summarized into the yearly maps in §6b. It's enormous because it's ~140 years × 365 days ×
6.5 million squares.

**Right now it's incomplete.** As of this writing the folder holds a partial `tasmax` (daily
high temperature) download, about 13 GB so far. It **won't open yet** — the "table of
contents" file and the year/day ruler haven't finished downloading. (Earlier it briefly held
a different variable, `hurs`/humidity, which got replaced.) Once the download finishes, re-run
the check in §8. We probably only need this folder for spot-checks (e.g. "show me the daily
history at one location"), not for the maps themselves.

---

## 7. Converting the numbers to something readable

This is the part that trips everyone up first. Cheat-sheet:

| If you see… | It's stored as… | To make it human-readable… |
|---|---|---|
| a temperature ~200–340 in `climatologies/` | **Kelvin** | subtract **273.15** → °C |
| a temperature ~−40 to +40 in `annual_aggregates/` | **already °C** | nothing to do |
| a tiny rain number like `0.00002` | a per-**second** rate | multiply by **86,400** → mm/day |
| humidity 0–100 | **percent** | nothing to do |
| wind 0–15 | metres/second | ×3.6 → km/h |
| a blank / `NaN` | **"no data"** (it's ocean) | skip it / leave transparent |
| `-inf` (only in the §6c diff files) | another "no data" marker | skip it |

**The two classic mistakes:**
1. Seeing `271` and thinking it's an error — it's Kelvin, meaning −2 °C.
2. Seeing `0.00002` for rain and thinking it's basically zero — times 86,400 it's ~1.6 mm/day.

---

## 8. How to open a file yourself (copy-paste)

The tools to read Zarr aren't installed in the project's normal Python environment, and we
don't want to disturb it. Make a separate throwaway one:

```bash
python3 -m venv /tmp/zarrenv
/tmp/zarrenv/bin/pip install "zarr>=3" xarray numpy
```

Then read a file (`xarray` is the standard library for this kind of gridded data — it opens
the folder and hands you the numbers + rulers together):

```python
import xarray as xr
BASE = "/Users/moustafawehbe/work/pf-downscaled-data"

# --- open one of the "average" maps ---
ds = xr.open_zarr(f"{BASE}/climatologies/tasmax/"
                  "tasmax_MPI-ESM1-2-HR_ww-isimip_ssp585_mean_1971-2010.zarr")
print(ds)                                  # shows what's inside: the grid + the rulers

celsius = ds["tasmax"] - 273.15            # Kelvin -> Celsius
# look up the value nearest to New York City (lat 40.7, lon -74.0):
print(float(celsius.sel(lat=40.7, lon=-74.0, method="nearest")), "°C")

# --- open one of the yearly maps and pick a year ---
da = xr.open_zarr(f"{BASE}/annual_aggregates/days-above-32c/"
                  "days-above-32c_MPI-ESM1-2-HR_ww-isimip_ssp585_day.zarr")
print(da.time.values[[0, -1]])             # first and last year: 1961 ... 2099
year_2050 = da["days_above_32c"].sel(time="2050", method="nearest")
```

Every number in this doc came from exactly this. (I can save this as a reusable
`scripts/inspect_zarr.py` if you want — just ask.)

---

## 9. How this connects to our maps project

**The good news:** the grid resolution matches perfectly. Our
[tiling plan](HI-RES-TILES.md) was written for exactly this 11 km (0.1°) grid. And since the
ocean is blank, there's *less* data per map tile than that plan feared.

**The one real snag — the data is organized differently than our current maps:**

- **Our current published maps** are organized by **"warming level"** — i.e. "what the world
  looks like when it's 1 °C hotter," "…2 °C hotter," etc. Each square stores a bundle of ~35
  such values.
- **This new data** is organized by **calendar year** — "1961, 1962, … 2099." One value per
  year.

These are two different ways of slicing the same information. Converting "year" → "warming
level" is a real, separate step (it's the "recalculate warming levels" task Carlos mentions
in the notes — different scenarios reach "+2 °C" in different years, and someone has to work
out when).

**Why you should care:** our tiling plan assumes the data arrives already sliced by warming
level (like today's maps). This raw batch is *not* sliced that way. So:

> **Key question to confirm with the science team:** will the final map-ready data they send
> us already be organized by warming level (matching today's maps)? If yes, our tiling plan
> works as written. If they hand us these year-by-year files instead, converting them is
> extra work that isn't in the plan yet.

---

## 10. Questions to send the science team (Carlos)

1. Will the map-ready data be organized by **warming level** (like today's maps), or will we
   get these **year-by-year** files and convert them ourselves? *(This is the big one — §9.)*
2. Which **units** will the final maps use? (Right now the "average" files are in Kelvin but
   the yearly maps are in Celsius — inconsistent.)
3. Is **blank ocean** the intended final look, or should coastlines be filled in?
4. For precipitation, which version is the real one — `pr`, `pr_bil`, or `pr_con2`?
5. Only the high-emissions scenario (`ssp585`) is here. Do we need the other future
   scenarios too?
6. Of the ~30 total maps, how many are final? (20 are here so far.)

---

## Quick facts

- **Where it lives:** `/Users/moustafawehbe/work/pf-downscaled-data` (~37 GB, still downloading)
- **Detail level:** 11 km squares (0.1°), whole world, **land only** (~66% of squares blank)
- **Time covered:** yearly maps span 1961–2099; the "average" files cover 1971–2010
- **Future scenario:** high-emissions (`ssp585`)
- **Format:** Zarr (version 3) — a folder of compressed number-grids, read with Python's `xarray`
