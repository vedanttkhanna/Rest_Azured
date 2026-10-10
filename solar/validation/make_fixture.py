"""Generate the integration fixture using real cached PVGIS weather (network if absent)."""
from __future__ import annotations
import json
import shutil
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw
from pyproj import Transformer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from handlers import simulate_handler

ROOT=Path(__file__).resolve().parents[2]


def preview(job,seg,report,dest):
    image=Image.open(ROOT/"contracts/fixtures/rgb.png").convert("RGB").resize((768,768))
    left,right=image.copy(),image.copy()
    merc=Transformer.from_crs(4326,3857,always_xy=True)
    b=job["image_bounds"]
    x0,y0=merc.transform(b[0],b[1]);x1,y1=merc.transform(b[2],b[3])
    def points(geometry):
        return [((x-x0)/(x1-x0)*768,(y1-y)/(y1-y0)*768) for x,y in
                [merc.transform(*p) for p in geometry["coordinates"][0]]]
    for f in seg["features"]:
        color="yellow" if f["properties"]["kind"]=="roof" else "red"
        ImageDraw.Draw(left).line(points(f["geometry"]),fill=color,width=3)
    for f in report["panels"]["features"]:
        ImageDraw.Draw(right).polygon(points(f["geometry"]),fill="#177eb0",outline="white",width=2)
    out=Image.new("RGB",(1536,840),"#142332")
    out.paste(left,(0,50));out.paste(right,(768,50))
    d=ImageDraw.Draw(out)
    d.text((16,16),"P1: roof (yellow), detected obstacles (red)",fill="white")
    d.text((784,16),f"P2: {report['system']['panel_count']} panels; actual panel orientation is used for energy",fill="white")
    d.text((16,820),"Diagnostic only: fixture lacks neighbor geometry; undetected obstacles are not automatically excluded.",fill="white")
    out.save(dest)


def main():
    start=time.perf_counter()
    report=simulate_handler({"A":"contracts/fixtures/job_A.json","B":"contracts/fixtures/seg_B.json"})
    elapsed=time.perf_counter()-start
    fixture=ROOT/"contracts/fixtures"
    shutil.copyfile(report["heatmap_png_s3_uri"],fixture/"shade_C.png")
    report["heatmap_png_s3_uri"]="contracts/fixtures/shade_C.png"
    (fixture/"report_C.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    job=json.loads((fixture/"job_A.json").read_text())
    seg=json.loads((fixture/"seg_B.json").read_text())
    preview(job,seg,report,ROOT/"solar/validation/fixture_preview.png")
    print(json.dumps({"seconds":round(elapsed,3),"system":report["system"],"energy":report["energy"],
                      "finance":report["finance"],"sources":report["data_sources"]},indent=2))


if __name__=="__main__":main()
