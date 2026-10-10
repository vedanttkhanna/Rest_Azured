"""Tile + job location -> contract B (roof + obstacle polygons as WGS84 GeoJSON).

Implements the post-processing rules in P1_ML_Segmentation.md:
  1. split touching roofs (erode + watershed on the image), then keep the target building only: the roof component that best overlaps the job footprint, else the one
     containing (or nearest, within --max-dist-m) the job lat/lng. If the footprint is well covered by the
     prediction, the footprint polygon itself is used as the roof outline (cleaner edges).
     Without a footprint the roof is capped to --max-radius-m around the point and a `warning` is set:
     attached Delhi row houses share walls and cannot be separated from imagery alone.
  2. polygonise per class, drop parts < 0.3 m^2, simplify (~0.15 m roofs/obstacles), output WGS84.
  3. each obstacle gets the roof_id of its roof.  4. roof_type "flat", azimuth/tilt null.  5. height_m null.

CLI (from repo root):
  ml/.venv/bin/python ml/serve/segment.py --model data/models/segformer_b2_delhi_fp/best \
      --image data/raw/delhi_tiles_g5/mayur_vihar_1_1.png --lat 28.60 --lng 77.29 --out seg_B.json
  (bounds are read from the tile's .json sidecar unless --bounds is given)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.polygon import orient
from transformers import SegformerForSemanticSegmentation

R = 6378137.0
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# model class index -> contract-B obstacle class
OBSTACLE_CLASS = {2: "water_tank", 3: "stair_room", 4: "ac_unit", 5: "solar_heater",
                  6: "existing_pv", 7: "parapet", 8: "tree", 9: "other"}
BUILT = [1, 2, 3, 4, 5, 6, 7, 9]  # pixels that belong to a building's roof extent


# ---------- model ----------
def load_model(path: str | Path, device: str | None = None):
    device = torch.device(device or ("mps" if torch.backends.mps.is_available() else "cpu"))
    model = SegformerForSemanticSegmentation.from_pretrained(path).to(device).eval()
    return model, device


@torch.no_grad()
def predict_probs(model, device, img: np.ndarray) -> np.ndarray:
    """RGB uint8 HxWx3 -> class probabilities CxHxW (float32)."""
    x = (img.astype(np.float32) / 255.0 - MEAN) / STD
    x = torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0).to(device)
    logits = F.interpolate(model(pixel_values=x).logits, size=img.shape[:2], mode="bilinear", align_corners=False)
    return logits.softmax(1)[0].cpu().numpy()


# ---------- geo helpers (tile is a Web-Mercator rectangle) ----------
class TileGeo:
    def __init__(self, bounds: list[float], width: int, height: int):
        self.w, self.h = width, height
        self.x0, self.y0 = self._merc(bounds[0], bounds[1])
        self.x1, self.y1 = self._merc(bounds[2], bounds[3])
        lat_c = (bounds[1] + bounds[3]) / 2
        self.gsd = (self.x1 - self.x0) / width * math.cos(math.radians(lat_c))  # ground metres / px

    @staticmethod
    def _merc(lon, lat):
        return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    def to_px(self, lon, lat):
        mx, my = self._merc(lon, lat)
        return (mx - self.x0) / (self.x1 - self.x0) * self.w, (self.y1 - my) / (self.y1 - self.y0) * self.h

    def to_lonlat(self, x, y):
        mx = self.x0 + x / self.w * (self.x1 - self.x0)
        my = self.y1 - y / self.h * (self.y1 - self.y0)
        return math.degrees(mx / R), math.degrees(2 * math.atan(math.exp(my / R)) - math.pi / 2)

    def poly_to_px(self, geom: dict) -> Polygon:
        g = shape(geom)
        g = max(getattr(g, "geoms", [g]), key=lambda p: p.area)
        return Polygon([self.to_px(*c) for c in g.exterior.coords])

    def poly_to_geojson(self, poly: Polygon) -> dict:
        poly = orient(poly, sign=1.0)  # counter-clockwise exterior (RFC 7946)
        ring = [list(self.to_lonlat(x, y)) for x, y in poly.exterior.coords]
        return {"type": "Polygon", "coordinates": [[[round(a, 7), round(b, 7)] for a, b in ring]]}


# ---------- raster <-> vector ----------
def contours_to_polys(binary: np.ndarray, min_px: float, eps_px: float) -> list[Polygon]:
    contours, _ = cv2.findContours(binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        if cv2.contourArea(c) < min_px:
            continue
        c = cv2.approxPolyDP(c, eps_px, True).reshape(-1, 2)
        if len(c) >= 3:
            p = Polygon(c).buffer(0)
            if p.is_valid and not p.is_empty:
                out.extend(getattr(p, "geoms", [p]))
    return [p for p in out if p.area >= min_px]


def rasterize(poly: Polygon, h: int, w: int) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.round(np.array(poly.exterior.coords)).astype(np.int32)], 1)
    return m.astype(bool)


# ---------- main post-processing ----------
def split_buildings(built: np.ndarray, image: np.ndarray, erode_px: float) -> tuple[np.ndarray, int]:
    """Split touching roofs: seeds = built mask eroded by ~erode_px, grown back with a watershed on the image
    (walls/shadows between buildings act as ridges). Returns (labels, n) like cv2.connectedComponents."""
    k = max(3, int(round(erode_px)) | 1)
    seeds = cv2.erode(built, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, markers = cv2.connectedComponents(seeds)
    markers = markers.astype(np.int32)
    markers[cv2.erode(1 - built, np.ones((3, 3), np.uint8)) > 0] = n  # sure background
    markers = cv2.watershed(cv2.cvtColor(image, cv2.COLOR_RGB2BGR), markers)
    labels = np.where((markers > 0) & (markers < n) & (built > 0), markers, 0)
    return labels, n


def to_contract_b(probs: np.ndarray, bounds: list[float], lat: float, lng: float, job_id: str,
                  model_version: str, footprint: dict | None = None, max_dist_m: float = 10.0,
                  min_area_m2: float = 0.3, image: np.ndarray | None = None, split_m: float = 2.5,
                  max_radius_m: float = 12.0) -> dict:
    C, H, W = probs.shape
    geo = TileGeo(bounds, W, H)
    pred, conf = probs.argmax(0), probs.max(0)
    min_px = min_area_m2 / geo.gsd ** 2
    eps_roof, eps_obs = max(1.0, 0.15 / geo.gsd), 1.0

    # 1. roof extent -> one component per building
    built = np.isin(pred, BUILT).astype(np.uint8)
    built = cv2.morphologyEx(built, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    labels, n = split_buildings(built, image, split_m / geo.gsd) if image is not None and split_m > 0 \
        else cv2.connectedComponents(built)[::-1]
    fp_px = geo.poly_to_px(footprint) if footprint else None
    jx, jy = geo.to_px(lng, lat)

    target = None
    if fp_px is not None:
        fp_mask = rasterize(fp_px, H, W)
        overlaps = np.bincount(labels[fp_mask], minlength=n)
        overlaps[0] = 0
        if overlaps.max() > 0:
            target = int(overlaps.argmax())
    if target is None and 0 <= int(jy) < H and 0 <= int(jx) < W and labels[int(jy), int(jx)] > 0:
        target = int(labels[int(jy), int(jx)])
    if target is None and n > 1:
        ys, xs = np.nonzero(labels)
        d = np.hypot(xs - jx, ys - jy)
        if d.min() * geo.gsd <= max_dist_m:
            target = int(labels[ys[d.argmin()], xs[d.argmin()]])

    features = []
    fc = {"job_id": job_id, "model_version": model_version, "type": "FeatureCollection", "features": features}
    if target is None:
        fc["warning"] = "no roof found at the job location"
        return fc

    comp = labels == target
    if fp_px is None and max_radius_m > 0:
        # Attached row houses share walls, so the image alone can't separate them. Without a footprint,
        # limit the roof to max_radius_m around the job point and say so.
        disk = np.zeros((H, W), np.uint8)
        cv2.circle(disk, (int(round(jx)), int(round(jy))), int(round(max_radius_m / geo.gsd)), 1, -1)
        if (comp & ~disk.astype(bool)).any():
            fc["warning"] = (f"no building footprint; roof limited to {max_radius_m:g} m around the job point "
                             "(attached buildings may be merged)")
        comp = comp & disk.astype(bool)
    roof_polys = contours_to_polys(comp, min_px, eps_roof)
    if fp_px is not None:
        fp_mask = rasterize(fp_px, H, W)
        covered = (comp & fp_mask).sum() / max(fp_mask.sum(), 1)
        if covered >= 0.5:  # prediction confirms the footprint -> use its clean outline
            roof_polys = [fp_px.buffer(0)]
    if not roof_polys:
        fc["warning"] = "roof component too small"
        return fc
    roof = max(roof_polys, key=lambda p: p.area)
    roof_mask = rasterize(roof, H, W)
    features.append({"type": "Feature", "geometry": geo.poly_to_geojson(roof), "properties": {
        "id": "r1", "kind": "roof", "roof_type": "flat", "azimuth_deg": None, "tilt_deg": None,
        "confidence": round(float(conf[roof_mask].mean()), 3)}})

    # 2-3. obstacles / PV on that roof; trees overhanging it
    near_roof = cv2.dilate(roof_mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    k = 0
    for cls, name in OBSTACLE_CLASS.items():
        region = (pred == cls) & (near_roof if cls == 8 else roof_mask)
        for p in contours_to_polys(region, min_px, eps_obs):
            p = p.intersection(roof) if cls != 8 else p
            if p.is_empty or p.area < min_px:
                continue
            p = max(getattr(p, "geoms", [p]), key=lambda q: q.area)
            k += 1
            pm = rasterize(p, H, W)
            features.append({"type": "Feature", "geometry": geo.poly_to_geojson(p), "properties": {
                "id": f"o{k}", "kind": "obstacle", "roof_id": "r1", "class": name, "height_m": None,
                "confidence": round(float(conf[pm].mean()) if pm.any() else 0.0, 3)}})
    return fc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--bounds", type=float, nargs=4, help="minLng minLat maxLng maxLat (default: tile .json sidecar)")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lng", type=float, required=True)
    ap.add_argument("--footprint", type=Path, help="GeoJSON Polygon file for the target building (optional)")
    ap.add_argument("--job-id", default="local-test")
    ap.add_argument("--model-version", default="segformer-b2-delhi-fp-v1")
    ap.add_argument("--device", help="mps | cpu (default: mps if available)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    bounds = args.bounds or json.loads(args.image.with_suffix(".json").read_text())["bounds"]
    footprint = json.loads(args.footprint.read_text()) if args.footprint else None
    model, device = load_model(args.model, args.device)
    img = np.asarray(Image.open(args.image).convert("RGB"))
    t0 = time.time()
    probs = predict_probs(model, device, img)
    t1 = time.time()
    fc = to_contract_b(probs, bounds, args.lat, args.lng, args.job_id, args.model_version, footprint, image=img)
    t2 = time.time()
    args.out.write_text(json.dumps(fc, indent=1))
    kinds = [f["properties"].get("class", f["properties"]["kind"]) for f in fc["features"]]
    print(f"{len(fc['features'])} features {kinds} | inference {t1 - t0:.2f}s on {device}, "
          f"post-processing {t2 - t1:.2f}s -> {args.out}" + (f" | WARNING: {fc['warning']}" if "warning" in fc else ""))


if __name__ == "__main__":
    main()
