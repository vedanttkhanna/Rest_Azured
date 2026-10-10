"""Convert RID (TUM Roof Information Dataset) masks to our class scheme.

RID mask format (from github.com/TUMFTM/RID, definitions.py + mask_generation.py):
  - 512x512 single-channel PNG, filename "<image_id>.png", pixel value = class index.
  - Segment masks: 0..15 = 16 azimuth bins (N, NNE, ... NNW), 16 = flat, 17 = background.
  - Superstructure masks: 0 pvmodule, 1 dormer, 2 window, 3 ladder, 4 chimney,
    5 shadow, 6 tree, 7 unknown, 8 background.

Our classes (see P1_ML_Segmentation.md):
  0 background, 1 usable_roof, 2 water_tank, 3 stair_room, 4 ac_unit, 5 solar_heater,
  6 existing_pv, 7 parapet, 8 tree, 9 other_obstacle, 255 ignore.

Download layout (verified 2026-10-10, mediaTUM m1655470):
  RID_dataset/images_roof_centered_geotiff/<id>.tif   (512x512 RGB GeoTIFF)
  RID_dataset/masks_segments_reviewed/<id>.png
  RID_dataset/masks_superstructures_reviewed/<id>.png
  RID_dataset/filenames_train_val_test_split/{train,val,test}_filenames_<fold>_rev.txt  (folds 1-5, one "<id>.png" per line)

Usage:
  python rid_to_ours.py --rid-data /path/to/RID_dataset --out /path/to/rid_ours [--fold 1] [--check 5]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
from PIL import Image

RID_SEG_BACKGROUND = 17
RID_SUP_BACKGROUND = 8
IGNORE = 255

# RID superstructure index -> our class
SUP_TO_OURS = {
    0: 6,       # pvmodule -> existing_pv
    1: 9,       # dormer   -> other_obstacle
    2: 9,       # window   -> other_obstacle
    3: 9,       # ladder   -> other_obstacle
    4: 9,       # chimney  -> other_obstacle
    5: IGNORE,  # shadow   -> ignore (not a physical object)
    6: 8,       # tree     -> tree
    7: 9,       # unknown  -> other_obstacle
}

# For visual sanity checks only
PALETTE = {0: (0, 0, 0), 1: (255, 210, 0), 6: (0, 120, 255), 8: (0, 170, 0),
           9: (255, 0, 0), IGNORE: (128, 128, 128)}


def convert(seg: np.ndarray, sup: np.ndarray | None) -> np.ndarray:
    out = np.zeros(seg.shape, dtype=np.uint8)
    out[seg < RID_SEG_BACKGROUND] = 1
    if sup is not None:
        for rid_cls, ours in SUP_TO_OURS.items():
            out[sup == rid_cls] = ours
    return out


def colorize(mask: np.ndarray) -> Image.Image:
    rgb = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for cls, color in PALETTE.items():
        rgb[mask == cls] = color
    return Image.fromarray(rgb)


def find_dir(root: Path, *names: str) -> Path | None:
    for name in names:
        p = root / name
        if p.is_dir():
            return p
    return None


def read_split(split_dir: Path, fold: int) -> dict[str, set[str]]:
    """Read RID's {train,val,test}_filenames_<fold>_rev.txt (one '<id>.png' per line)."""
    split = {}
    for part in ("train", "val", "test"):
        f = split_dir / f"{part}_filenames_{fold}_rev.txt"
        if f.exists():
            split[part] = set(re.findall(r"(\d+)\.png", f.read_text()))
    return split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rid-data", type=Path, required=True, help="RID_dataset folder from the TUM download")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fold", type=int, default=1, help="which of RID's 5 train/val/test splits to use")
    ap.add_argument("--check", type=int, default=0, help="print value histograms + save previews for N masks")
    args = ap.parse_args()

    img_dir = find_dir(args.rid_data, "images_roof_centered_geotiff", "images_roof_centered_png")
    seg_dir = find_dir(args.rid_data, "masks_segments_reviewed", "masks_segments")
    sup_dir = find_dir(args.rid_data, "masks_superstructures_reviewed", "masks_superstructures_initial")
    if not (img_dir and seg_dir):
        raise SystemExit(f"Expected images_roof_centered_geotiff/ and masks_segments*/ under {args.rid_data}. "
                         f"Found: {[p.name for p in args.rid_data.iterdir()]}")
    print(f"images: {img_dir}\nsegments: {seg_dir}\nsuperstructures: {sup_dir}")

    split_dir = args.rid_data / "filenames_train_val_test_split"
    split = read_split(split_dir, args.fold) if split_dir.is_dir() else {}
    print(f"fold {args.fold} split sizes:", {k: len(v) for k, v in split.items()} or "none found -> all/")

    n = 0
    for seg_path in sorted(seg_dir.glob("*.png")):
        image_id = seg_path.stem
        img_path = next((p for p in (img_dir / f"{image_id}.tif", img_dir / f"{image_id}.png") if p.exists()), None)
        if img_path is None:
            continue
        seg = np.array(Image.open(seg_path))
        sup_path = sup_dir / f"{image_id}.png" if sup_dir else None
        sup = np.array(Image.open(sup_path)) if sup_path and sup_path.exists() else None

        part = next((k for k, ids in split.items() if image_id in ids), "all")
        (args.out / part / "images").mkdir(parents=True, exist_ok=True)
        (args.out / part / "masks").mkdir(parents=True, exist_ok=True)
        img = Image.open(img_path).convert("RGB")
        img.save(args.out / part / "images" / f"{image_id}.png")
        mask = convert(seg, sup)
        Image.fromarray(mask).save(args.out / part / "masks" / f"{image_id}.png")

        if n < args.check:
            print(f"{image_id}: seg values {np.unique(seg).tolist()}, "
                  f"sup values {None if sup is None else np.unique(sup).tolist()}, "
                  f"ours {np.unique(mask).tolist()}")
            (args.out / "_preview").mkdir(parents=True, exist_ok=True)
            colorize(mask).save(args.out / "_preview" / f"{image_id}_mask.png")
            img.save(args.out / "_preview" / f"{image_id}_img.png")
        n += 1
    print(f"converted {n} images -> {args.out}")


if __name__ == "__main__":
    main()
