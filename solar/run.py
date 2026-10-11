from __future__ import annotations
import argparse
import json
from pathlib import Path
from handlers import fetch_handler, simulate_handler
from solar.config import load_config
from solar.storage import Store
from solar.weather import get_weather


def main():
    parser=argparse.ArgumentParser(description="P2 local fetch/simulate/weather commands")
    subs=parser.add_subparsers(dest="command",required=True)
    for name in ("fetch","simulate"):
        p=subs.add_parser(name)
        p.add_argument("--event",required=True,type=Path)
        p.add_argument("--out",type=Path)
    p=subs.add_parser("weather")
    p.add_argument("--lat",type=float,required=True)
    p.add_argument("--lng",type=float,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="weather":
        weather,meta=get_weather(args.lat,args.lng,load_config(),"data/solar/weather")
        args.out.parent.mkdir(parents=True,exist_ok=True)
        weather.to_csv(args.out)
        args.out.with_suffix(".json").write_text(json.dumps(meta,indent=2))
        print(f"Saved {len(weather)} weather samples to {args.out}")
        return
    event=json.loads(args.event.read_text())
    result=(fetch_handler if args.command=="fetch" else simulate_handler)(event)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:result[k] for k in ("job_id","status","system","energy") if k in result},indent=2))


if __name__=="__main__": main()
