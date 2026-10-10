"""Public-location unshaded yield benchmark; not surveyed-building validation."""
from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
import numpy as np
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from solar.config import load_config
from solar.weather import get_weather
from solar.energy import irradiance, simulate_energy


def benchmark(row,config,cache):
    lat,lng=float(row["lat"]),float(row["lng"])
    weather,metadata=get_weather(lat,lng,config,cache/"weather")
    # Compare at the weather cache grid point so location differences do not bias validation.
    lat,lng=metadata["latitude"],metadata["longitude"]
    config["layout"]["panel_wp"]=1000
    c=config["layout"]
    poa,groups,_=irradiance(weather,lat,lng,c["tilt_deg"],c["azimuth_deg"],config)
    ours,_=simulate_energy(weather,poa,groups,np.zeros(288),1,config)
    result_path=cache/f"pvcalc_{lat:.3f}_{lng:.3f}.json"
    if result_path.exists(): reference=json.loads(result_path.read_text())
    else:
        response=requests.get(config["weather"]["api_url"]+"PVcalc",params={
            "lat":lat,"lon":lng,"peakpower":1,"loss":config["energy"]["total_system_loss_pct"],
            "angle":c["tilt_deg"],"aspect":c["azimuth_deg"]-180,"outputformat":"json",
            "pvtechchoice":"crystSi","mountingplace":"free","raddatabase":"PVGIS-ERA5",
            "usehorizon":int(config["weather"]["use_horizon"])},timeout=config["weather"]["timeout_s"])
        response.raise_for_status()
        reference=response.json()
        result_path.write_text(json.dumps(reference))
    expected=reference["outputs"]["totals"]["fixed"]["E_y"]
    actual=float(ours.sum())
    deviation=100*(actual/expected-1)
    return {**row,"weather_lat":lat,"weather_lng":lng,"ours_kwh_per_kwp":round(actual,2),
        "pvgis_kwh_per_kwp":round(expected,2),"difference_pct":round(deviation,3),
        "within_7pct":abs(deviation)<=7,"status":"computed",
        "roof_area_ours_m2":"","roof_area_hand_measured_m2":"","google_annual_kwh":"",
        "shade_loss_pct":"","building_validation":"not_run","error":""}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--locations",type=Path,default=Path(__file__).with_name("locations.csv"))
    parser.add_argument("--out",type=Path,default=Path(__file__).with_name("validation_delhi.csv"))
    args=parser.parse_args()
    rows=list(csv.DictReader(args.locations.open()))
    cache=Path("data/solar/validation"); cache.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0])+["weather_lat","weather_lng","ours_kwh_per_kwp","pvgis_kwh_per_kwp","difference_pct",
        "within_7pct","status","roof_area_ours_m2","roof_area_hand_measured_m2","google_annual_kwh",
        "shade_loss_pct","building_validation","error"]
    with args.out.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:
            try: result=benchmark(row,load_config(),cache)
            except Exception as exc:
                result={**row,"status":"failed","building_validation":"not_run","error":type(exc).__name__}
            writer.writerow(result);f.flush()
            print(row["name"],result.get("difference_pct"),result["status"],flush=True)


if __name__=="__main__":main()
