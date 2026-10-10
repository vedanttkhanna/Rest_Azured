"""Train / fine-tune SegFormer for rooftop segmentation (runs on Apple-silicon GPU via MPS).

Data layout (produced by ml/data/rid_to_ours.py):
  <data>/{train,val,test}/images/<id>.png   RGB 512x512
  <data>/{train,val,test}/masks/<id>.png    class index per pixel, 255 = ignore

Examples (from repo root):
  # quick benchmark: 1 epoch on 200 images
  ml/.venv/bin/python ml/train/train.py --epochs 1 --limit 200 --out data/models/bench
  # Stage A: RID
  ml/.venv/bin/python ml/train/train.py --epochs 40 --out data/models/segformer_b2_rid
  # Stage B: fine-tune on Delhi starting from Stage A
  ml/.venv/bin/python ml/train/train.py --data data/processed/delhi --init data/models/segformer_b2_rid/best --lr 2e-5 --out data/models/segformer_b2_delhi
  # evaluate a checkpoint on the test split
  ml/.venv/bin/python ml/train/train.py --eval-only --init data/models/segformer_b2_rid/best --split test
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import SegformerForSemanticSegmentation

CLASSES = ["background", "usable_roof", "water_tank", "stair_room", "ac_unit",
           "solar_heater", "existing_pv", "parapet", "tree", "other_obstacle"]
IGNORE = 255
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class RoofDataset(Dataset):
    def __init__(self, root: Path, split: str, train: bool, limit: int | None = None):
        self.images = sorted((root / split / "images").glob("*.png"))
        if limit:
            self.images = self.images[:limit]
        self.masks_dir = root / split / "masks"
        self.train = train
        if not self.images:
            raise SystemExit(f"No images in {root / split / 'images'}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, i):
        img = np.asarray(Image.open(self.images[i]).convert("RGB"), dtype=np.float32) / 255.0
        mask = np.asarray(Image.open(self.masks_dir / self.images[i].name), dtype=np.int64)
        if self.train:
            k = random.randint(0, 3)
            img, mask = np.rot90(img, k), np.rot90(mask, k)
            if random.random() < 0.5:
                img, mask = img[:, ::-1], mask[:, ::-1]
            # brightness / contrast jitter + occasional haze (Delhi imagery is often hazy)
            img = (img - 0.5) * random.uniform(0.8, 1.2) + 0.5 + random.uniform(-0.1, 0.1)
            if random.random() < 0.3:
                a = random.uniform(0.05, 0.3)
                img = img * (1 - a) + a * 0.8
            img = np.clip(img, 0, 1)
        img = (img - MEAN) / STD
        return (torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1))),
                torch.from_numpy(np.ascontiguousarray(mask)))


def class_weights(ds: RoofDataset, n: int = 300) -> torch.Tensor:
    """Inverse-sqrt pixel frequency over a sample of training masks; absent classes get weight 1."""
    counts = np.zeros(len(CLASSES))
    for p in ds.images[:n]:
        m = np.asarray(Image.open(ds.masks_dir / p.name))
        counts += np.bincount(m[m != IGNORE].ravel(), minlength=256)[:len(CLASSES)]
    w = np.ones(len(CLASSES))
    present = counts > 0
    w[present] = 1 / np.sqrt(counts[present] / counts[present].sum())
    w[present] /= w[present].mean()
    return torch.tensor(np.clip(w, 0.1, 10), dtype=torch.float32)


def logits_at(model, x):
    out = model(pixel_values=x).logits
    return F.interpolate(out, size=x.shape[-2:], mode="bilinear", align_corners=False)


@torch.no_grad()
def evaluate(model, loader, device) -> dict:
    model.eval()
    n = len(CLASSES)
    conf = torch.zeros(n, n, dtype=torch.int64)
    for x, y in tqdm(loader, desc="eval", leave=False):
        pred = logits_at(model, x.to(device)).argmax(1).cpu()
        valid = y != IGNORE
        conf += torch.bincount(y[valid] * n + pred[valid], minlength=n * n).reshape(n, n)
    inter = conf.diag().double()
    union = conf.sum(0).double() + conf.sum(1).double() - inter
    present = conf.sum(1) > 0  # classes that appear in the ground truth
    iou = {CLASSES[c]: round(float(inter[c] / union[c]), 4) for c in range(n) if present[c]}
    obstacles = [v for k, v in iou.items() if k not in ("background", "usable_roof")]
    return {"iou": iou,
            "miou": round(float(np.mean(list(iou.values()))), 4),
            "miou_obstacles": round(float(np.mean(obstacles)), 4) if obstacles else None,
            "pixel_acc": round(float(inter.sum() / conf.sum()), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/processed/rid_ours"))
    ap.add_argument("--out", type=Path, default=Path("data/models/segformer_b2_rid"))
    ap.add_argument("--backbone", default="nvidia/mit-b2")
    ap.add_argument("--init", type=Path, help="start from a saved checkpoint dir instead of the backbone")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=6e-5)
    ap.add_argument("--limit", type=int, help="use only N training images (quick tests)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--split", default="val", help="split to evaluate with --eval-only")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = torch.device("mps" if torch.backends.mps.is_available() else
                          "cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    if args.init:
        model = SegformerForSemanticSegmentation.from_pretrained(args.init)
    else:
        model = SegformerForSemanticSegmentation.from_pretrained(
            args.backbone, num_labels=len(CLASSES),
            id2label=dict(enumerate(CLASSES)), label2id={c: i for i, c in enumerate(CLASSES)},
            ignore_mismatched_sizes=True)
    model.to(device)

    if args.eval_only:
        ds = RoofDataset(args.data, args.split, train=False)
        res = evaluate(model, DataLoader(ds, batch_size=args.batch, num_workers=args.workers), device)
        print(json.dumps(res, indent=2))
        return

    train_ds = RoofDataset(args.data, "train", train=True, limit=args.limit)
    val_ds = RoofDataset(args.data, "val", train=False, limit=args.limit and max(args.limit // 4, 8))
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=args.workers,
                          drop_last=True, persistent_workers=args.workers > 0)
    val_dl = DataLoader(val_ds, batch_size=args.batch, num_workers=args.workers)
    print(f"train {len(train_ds)} | val {len(val_ds)} images")

    weights = class_weights(train_ds)
    print("class weights:", {c: round(float(w), 2) for c, w in zip(CLASSES, weights)})
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights.to(device), ignore_index=IGNORE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total = args.epochs * len(train_dl)
    warmup = min(500, total // 10)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warmup if s < warmup else (1 - (s - warmup) / max(1, total - warmup)) ** 0.9)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "args.json").write_text(json.dumps({k: str(v) for k, v in vars(args).items()}, indent=2))
    log_path = args.out / "log.csv"
    best = -1.0
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(["epoch", "train_loss", "val_miou", "val_miou_obstacles", "roof_iou", "minutes"])

    for epoch in range(1, args.epochs + 1):
        model.train()
        t0, running = time.time(), 0.0
        bar = tqdm(train_dl, desc=f"epoch {epoch}/{args.epochs}")
        for x, y in bar:
            x, y = x.to(device), y.to(device)
            loss = loss_fn(logits_at(model, x), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step(); sched.step()
            running += loss.item()
            bar.set_postfix(loss=f"{loss.item():.3f}", lr=f"{sched.get_last_lr()[0]:.1e}")
        res = evaluate(model, val_dl, device)
        minutes = (time.time() - t0) / 60
        roof = res["iou"].get("usable_roof")
        print(f"epoch {epoch}: loss {running / len(train_dl):.4f} | val mIoU {res['miou']} | "
              f"roof IoU {roof} | obstacles mIoU {res['miou_obstacles']} | {minutes:.1f} min")
        print("  per-class IoU:", res["iou"])
        with open(log_path, "a", newline="") as f:
            csv.writer(f).writerow([epoch, round(running / len(train_dl), 4), res["miou"],
                                    res["miou_obstacles"], roof, round(minutes, 2)])
        if res["miou"] > best:
            best = res["miou"]
            model.save_pretrained(args.out / "best")
            (args.out / "best" / "metrics.json").write_text(json.dumps({"epoch": epoch, **res}, indent=2))
            print(f"  saved new best -> {args.out / 'best'}")
    model.save_pretrained(args.out / "last")
    print(f"done. best val mIoU {best}")


if __name__ == "__main__":
    main()
