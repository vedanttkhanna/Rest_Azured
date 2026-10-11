from __future__ import annotations
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator
from shapely.ops import unary_union
from .geo import metric, geojson, make_grid, check_location
from .heights import build_heights
from .shading import representative_shadows, weighted_shade, heatmap_png
from .layout import orientations, usable_polygon, pack_panels
from .energy import irradiance, simulate_energy, summarize_energy
from .finance import calculate_finance
from .weather import get_weather, validate_weather
from .storage import job_id

SCHEMAS=Path(__file__).resolve().parents[1]/"contracts"/"schemas"
if not SCHEMAS.exists(): SCHEMAS=Path(__file__).resolve().parents[2]/"contracts"/"schemas"


def validate_inputs(job,segmentation,config):
    job_id(job["job_id"])
    check_location(job["lat"],job["lng"],config)
    Draft202012Validator(json.loads((SCHEMAS/"B.schema.json").read_text())).validate(segmentation)
    if job["job_id"]!=segmentation["job_id"]: raise ValueError("A and B job IDs differ")
    roofs,obstacles=[],[]
    ids=set()
    for f in segmentation["features"]:
        p=f["properties"]
        if p["id"] in ids: raise ValueError("Duplicate feature ID")
        ids.add(p["id"])
        item={"id":p["id"],"polygon":metric(f["geometry"]),"properties":p}
        (roofs if p["kind"]=="roof" else obstacles).append(item)
    if not roofs: raise ValueError("No roof found; cannot produce a solar assessment")
    ids={r["id"] for r in roofs}
    for o in obstacles:
        if o["properties"]["roof_id"] not in ids: raise ValueError("Obstacle refers to unknown roof")
        parent = next(r["polygon"] for r in roofs if r["id"] == o["properties"]["roof_id"])
        if o["properties"]["class"] != "tree" and not parent.buffer(0.05).covers(o["polygon"]):
            raise ValueError("Obstacle geometry lies outside its parent roof")
        height = o["properties"].get("height_m")
        if height is not None and not np.isfinite(height): raise ValueError("Nonfinite obstacle height")
    union=unary_union([r["polygon"] for r in roofs])
    if sum(r["polygon"].area for r in roofs)-union.area>1e-5:
        raise ValueError("Roof polygons overlap")
    return roofs,obstacles


