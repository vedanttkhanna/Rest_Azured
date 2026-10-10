"""Run a trained SegFormer on a folder of images and save masks + coloured overlays.

Usage (from repo root):
  ml/.venv/bin/python ml/infer/predict.py --model data/models/segformer_b2_rid/best \
      --images data/raw/delhi_tiles --out data/predictions/delhi_rid_only
Outputs per image: <id>_mask.png (class index), <id>_overlay.png (image | overlay side by side),
plus summary.csv with per-class pixel shares.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import SegformerForSemanticSegmentation

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PALETTE = {0: None, 1: (255, 210, 0), 2: (0, 255, 255), 3: (255, 0, 255), 4: (255, 128, 0),
           5: (128, 0, 255), 6: (0, 120, 255), 7: (255, 255, 255), 8: (0, 170, 0), 9: (255, 0, 0)}


@torch.no_grad()
def predict(model, img: Image.Image, device) -> np.ndarray:
    x = (np.asarray(img, dtype=np.float32) / 255.0 - MEAN) / STD
    x = torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0).to(device)
    logits = model(pixel_values=x).logits
    logits = F.interpolate(logits, size=x.shape[-2:], mode="bilinear", align_corners=False)
    return logits.argmax(1)[0].cpu().numpy().astype(np.uint8)


def overlay(img: Image.Image, mask: np.ndarray) -> Image.Image:
    color = np.asarray(img).copy()
    for cls, rgb in PALETTE.items():
        if rgb is not None:
            sel = mask == cls
            color[sel] = (0.5 * color[sel] + 0.5 * np.array(rgb)).astype(np.uint8)
    out = Image.new("RGB", (img.width * 2, img.height))
    out.paste(img, (0, 0))
    out.paste(Image.fromarray(color), (img.width, 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True, help="folder of .png/.jpg/.tif images")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--size", type=int, default=512, help="images are resized to this square size")
    args = ap.parse_args()

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = SegformerForSemanticSegmentation.from_pretrained(args.model).to(device).eval()
    classes = [model.config.id2label[i] for i in range(model.config.num_labels)]
    args.out.mkdir(parents=True, exist_ok=True)

    paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"})
    with open(args.out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image"] + [f"{c}_pct" for c in classes])
        for p in paths:
            img = Image.open(p).convert("RGB").resize((args.size, args.size))
            mask = predict(model, img, device)
            Image.fromarray(mask).save(args.out / f"{p.stem}_mask.png")
            overlay(img, mask).save(args.out / f"{p.stem}_overlay.png")
            share = np.bincount(mask.ravel(), minlength=len(classes)) / mask.size * 100
            w.writerow([p.name] + [round(float(s), 2) for s in share])
            print(f"{p.name}: roof {share[1]:.1f}% | obstacles {share[[2, 3, 4, 5, 7, 9]].sum():.1f}% | "
                  f"pv {share[6]:.1f}% | tree {share[8]:.1f}%")
    print(f"done: {len(paths)} images -> {args.out}")


if __name__ == "__main__":
    main()
