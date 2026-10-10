"""Build automatic Delhi training labels from building footprints (Overture Maps) + model predictions.

Label rule per tile (classes as in train.py):
  inside a footprint                      -> usable_roof (1), unless the model predicts obstacle (9), PV (6) or tree (8) there
  outside footprints, model says roof/obstacle/PV -> ignore (255): the footprint may just be missing
  everything else                         -> background (0)
  a --edge-px band around footprint edges -> ignore (255), absorbs small footprint/imagery misalignment

Footprint/imagery misalignment: OSM footprints in some areas sit several metres off the Esri imagery.
Optional model-based shift search (--max-shift) and IoU filter (--min-iou) exist but are OFF by default:
tested 2026-10-10, they did not separate good from bad tiles because the RID-only model misses too many
Delhi roofs to register against. Bad tiles/areas are instead excluded by visual review (--exclude).
A per-tile report is written to <out>/alignment.csv.

Usage (from repo root):
  ml/.venv/bin/python ml/data/footprint_labels.py --tiles data/raw/delhi_tiles_g5 \
      --pred data/predictions/delhi_g5_rid_only --footprints data/raw/footprints \
      --out data/processed/delhi_fp --test-area mayur_vihar
  (add --preview-only to just write overlays to <out>/_preview for an alignment check)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_erosion

R = 6378137.0
OBSTACLE_PRED = [2, 3, 4, 5, 7, 9]


def merc(lon: float, lat: float) -> tuple[float, float]:
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def area_of(stem: str) -> str:
    return stem.rsplit("_", 2)[0]


def fetch_footprints(area: str, tiles: list[Path], out_dir: Path) -> gpd.GeoDataFrame:
    path = out_dir / f"{area}.parquet"
    if not path.exists():
        b = [json.loads(t.with_suffix(".json").read_text())["bounds"] for t in tiles]
        bbox = f"{min(x[0] for x in b)},{min(x[1] for x in b)},{max(x[2] for x in b)},{max(x[3] for x in b)}"
        exe = Path(sys.executable).with_name("overturemaps")
        subprocess.run([str(exe), "download", f"--bbox={bbox}", "-f", "geoparquet", "-t", "building",
                        "-o", str(path)], check=True)
    return gpd.read_parquet(path)


def rasterize(gdf: gpd.GeoDataFrame, bounds: list[float], size: int) -> np.ndarray:
    x0, y0 = merc(bounds[0], bounds[1])
    x1, y1 = merc(bounds[2], bounds[3])

    def px(coords):
        out = []
        for lon, lat in coords:
            mx, my = merc(lon, lat)
            out.append(((mx - x0) / (x1 - x0) * size, (y1 - my) / (y1 - y0) * size))
        return out

    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    for geom in gdf.geometry:
        for poly in getattr(geom, "geoms", [geom]):
            if poly.geom_type != "Polygon":
                continue
            draw.polygon(px(poly.exterior.coords), fill=1)
            for hole in poly.interiors:
                draw.polygon(px(hole.coords), fill=0)
    return np.array(img, dtype=bool)


def shift(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.zeros_like(mask)
    h, w = mask.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = mask[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def align(fp: np.ndarray, built: np.ndarray, max_shift: int, step: int = 2) -> tuple[int, int, float, float]:
    """Return (dy, dx, iou_before, iou_after) maximising IoU between shifted footprints and built-up prediction."""
    def iou(a):
        u = (a | built).sum()
        return float((a & built).sum() / u) if u else 0.0
    base = iou(fp)
    best = (0, 0, base)
    for dy in range(-max_shift, max_shift + 1, step):
        for dx in range(-max_shift, max_shift + 1, step):
            v = iou(shift(fp, dy, dx))
            if v > best[2] + 1e-9:
                best = (dy, dx, v)
    return best[0], best[1], base, best[2]


def build_label(fp: np.ndarray, pred: np.ndarray, edge_px: int) -> np.ndarray:
    label = np.zeros(fp.shape, dtype=np.uint8)
    label[fp] = 1
    label[fp & np.isin(pred, OBSTACLE_PRED)] = 9
    label[fp & (pred == 6)] = 6
    label[fp & (pred == 8)] = 8
    label[~fp & np.isin(pred, [1, 6] + OBSTACLE_PRED)] = 255
    if edge_px > 0:
        edge = binary_dilation(fp, iterations=edge_px) & ~binary_erosion(fp, iterations=edge_px)
        label[edge] = 255
    return label


def preview(img: Image.Image, fp: np.ndarray, label: np.ndarray) -> Image.Image:
    base = np.asarray(img).copy()
    outline = fp ^ binary_erosion(fp, iterations=2)
    left = base.copy()
    left[outline] = (0, 255, 255)
    colors = {1: (255, 210, 0), 9: (255, 0, 0), 6: (0, 120, 255), 8: (0, 170, 0), 255: (128, 128, 128)}
    right = base.copy()
    for c, rgb in colors.items():
        sel = label == c
        right[sel] = (0.5 * right[sel] + 0.5 * np.array(rgb)).astype(np.uint8)
    out = Image.new("RGB", (img.width * 2, img.height))
    out.paste(Image.fromarray(left), (0, 0))
    out.paste(Image.fromarray(right), (img.width, 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True, help="predict.py output with <stem>_mask.png")
    ap.add_argument("--footprints", type=Path, default=Path("data/raw/footprints"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--test-area", default="mayur_vihar")
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--edge-px", type=int, default=3)
    ap.add_argument("--max-shift", type=int, default=0, help="0 = no shift search (default)")
    ap.add_argument("--min-iou", type=float, default=0.0, help="0 = no IoU filter (default)")
    ap.add_argument("--exclude", nargs="*", default=[], help="tile stems or whole area names to skip")
    ap.add_argument("--min-fp-px", type=int, default=2000, help="tiles with fewer footprint pixels skip the IoU filter")
    ap.add_argument("--preview-only", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    args.footprints.mkdir(parents=True, exist_ok=True)

    tiles = sorted(args.tiles.glob("*.png"))
    by_area: dict[str, list[Path]] = {}
    for t in tiles:
        by_area.setdefault(area_of(t.stem), []).append(t)

    train_stems = [t.stem for a, ts in by_area.items() if a != args.test_area for t in ts]
    random.Random(args.seed).shuffle(train_stems)
    n_val = round(len(train_stems) * args.val_frac)
    part_of = {s: "val" for s in train_stems[:n_val]} | {s: "train" for s in train_stems[n_val:]}

    stats = {"train": 0, "val": 0, "test": 0, "skipped": 0}
    args.out.mkdir(parents=True, exist_ok=True)
    report = open(args.out / "alignment.csv", "w")
    report.write("tile,fp_px,dy,dx,iou_before,iou_after,kept\n")
    for area, ts in sorted(by_area.items()):
        gdf = fetch_footprints(area, ts, args.footprints)
        print(f"{area}: {len(gdf)} footprints, {len(ts)} tiles")
        for t in ts:
            img = Image.open(t).convert("RGB")
            bounds = json.loads(t.with_suffix(".json").read_text())["bounds"]
            fp = rasterize(gdf, bounds, img.width)
            pred = np.array(Image.open(args.pred / f"{t.stem}_mask.png"))
            built = np.isin(pred, [1, 6] + OBSTACLE_PRED)
            dy, dx, before, after = align(fp, built, args.max_shift) if args.max_shift else (0, 0, 0.0, 0.0)
            fp = shift(fp, dy, dx)
            kept = (fp.sum() < args.min_fp_px or after >= args.min_iou) and \
                t.stem not in args.exclude and area not in args.exclude
            report.write(f"{t.stem},{int(fp.sum())},{dy},{dx},{before:.3f},{after:.3f},{int(kept)}\n")
            label = build_label(fp, pred, args.edge_px)
            (args.out / "_preview").mkdir(parents=True, exist_ok=True)
            preview(img, fp, label).save(args.out / "_preview" / f"{t.stem}.png")
            if args.preview_only:
                continue
            if not kept:
                stats["skipped"] += 1
                continue
            part = "test" if area == args.test_area else part_of[t.stem]
            for sub in ("images", "masks"):
                (args.out / part / sub).mkdir(parents=True, exist_ok=True)
            shutil.copy(t, args.out / part / "images" / t.name)
            Image.fromarray(label).save(args.out / part / "masks" / t.name)
            stats[part] += 1
    report.close()
    print("written:" if not args.preview_only else "previews only:", stats, "->", args.out)


if __name__ == "__main__":
    main()
