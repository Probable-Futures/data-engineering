# Downscaling project — meeting notes, 2026

Raw minutes, kept for the record and ordered by date. **Append-only.** The decisions that still
matter are distilled under "Project background" in
[`../decisions-and-status.md`](../decisions-and-status.md); when something here is superseded, note
it there rather than editing the minutes.

Figures below are as recorded on the day. Several were revised later in the same document — those
are marked inline.

## Executive summary

After the [April 7 meeting](#apr-7-2026--downscaling-project-discussion) and subsequent discussion
in Slack, the group decided on the following path forward.

We will proceed with a statistical downscaling experiment, starting with one CMIP6 model and all
maps. It will use the variables tasmax, tasmin, precipitation, relative humidity, wind speed and
solar radiation (surface downwelling). We are thinking of using the MPI model that both ISIMIP and
REMO use.

We will create maps that are 11 km squared. At that resolution the computing cost will be
approximately **$3,000** to do the downscaling for all maps, plus about **$372** to recalculate all
maps. These are conservative estimates, so we do not expect to exceed them. Woodwell will run the
calculations on their own Google Cloud account, since the code already exists there.

Carlos will work on the project three days a week. The project will take about 12 weeks, starting
April 20, 2026, implying a completion date of July 13.

Details to note: this will include all 30 Probable Futures maps — heat, precipitation, drought and
fire. The 100-year storm maps will be done with a simple 99th-percentile calculation.

## Apr 7, 2026 — downscaling project discussion

Attendees: Probable Futures (Alison, Peter, Spencer) and Woodwell (Carlos, Christopher).

### Background

PF is interested in exploring statistical downscaling in some depth. This would involve doing CMIP6
statistical downscaling with our existing maps. We would digitize these (like our existing maps) and
make them available to our internal team. After having time to use them internally, comparing them
to our dynamical maps, and considering how each represents tipping points and other nonlinearities,
we would consider whether we would like to publish them online or use them externally in other ways,
such as in presentations. As part of that we would consider different narratives to accompany
different map options, such as "this is the best option of what the future could look like".

Worth noting that the difference between dynamical and statistical downscaling will blur with CMIP7.
Emulators will play a part.

### Questions raised

- What would be the time investment to do this?
- Would we need a different team? More of Carlos's time? More of Carlos plus someone else's time?
- Is the current resolution good enough?
- What kinds of downscaling algorithms are worth considering?

### Carlos's time estimate (sent via Slack), plus notes

- **Setting up the code: 80 hrs (10 days)** of Carlos's time. Writing scripts to download and
  prepare GCM and ERA5 data, run the downscaling pipeline, and save results.
- **Downscaling 4 variables from 1 GCM, 1 SSP: 384 computing hours (16 days).** That is the time a
  cloud instance of ~14 cores and ~50 GB RAM needs to downscale 130 years of daily data globally at
  1/4 degree resolution (~22 km). During this time Carlos is babysitting the instance, making sure
  it keeps running. The computing time could be reduced by using more instances simultaneously, and
  will increase with the number of GCMs we want to downscale.
- **Recalculating warming levels' breaching years: 40 hrs (5 days)**, depending on the algorithm.
  The bias-adjustment step alters the warming signal from the original GCM, so the warming trend has
  to be recalculated for every downscaled model, with a special modification to account for oceans,
  which we will not downscale. This step would be skipped with an algorithm that has no bias
  adjustment.
- **Reproducing the heat and water volumes: 40 hrs (5 days)** of Carlos's time to adapt the existing
  code, plus 160 hrs of computing time to calculate all the stress metrics.
- Totals: 20 work days, 22.6 babysitting days, plus **~$600 AWS cost** — covering four variables
  (TASMAX, TASMIN, PRECIP, RELHUM); for dryness we would need WIND, SNOW, possibly others.
  *(Superseded: this figure was for one model at 22 km on AWS. The decision taken the same day was
  9–11 km on Woodwell's GCP account, re-estimated at ~$3,000 plus ~$372 — see the executive summary
  above.)*
- These are rough estimates. Never done this before globally and with this many models — typically
  only a small area of the world is downscaled.
- Open-source ERA5 downscaled data is limited to temperature and sometimes others. ISIMIP has some,
  but it is limited to a subset of models.

### Next steps discussion

- How many models are in the ensemble?
  - What is the sweet spot? 5? 30?
  - Let's look at some others and compare them to decide: is this worth doing? If so, how many
    models would we need to include?
- What resolution?
  - 9–11 km would be our recommendation.
  - It is a norm, and there is material gain from that level of precision.

### Action items

- Carlos will look at other products available to help answer: is this worth doing, and if so what
  is the sweet spot for the number of models to include? 5? 30? We can think expansively about this.
- What resolution would we want? We decided on the call that we would do between 9 and 11 km. It is
  increasingly a norm, and there is material gain from that level of precision compared to our
  existing maps at 22 km.
- What variables would we need to include? The existing ~$600/mo compute cost reflects one model at
  22 km for TASMAX, TASMIN, PRECIP, RELHUM. Dryness maps would need others too — Carlos will check
  which, and suspects WIND and SNOW among them.
- Carlos will provide an updated compute estimate based on using all variables and the decision to
  roughly halve the resolution.

## Jul 22, 2026 — Carlos, Richard, Moustafa, Peter

### Raw variables

tmax, tmin, tavg, wind, precipitation, minimum relative humidity, solar radiation.

### Analysis features wanted

- Compare with observational data (which is only raw variables): select a raw variable, and select a
  time window to compare (1970–2025).
- Compare projections (e.g. old maps) against projections (e.g. new maps).
- Compare the variables directly.
- Histograms at a single location.
- Difference maps: blue and red for higher and lower.

### Map comparisons

- Regrid with nearest neighbour, using the grid of the new maps, which is higher resolution.
