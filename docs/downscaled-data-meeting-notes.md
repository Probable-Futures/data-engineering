## **Executive Summary of Project**

After the [meeting on April 7](#apr-7,-2026-|-downscaling-project-discussion)  and subsequent discussion in Slack direct messages, the group decided on the following path forward. 

We will proceed with doing a statistical downscaling experiment, starting with one CMIP6 model and all maps. This will use the variables: tasmax, tasmin, precip, relative humidity, wind speed, and solar radiation (surface downwelling). We're thinking of using the MPI model that both ISIMIP and REMO use. 

We will create maps that are 11km squared. With this level of resolution, the computing cost will be approximately $3000 to do the downscaling for all maps, plus about $372 to recalculate all maps. These are conservative estimates so we do not expect computing costs to exceed these amounts. Woodwell will do these calculations on their own Google Cloud account, for efficiency, since the code that will be used already exists in this account. 

Carlos will work on the project three days a week. The project will take about 12 weeks, starting April 20, 2026, and implying a completion date of July 13\. 

Details to note: This will include all 30 Probable Futures maps, including heat, precipitation, drought, and fire. The 100-year storm maps will be done with a simple 99th percentile calculation. 

## **Apr 7, 2026 | [Downscaling project discussion](https://www.google.com/calendar/event?eid=NnJoNXY2cnZsYTd0ajJxbWdxa2VsaGkwaWkgcGNyb2NlQHByb2JhYmxlZnV0dXJlcy5vcmc)** {#apr-7,-2026-|-downscaling-project-discussion}

Attendees: [Alison Smart](mailto:asmart@probablefutures.org) [cdobler@woodwellclimate.org](mailto:cdobler@woodwellclimate.org) [Christopher Schwalm](mailto:cschwalm@woodwellclimate.org) [Peter Croce](mailto:pcroce@probablefutures.org) [Spencer Glendon](mailto:sglendon@probablefutures.org)

**Background**  
PF is interested in exploring statistical downscaling in some depth. This would involve doing CMIP6 statistical downscaling with our existing maps. We would digitize these (like our existing maps) and make them available to our internal team. After having time to use them internally and comparing them to our dynamical maps and considering how each represents tipping points and other nonlinearities, we would consider the question of whether or not we would like to publish them online or use them externally in other ways, such as in presentations. As part of this process, we would consider different narratives to accompany different map options, such as “this is the best option of what the future could look like.”

Worth noting that the difference between dynamical and statistical downscaling will blur with CMIP7. Emulators will play a part. 

Questions

- What would be the time investment to do this?   
- Would we need a different team? More of Carlos’s time? More of Carlos plus more of someone else’s time?  
- Is the current resolution good enough?  
- What kinds of downscaling algorithms are worth considering? 

Carlos’s time estimate, sent via Slack, plus notes: 

* Setting up the code: 80 hrs (10 days) of Carlos' time. This entails writing scripts to download and prepare GCM and ERA5 data, run the downscaling pipeline, and save results.   
* Downscaling 4 variables from 1 GCM, 1 SSP: 384 computing hours (16 days). This is the amount of time needed for a cloud instance of \~14 cores and \~50GB RAM to downscale 130 years of daily data globally at 1/4 degree resolution (\~22 km). During this time, I am just babysitting the instance, making sure it is continuously running. This computing time could be reduced by using more instances simultaneously. Meanwhile, it will increase depending on the number of GCMs we want to downscale  
* Depending on the downscaling algorithm, we may need to recalculate warming levels' breaching years. The issue is that the bias-adjustment step alters the warming signal from the original GCM, so we need to recalculate the warming trend for every downscaled model, with a special modification to account for oceans, which we won't downscale. That would take 40 hrs (5 days) of Carlos' time. This step would be skipped if we choose an algorithm without bias adjustment.  
* If the end goal is to reproduce the heat and water volumes, this would entail adapting the existing code, which would take 40 hrs (5 days) of Carlos' time, plus 160 hrs of computing time to calculate all the stress metrics.  
  * TOTALS reflected above: 20 work days, 22.6 babysitting days (+ \~$600 AWS cost, includes four variables: TASMAX, TAXMIN, PRECIP, RELHUM; for dryness we’d need WIND, SNOW? Others?  
  * Rough estimates  
  * Never done this before globally and with this many models. Typically downscale a small area of the world.  
  * Open source ERA5 downscaled data is limited to temp and sometimes others. ISI MIP has some stuff but it’s limited to a subset of models. 

Next steps discussion 

- How many models are in the ensemble?   
  - What’s the sweet spot? 5? 30?   
  - Let’s look at some others and compare them to decide: is this worth doing? If so, how many models would we need to include?   
- What resolution?   
  - 9-11km would be our recommendation   
  - It’s a norm and there’s material gain from that level of precision 

Action items

- [ ] Carlos  will look at other products available to help us answer the questions: Is this worth doing? If so, what is the sweet spot for the number of models to include? 5? 30? We can think expansively about this.   
- [ ] What resolution would we want to do? We decided on the call that we would do between 9 and 11km. It's increasingly a norm, and there's material gain from that level of precision (compared to our existing maps at 22km).   
- [ ] What variables would we need to include? The existing \~$600/mo for compute cost reflects one model at 22km for TASMAX, TAXMIN, PRECIP, RELHUM. To do dryness maps, we'd need others too (Carlos will check which, suspects WIND, SNOW, others?)  
- [ ] Carlos will provide updated compute estimate based on using all variables and the decision to \~halve the resolution.

## **Jul 22, 2026 Carlos, Richard, Moustafa, Peter notes**

Raw variables: 

- tmax, tmin, tavg, wind, precip, min rel hu, solar radiation

Analysis features

- Compare with observational data (which is only raw variables)   
  - Observational ()   
    - Select raw variable  
    - Select time window to compare (1970 \- 2025\)  
  - Projections (  
  - Histograms (single location)   
  - Difference maps  
- Compare projections (e.g. old maps) vs projections (e.g. new maps)   
- Compare the variables directly   
- Difference maps: blue and red for higher and lower

Map comparisons

- Regrid with nearest neighbor – using the grid of the new maps, which is higher res