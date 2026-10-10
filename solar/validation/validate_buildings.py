"""End-to-end P2 validation using unchanged P1 inference on real public imagery.

No hand-measured roof area or Google comparison is invented. Raw inputs and
reports remain in ignored data/; the small summary is a validation artifact.
"""
from __future__ import annotations
import argparse
import csv
import json
import sys
import time
from pathlib import Path
import faulthandler
faulthandler.dump_traceback_later(60, repeat=True)
print("Loading validation dependencies", flush=True)
import numpy as np
import torch
print("PyTorch imported", flush=True)
from PIL import Image
from rasterio.warp import transform_bounds
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"solar"))
sys.path.insert(0,str(ROOT/"ml/serve"))
import segment
from solar.config import load_config
from solar.fetch import fetch_job
from solar.geo import TO_METRIC, TO_WGS84, metric, make_grid, geojson
from solar.providers import fetch_footprints
from solar.report import simulate
from solar.storage import Store


def choose_building(neighbors,lat,lng):
    point=Point(*TO_METRIC(lng,lat))
    candidates=[]
    for feature in neighbors.get("features",[]):
        try: poly=metric(feature["geometry"])
        except (KeyError,ValueError): continue
        for part in getattr(poly,"geoms",[poly]):
            left,bottom,right,top=part.bounds
            # Validation selects residential-size roofs fitting P1's fixed tile.
            if 60<=part.area<=450 and max(right-left,top-bottom)<=40 and part.distance(point)<=80:
                candidates.append((part.distance(point),part))
    if not candidates: raise ValueError("No suitable building in sampling window")
    poly=min(candidates,key=lambda p:p[0])[1]
    center=poly.representative_point()
    lng,lat=TO_WGS84(center.x,center.y)
    return lat,lng,geojson(poly)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--locations",type=Path,default=Path(__file__).with_name("locations.csv"))
    parser.add_argument("--model",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=Path(__file__).with_name("building_validation_delhi.csv"))
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--footprint-timeout",type=float,default=120,help="Batch-only download timeout; production remains 35 seconds")
    args=parser.parse_args()
    store=Store(ROOT/"data/solar/building_validation")
    torch.set_num_threads(4)
    print("Loading local model", flush=True)
    model,device=segment.load_model(args.model,"cpu")
    faulthandler.cancel_dump_traceback_later()
    print("Model ready", flush=True)
    cfg=load_config()
    cfg["fetch"]["footprint_timeout_s"]=args.footprint_timeout
    locations=list(csv.DictReader(args.locations.open()))
    previous={}
    if args.resume and args.out.exists():
        previous={r["sample_id"]:r for r in csv.DictReader(args.out.open()) if r["status"]=="computed"}
    fields=["sample_id","locality","lat","lng","status","neighbor_count","roof_area_m2","usable_area_m2",
            "panel_count","kw_dc","annual_kwh","specific_yield_kwh_per_kwp","shade_loss_pct",
            "fetch_seconds","inference_seconds","simulation_seconds","heatmap_exists",
            "schema_valid","warning_count","error","hand_measured_area_m2","google_annual_kwh"]
    with args.out.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for i,row in enumerate(locations):
            jid=f"p2-validation-{i+1:02d}"
            if jid in previous:
                writer.writerow(previous[jid]);f.flush();print(jid,"cached",flush=True);continue
            record={"sample_id":jid,"locality":row["name"],"status":"failed"}
            stage="footprints"
            try:
                original_lat,original_lng=float(row["lat"]),float(row["lng"])
                grid=make_grid({"lat":original_lat,"lng":original_lng},cfg)
                # Wider selection context also covers ray extent after recentering.
                bounds=list(grid.bounds)
                bounds=[bounds[0]-100,bounds[1]-100,bounds[2]+100,bounds[3]+100]
                bounds=transform_bounds(grid.crs,4326,*bounds)
                dest=store.path(f"samples/{jid}/neighbors.geojson")
                neighbors=None
                if dest.exists():
                    try:
                        neighbors=json.loads(dest.read_text(encoding="utf-8"))
                        if not isinstance(neighbors,dict) or not isinstance(neighbors.get("features"),list):
                            neighbors=None
                    except (ValueError,OSError):
                        pass
                if neighbors is None: neighbors=fetch_footprints(bounds,dest,cfg)
                lat,lng,footprint=choose_building(neighbors,original_lat,original_lng)
                record.update(lat=lat,lng=lng,neighbor_count=len(neighbors["features"]))
                stage="fetch"
                start=time.perf_counter()
                cached=store.path(f"jobs/{jid}/job_A.json")
                if cached.exists(): job=json.loads(cached.read_text())
                else: job=fetch_job({"job_id":jid,"lat":lat,"lng":lng,"provider":"esri",
                                    "footprint":footprint,"neighbors":neighbors},store,cfg)
                record["fetch_seconds"]=round(time.perf_counter()-start,3)
                stage="inference"
                start=time.perf_counter()
                image=np.asarray(Image.open(job["image_s3_uri"]).convert("RGB"))
                probs=segment.predict_probs(model,device,image)
                segmentation=segment.to_contract_b(probs,job["image_bounds"],lat,lng,jid,
                    "segformer-b2-delhi-fp-v1",job["footprint"],image=image)
                store.put_json(f"jobs/{jid}/seg_B.json",segmentation)
                record["inference_seconds"]=round(time.perf_counter()-start,3)
                stage="simulate"
                start=time.perf_counter()
                report=simulate(job,segmentation,store,cfg)
                record["simulation_seconds"]=round(time.perf_counter()-start,3)
                record.update(status="computed",roof_area_m2=report["building"]["roof_area_m2"],
                    usable_area_m2=report["building"]["usable_area_m2"],panel_count=report["system"]["panel_count"],
                    kw_dc=report["system"]["kw_dc"],annual_kwh=report["energy"]["annual_kwh"],
                    specific_yield_kwh_per_kwp=report["energy"]["specific_yield_kwh_per_kwp"],
                    shade_loss_pct=report["energy"]["shade_loss_pct"],
                    heatmap_exists=Path(report["heatmap_png_s3_uri"]).exists(),schema_valid=True,
                    warning_count=len(report["assumptions"]["warnings"]))
            except Exception as exc:
                # Exception type/stage are enough to diagnose without exposing provider URLs.
                record["error"]=stage+":"+type(exc).__name__
            writer.writerow(record);f.flush()
            print(jid,row["name"],record["status"],record.get("panel_count"),record.get("error",""),flush=True)


if __name__=="__main__":main()
