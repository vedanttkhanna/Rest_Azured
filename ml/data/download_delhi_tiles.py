"""Download 512x512 satellite tiles for Delhi localities from Esri World Imagery (XYZ tile service).

Verified 2026-10-10: Esri's best zoom over Delhi is 19 (~0.26 m/px); zoom 20 returns a
"Map data not yet available" placeholder, and the MapServer/export endpoint returns HTTP 500.

--scale 1: each output = 2x2 source tiles stitched (512 px at ~0.26 m/px)
--scale 2: each output = 1 source tile upsampled to 512 px (~0.13 m/px) — closer to RID's ~0.1 m/px,
           so roofs appear at the size the RID-trained model expects (no new detail is added).

Each tile is saved as <area>_<row>_<col>.png plus a .json sidecar with WGS84 bounds and effective gsd.
Check Esri's terms of use before using tiles beyond development.

Usage (from repo root):
  ml/.venv/bin/python ml/data/download_delhi_tiles.py --out data/raw/delhi_tiles --grid 3 --scale 2
  # one tile centred on a job location (what the production fetch step should do):
  ml/.venv/bin/python ml/data/download_delhi_tiles.py --out data/raw/jobs --center 28.6034 77.2932 --name job1
"""
from __future__ import annotations

import argparse
import io
import json
import math
import time
import urllib.request
from pathlib import Path

from PIL import Image

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ZOOM = 19

# Approximate residential centre points (lat, lon) — good enough for sampling roofs.
AREAS = {
    "dwarka": (28.5921, 77.0460),
    "rohini": (28.7383, 77.0822),
    "vasant_kunj": (28.5293, 77.1517),
    "lajpat_nagar": (28.5677, 77.2433),
    "mayur_vihar": (28.6040, 77.2930),
    "janakpuri": (28.6219, 77.0878),
    "sangam_vihar": (28.5070, 77.2420),
    "okhla": (28.5355, 77.2735),
}


def tile_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def tile_corner(x: int, y: int, z: int) -> tuple[float, float]:
    """North-west corner (lat, lon) of tile x, y."""
    n = 2 ** z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))), x / n * 360 - 180


def fetch(x: int, y: int, z: int) -> Image.Image:
    with urllib.request.urlopen(TILE_URL.format(z=z, y=y, x=x), timeout=30) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def fetch_centered(lat: float, lon: float, size: int = 512, scale: int = 2) -> tuple[Image.Image, list[float], float]:
    """Tile of `size` px centred on (lat, lon): z19 source pixels stitched, cropped, upsampled by `scale`.
    Returns (image, [minLng, minLat, maxLng, maxLat], gsd_m)."""
    n = 2 ** ZOOM
    gx = (lon + 180) / 360 * n * 256  # global z19 pixel coords
    gy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256
    half = size / scale / 2
    x0, y0, x1, y1 = gx - half, gy - half, gx + half, gy + half
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            canvas.paste(fetch(tx, ty, ZOOM), ((tx - tx0) * 256, (ty - ty0) * 256))
            time.sleep(0.2)
    crop = canvas.crop((round(x0 - tx0 * 256), round(y0 - ty0 * 256), round(x1 - tx0 * 256), round(y1 - ty0 * 256)))
    img = crop.resize((size, size), Image.BICUBIC)
    to_lon = lambda px: px / (n * 256) * 360 - 180
    to_lat = lambda py: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / (n * 256)))))
    bounds = [to_lon(x0), to_lat(y1), to_lon(x1), to_lat(y0)]
    gsd = 156543.03392 * math.cos(math.radians(lat)) / n / scale
    return img, bounds, gsd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/raw/delhi_tiles"))
    ap.add_argument("--grid", type=int, default=3, help="output tiles per side around each centre")
    ap.add_argument("--scale", type=int, choices=[1, 2], default=2)
    ap.add_argument("--areas", nargs="*", default=list(AREAS))
    ap.add_argument("--center", type=float, nargs=2, metavar=("LAT", "LNG"), help="fetch one tile centred here")
    ap.add_argument("--name", default="job", help="file stem for --center")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.center:
        img, bounds, gsd = fetch_centered(*args.center, scale=args.scale)
        img.save(args.out / f"{args.name}.png")
        (args.out / f"{args.name}.json").write_text(json.dumps(
            {"bounds": bounds, "gsd_m": round(gsd, 4), "zoom": ZOOM, "scale": args.scale,
             "center": args.center, "source": "esri_world_imagery"}))
        print(f"saved {args.name}.png centred on {args.center} (gsd {gsd:.3f} m/px)")
        return
    k = 2 // args.scale  # source tiles per output side

    for name in args.areas:
        lat, lon = AREAS[name]
        cx, cy = tile_xy(lat, lon, ZOOM)
        x_start, y_start = cx - (args.grid * k) // 2, cy - (args.grid * k) // 2
        for r in range(args.grid):
            for c in range(args.grid):
                stem = f"{name}_{r}_{c}"
                dest = args.out / f"{stem}.png"
                if dest.exists():
                    continue
                x0, y0 = x_start + c * k, y_start + r * k
                canvas = Image.new("RGB", (256 * k, 256 * k))
                for dy in range(k):
                    for dx in range(k):
                        canvas.paste(fetch(x0 + dx, y0 + dy, ZOOM), (256 * dx, 256 * dy))
                        time.sleep(0.2)
                canvas.resize((512, 512), Image.BICUBIC).save(dest)
                lat_n, lon_w = tile_corner(x0, y0, ZOOM)
                lat_s, lon_e = tile_corner(x0 + k, y0 + k, ZOOM)
                gsd = 156543.03392 * math.cos(math.radians(lat)) / 2 ** ZOOM * k * 256 / 512
                (args.out / f"{stem}.json").write_text(json.dumps(
                    {"bounds": [lon_w, lat_s, lon_e, lat_n], "gsd_m": round(gsd, 4), "zoom": ZOOM,
                     "scale": args.scale, "source": "esri_world_imagery"}))
                print(f"saved {dest.name} (gsd {gsd:.3f} m/px)")


if __name__ == "__main__":
    main()