def simulate(job,segmentation,store,config,weather=None,weather_metadata=None,neighbors=None,
             building_heights_path=None):
    roofs,obstacles=validate_inputs(job,segmentation,config)
    prefix=f"jobs/{job['job_id']}/"
    warnings=[]
    if segmentation.get("warning"): warnings.append(segmentation["warning"])
    raw=store.get_optional(prefix+"fetch_metadata.json")
    fetch_meta=json.loads(raw) if raw else {}
    warnings.extend(fetch_meta.get("warnings",[]))
    if neighbors is None:
        raw=store.get_optional(prefix+"neighbors.geojson")
        neighbors=json.loads(raw) if raw else {"type":"FeatureCollection","features":[]}
    if building_heights_path is None and fetch_meta.get("building_heights_uri"):
        building_heights_path=store.materialize(fetch_meta["building_heights_uri"])
    grid=make_grid(job,config,[r["polygon"] for r in roofs])
    dsm=store.materialize(job["dsm_s3_uri"]) if job.get("dsm_s3_uri") else None
    height,height_source,height_warnings=build_heights(grid,roofs,obstacles,neighbors,config,dsm,building_heights_path,
        dsm_source="google_solar_dsm" if job.get("imagery_source")=="google_solar" else "supplied_dsm")
    warnings.extend(height_warnings)
    if weather is None:
        weather,weather_metadata=get_weather(job["lat"],job["lng"],config,store.root/"weather",store)
    validate_weather(weather)
    weather = weather.copy()
    if weather_metadata is None: weather_metadata={"source":"supplied_weather"}
    weather.attrs["irradiance_time_offset_hours"] = weather_metadata.get("pvgis",{}).get("inputs",{}).get("location",{}).get("irradiance_time_offset",weather.attrs.get("irradiance_time_offset_hours",0))
    offset = pd.Timedelta(hours=weather.attrs["irradiance_time_offset_hours"])
    representative_minute = (weather.index[0]+offset).tz_convert(config["geo"]["timezone"]).minute
    receivers=grid.mask([r["polygon"] for r in roofs])
    rows,cols,masks=representative_shadows(height,grid,receivers,job["lat"],job["lng"],config,representative_minute)
    heatmap=np.zeros(grid.shape,dtype="float32")
    all_panels=[]
    orientation_details=[]
    shaded_total=np.zeros(len(weather))
    unshaded_total=np.zeros(len(weather))
    usable_area=0.0
    for roof in roofs:
        obs=[o["polygon"] for o in obstacles if o["properties"]["roof_id"]==roof["id"]]
        best=None
        for tilt,azimuth in orientations(roof["polygon"],roof["properties"],config,grid.convergence):
            poa,groups,weights=irradiance(weather,job["lat"],job["lng"],tilt,azimuth,config)
            shade=weighted_shade(grid,rows,cols,masks,weights)
            usable=usable_polygon(roof["polygon"],obs,grid,shade,config)
            panels,pitch=pack_panels(usable,job["lat"],job["lng"],tilt,azimuth,config,
                                    roof["properties"]["roof_type"]=="pitched",grid.convergence)
            candidate=(panels,tilt,azimuth,poa,groups,shade,usable,pitch)
            if best is None or len(panels)>len(best[0]): best=candidate
        panels,tilt,azimuth,poa,groups,shade,usable,pitch=best
        usable_area+=usable.area
        roof_mask=grid.mask([roof["polygon"]])
        heatmap[roof_mask]=shade[roof_mask]
        # Each panel contributes equally, even when raster cell counts differ.
        group_shade=np.zeros(288)
        for panel in panels:
            mask=grid.mask([panel])[rows,cols]
            if not mask.any(): raise ValueError("Grid resolution is too coarse to sample a panel")
            individual=masks[:,mask].mean(axis=1)
            group_shade+=individual
            all_panels.append({"type":"Feature","geometry":geojson(panel),"properties":{
                "id":f"p{len(all_panels)+1}","roof_id":roof["id"],"panel_wp":config["layout"]["panel_wp"],
                "tilt_deg":round(tilt,4),"azimuth_deg":round(azimuth,4),
                "annual_beam_shade_fraction":round(float(np.mean(shade[grid.mask([panel])])),4)}})
        if panels: group_shade/=len(panels)
        shaded,baseline=simulate_energy(weather,poa,groups,group_shade,len(panels),config)
        shaded_total+=shaded
        unshaded_total+=baseline
        orientation_details.append({"roof_id":roof["id"],"panel_count":len(panels),"tilt_deg":round(tilt,4),
                                    "azimuth_deg":round(azimuth,4),"row_pitch_m":round(pitch,4)})
    count=len(all_panels)
    kw=count*config["layout"]["panel_wp"]/1000
    energy=summarize_energy(weather,shaded_total,unshaded_total,kw,config)
    finance,co2=calculate_finance(kw,energy["annual_kwh"],config)
    main=max(orientation_details,key=lambda r:r["panel_count"])
    if not count: warnings.append("No panels fit the configured setbacks, spacing and shade threshold")
    if len({(o["tilt_deg"],o["azimuth_deg"]) for o in orientation_details})>1:
        warnings.append("System orientation summarizes the largest panel group; individual orientations are in panel properties")
    warnings.append("Small rooftop obstacles may be missed by segmentation; survey required before installation")
    heatmap_file=store.path(prefix+"shade.png")
    bounds=heatmap_png(heatmap_file,grid,heatmap,receivers)
    heatmap_uri=store.publish(prefix+"shade.png",heatmap_file,"image/png")
    assumptions=copy.deepcopy(config)
    assumptions.update({"warnings":list(dict.fromkeys(warnings)),"roof_systems":orientation_details,
        "shading_method":"12 monthly representative days, hourly; actual TMY beam-weighted month/hour groups",
        "energy_method":"hourly Hay-Davies POA, SAPM temperature, PVWatts DC/inverter; beam-only geometric shading",
        "shading_limits":"flat terrain fallback; no local shadow calculation below minimum solar elevation; representative monthly sun paths; receiver at surface plus mount offset; no electrical mismatch/bypass-diode model, inter-row loss simulation outside design hours, or terrain outside context",
        "weather_metadata":weather_metadata,"fetch_metadata":fetch_meta,
        "finance_basis":"illustrative tariff/capex; residential subsidy eligibility assumed when enabled; no financing, O&M or tariff escalation",
        "representative_minute_local":representative_minute,"utm_meridian_convergence_deg":grid.convergence,
        "soiling_included_in_total_loss":True,"system_orientation_summary":"largest panel group"})
    report={"job_id":job["job_id"],"status":"done",
        "building":{"roof_area_m2":round(sum(r["polygon"].area for r in roofs),3),"usable_area_m2":round(usable_area,3)},
        "system":{"panel_count":count,"panel_wp":config["layout"]["panel_wp"],"kw_dc":round(kw,6),
                  "tilt_deg":main["tilt_deg"],"azimuth_deg":main["azimuth_deg"]},
        "panels":{"type":"FeatureCollection","features":all_panels},"energy":energy,"finance":finance,
        "co2_t_per_year":co2,"heatmap_png_s3_uri":heatmap_uri,"heatmap_bounds":bounds,
        "assumptions":assumptions,"data_sources":{"weather":weather_metadata["source"],"heights":height_source,
                   "imagery":job.get("imagery_source","unknown"),"footprints":"supplied_or_overture"},
        "model_version":segmentation["model_version"]}
    Draft202012Validator(json.loads((SCHEMAS/"C.schema.json").read_text())).validate(report)
    store.put_json(prefix+"report_C.json",report)
    return report
