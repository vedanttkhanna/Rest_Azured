# P2 assumptions and sources

All defaults live in [config.yaml](../solar/config.yaml). The resolved configuration is copied into every report's `assumptions`; overrides are validated. This document distinguishes sourced values from design choices. Reviewed 2026-10-10.

| Area | Default and interpretation | Basis |
|---|---|---|
| Coordinates | WGS84 interchange; UTM 43N for metres; true-north azimuth corrected for grid convergence | Shared project contract |
| Simulation grid | 0.25 m cells, at least 120 m context, extended around the complete roof by the 60 m ray distance; maximum 1 million cells | P2 design and runtime limits |
| Imagery | Esri z19, 2x resampling, 512x512 centered Web Mercator tile | Existing P1 sampling geometry. ~0.13 m output pixels do **not** imply ~0.13 m source detail |
| Google imagery | BASE minimum quality, requested 0.25 m pixels, 150 m radius | [Google dataLayers API](https://developers.google.com/maps/documentation/solar/reference/rest/v1/dataLayers/get); live Delhi coverage unverified |
| Building heights | Supplied footprint height, otherwise median Open Buildings height, otherwise floor count x 3.2 m, otherwise four floors = 12.8 m | 3.2 m and four floors are project assumptions, not surveyed heights |
| Open Buildings | Optional 2023 `building_height` raster; height above terrain, not elevation above sea level | [Earth Engine dataset catalog](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1). Effective spatial detail is about 4 m; unsuitable for individual rooftop equipment |
| Obstacle heights | Tank 1.4 m; stair room 2.7; AC 0.8; heater 1.5; existing PV 1.2; parapet 1; tree 3 above roof; other 1 | Unsurveyed class defaults from the P2 brief; P1 currently mostly supplies `other`, `tree`, `existing_pv` |
| DSM | Absolute elevations resampled to the simulation grid; no additional guessed obstacles added | Avoids double-counting surface features. Missing target-roof coverage is an error; missing context generates a warning |
| Shadow receivers | Surface height plus 0.2 m mounting offset | Approximation, not a full 3D tilted-panel surface model |
| Shadow timing | 15th of each month, 24 hourly samples; actual TMY beam energy is summed by local month/hour to weight masks | P2 representative-day approximation; sample minute follows weather irradiance timestamps |
| Low sun | No local shadow calculation at or below 3 degrees solar elevation | Avoids unbounded rays; this can slightly understate local shade at dawn/dusk |
| Usable roof | 0.6 m edge setback, 0.5 m obstacle buffer, exclude cells above 20% annual beam shade | Project layout choices, not a statement of building-code compliance |
| Panels | 540 Wp; 2.278 x 1.134 m; portrait; flat-roof tilt 25 degrees | Generic module dimensions from the brief, not a selected manufacturer's datasheet |
| Orientation | Compare true south with a south-facing orientation parallel to the dominant roof edge; retain larger panel count | Actual selected orientation is used for irradiance and stored on each panel. For multiple roofs, top-level system orientation describes the largest group |
| Row spacing | Winter solstice, 09:00–15:00 **solar time**, every 15 minutes; worst projected shadow plus 0.02 m gap | Solar longitude and equation of time convert to UTC; civil-clock hours are not substituted |
| Pitched roofs | Require upstream tilt/azimuth; flush-mounted spacing based on projected length | Synthetic heights approximate the roof as level. A measured DSM is preferable for pitched-roof shading |
| Packing | Four x four grid-origin offsets, greedy non-overlapping rectangles | Deterministic heuristic, not an optimal packing guarantee; additional structural/walkway constraints are not inferred |
| Weather | PVGIS TMY cached to 0.05-degree coordinates, 8760 hourly samples, terrain horizon enabled | [pvlib PVGIS TMY API](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.iotools.get_pvgis_tmy.html). Actual database, selected years and location are retained |
| Irradiance timing | PVGIS metadata's irradiance time offset is applied to solar position and shadow grouping | Fixture PVGIS-ERA5 response reports +0.5 hours; meteorological timestamps and monthly energy integration remain hourly |
| Energy | Hay–Davies transposition; albedo 0.2; SAPM open-rack temperature coefficients a=-3.56, b=-0.075, deltaT=3; PVWatts DC gamma=-0.0035/°C | pvlib models; coefficients are configured engineering assumptions |
| Losses | 14% DC system loss **including** 5% soiling; PVWatts inverter nominal efficiency 96%; DC/AC ratio 1 | Brief defaults. Soiling is not deducted twice. Diffuse irradiance is retained under local beam shading; no electrical mismatch/bypass-diode model |
| Capital cost | INR 57,500/kW | Illustrative project assumption; not a current vendor quote |
| Electricity value | INR 7/kWh for all generation, assumed net-metering value | Illustrative assumption, not an applicable DISCOM tariff determination. No load profile/export settlement model |
| Central subsidy | Eligible residential case: INR 30,000/kW for first 2 kW, 18,000/kW for next 1 kW, cap 78,000; capped at project cost | [Delhi Solar Portal](https://solar.delhi.gov.in/page/central-subsidy), [Government scheme announcement](https://www.pmindia.gov.in/en/news_updates/cabinet-approves-pm-surya-ghar-muft-bijli-yojana-for-installing-rooftop-solar-in-one-crore-households/). Eligibility is an explicit configurable assumption, not guaranteed approval |
| Finance | Simple payback; 25-year net savings; 0.5% annual generation degradation; no loan interest, O&M, replacement cost, inflation, discounting or tariff escalation | Project model assumptions. Zero savings produces null payback |
| CO2 | 0.71 tCO2/MWh | Provisional brief value. Latest applicable [CEA baseline factor](https://www.cea.nic.in/cdm-co2-baseline-view?mappingId=234) was **not** numerically verified; do not present this as an audited emissions claim |

The simulation includes local building/obstacle shadows within the finite context. It does not simulate row-to-row electrical losses outside the row-spacing design hours, terrain outside the context beyond PVGIS's horizon correction, structural loading, wiring or inverter design, unseen obstacles, or legal installation suitability. Neighbor footprint omissions are not proof of an unobstructed horizon. Missing neighbor data and P1 warnings are propagated to the report.

Neither the generic tariff/capex nor the CO2 default has been validated as a current authoritative value. The real fixture's low shade loss is expected to be optimistic because it has no neighboring building data and P1 misses some rooftop structures. PVGIS yield comparison validates only the energy calculation, not roof area, obstacle recall or shading accuracy.
