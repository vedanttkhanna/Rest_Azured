from __future__ import annotations
import argparse
import csv
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from solar.config import load_config
from solar.providers import GoogleSolar, ProviderError, google_key


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--locations",type=Path,default=Path(__file__).with_name("locations.csv"))
    parser.add_argument("--out",type=Path,default=Path("data/solar/coverage_delhi.json"))
    parser.add_argument("--limit",type=int,default=10)
    args=parser.parse_args()
    key=google_key()
    if not key: raise SystemExit("Configure GOOGLE_SOLAR_SSM_PARAMETER or GOOGLE_SOLAR_API_KEY; coverage not tested")
    client=GoogleSolar(key,load_config())
    results=[]
    for row in list(csv.DictReader(args.locations.open()))[:args.limit]:
        try:
            result=client.insights(float(row["lat"]),float(row["lng"]))
            record={**row,"status":"covered","quality":result.get("imageryQuality"),"imagery_date":result.get("imageryDate")}
        except ProviderError as exc:
            record={**row,"status":"not_covered" if exc.status==404 else "request_failed","http_status":exc.status}
        results.append(record)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(results,indent=2))
    print(f"Recorded {len(results)} coverage checks to {args.out}")


if __name__=="__main__":main()
