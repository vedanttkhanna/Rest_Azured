"""Pick Delhi tiles worth labelling and export model predictions as editable pre-labels (COCO polygons).

Selection: tiles ranked by predicted built-up share (roof + obstacle + PV) from predict.py's summary.csv.
One area is held out entirely as the test set (no leakage between nearby tiles).

Usage (from repo root):
  ml/.venv/bin/python ml/data/make_label_batch.py \
      --images data/raw/delhi_tiles_g5 --pred data/predictions/delhi_g5_rid_only \
      --out data/labeling/batch1 --test-area mayur_vihar --per-area 7 --n-test 10 --min-built 8 \
      --exclude rohini_0_3 rohini_4_0 rohini_1_2
Outputs in --out: images/, prelabels_coco.json, cvat_prelabels.zip, split.json, contact_sheet.png
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# label name in the labelling tool -> class index in our masks
LABELS = {"usable_roof": 1, "other_obstacle": 9, "existing_pv": 6, "tree": 8}
# our class index -> pre-label name (obstacle-like classes collapse to other_obstacle)
PRED_TO_LABEL = {1: "usable_roof", 2: "other_obstacle", 3: "other_obstacle", 4: "other_obstacle",
                 5: "other_obstacle", 7: "other_obstacle", 9: "other_obstacle", 6: "existing_pv", 8: "tree"}
MIN_AREA_PX = {"usable_roof": 150, "other_obstacle": 20, "existing_pv": 40, "tree": 150}


def area_of(stem: str) -> str:
    return stem.rsplit("_", 2)[0]


def polygons(mask: np.ndarray, label: str) -> list[list[float]]:
    classes = [c for c, n in PRED_TO_LABEL.items() if n == label]
    binary = np.isin(mask, classes).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        if cv2.contourArea(c) < MIN_AREA_PX[label]:
            continue
        c = cv2.approxPolyDP(c, 1.5, True)
        if len(c) >= 3:
            out.append(c.reshape(-1).astype(float).tolist())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--pred", type=Path, required=True, help="predict.py output folder (summary.csv + *_mask.png)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--test-area", default="mayur_vihar")
    ap.add_argument("--per-area", type=int, default=6, help="training tiles per non-test area")
    ap.add_argument("--n-test", type=int, default=10)
    ap.add_argument("--min-built", type=float, default=15.0, help="min predicted built-up %% to consider a tile")
    ap.add_argument("--exclude", nargs="*", default=[], help="tile stems to skip (e.g. roads, parks)")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.pred / "summary.csv")))
    obstacle_cols = [k for k in rows[0] if k.endswith("_pct") and k not in
                     ("background_pct", "usable_roof_pct", "existing_pv_pct", "tree_pct")]
    for r in rows:
        r["stem"] = Path(r["image"]).stem
        r["built"] = float(r["usable_roof_pct"]) + float(r["existing_pv_pct"]) + sum(float(r[k]) for k in obstacle_cols)
    by_area: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: -r["built"]):
        if r["built"] >= args.min_built and r["stem"] not in args.exclude:
            by_area.setdefault(area_of(r["stem"]), []).append(r)

    split = {"train": [], "test": []}
    for area, rs in sorted(by_area.items()):
        if area == args.test_area:
            split["test"] += [r["stem"] for r in rs[:args.n_test]]
        else:
            split["train"] += [r["stem"] for r in rs[:args.per_area]]
    print("tiles per area:", {a: min(len(rs), args.n_test if a == args.test_area else args.per_area)
                              for a, rs in sorted(by_area.items())})
    if not split["test"]:
        raise SystemExit(f"No tiles from test area {args.test_area!r} passed --min-built")

    (args.out / "images").mkdir(parents=True, exist_ok=True)
    coco = {"images": [], "annotations": [],
            "categories": [{"id": i + 1, "name": n, "supercategory": ""} for i, n in enumerate(LABELS)]}
    cat_id = {c["name"]: c["id"] for c in coco["categories"]}
    stems = split["train"] + split["test"]
    for img_id, stem in enumerate(stems, start=1):
        src = args.images / f"{stem}.png"
        shutil.copy(src, args.out / "images" / src.name)
        w, h = Image.open(src).size
        coco["images"].append({"id": img_id, "file_name": src.name, "width": w, "height": h})
        mask = np.array(Image.open(args.pred / f"{stem}_mask.png"))
        for label in LABELS:
            for poly in polygons(mask, label):
                xs, ys = poly[0::2], poly[1::2]
                coco["annotations"].append({
                    "id": len(coco["annotations"]) + 1, "image_id": img_id, "category_id": cat_id[label],
                    "segmentation": [poly], "iscrowd": 0,
                    "area": float(cv2.contourArea(np.array(poly, np.float32).reshape(-1, 2))),
                    "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]})

    (args.out / "prelabels_coco.json").write_text(json.dumps(coco))
    with zipfile.ZipFile(args.out / "cvat_prelabels.zip", "w") as z:
        z.writestr("annotations/instances_default.json", json.dumps(coco))
    (args.out / "split.json").write_text(json.dumps(split, indent=2))

    # contact sheet for a quick visual check of the selection
    thumbs = [Image.open(args.out / "images" / f"{s}.png").resize((128, 128)) for s in stems]
    cols = 10
    sheet = Image.new("RGB", (cols * 128, ((len(thumbs) + cols - 1) // cols) * 128))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols) * 128, (i // cols) * 128))
    sheet.save(args.out / "contact_sheet.png")
    print(f"{len(split['train'])} train + {len(split['test'])} test tiles, "
          f"{len(coco['annotations'])} pre-label polygons -> {args.out}")


if __name__ == "__main__":
    main()
