from __future__ import annotations

import random
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATES_DIR = REPO_ROOT / "plates"
IMAGES_DIR = PLATES_DIR / "images" / "images"
LABELS_DIR = PLATES_DIR / "yolo_labels"
OUTPUT_DIR = PLATES_DIR / "yolo_dataset"

VAL_FRACTION = 0.15
RANDOM_SEED = 42

IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"]


def find_image_for_label(stem: str) -> Path | None:
    for ext in IMAGE_EXTENSIONS:
        candidate = IMAGES_DIR / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def main():
    label_files = sorted(
        p for p in LABELS_DIR.glob("*.txt") if p.stem != "classes"
    )
    print(f"Found {len(label_files)} label files.")

    pairs = []
    missing = []
    for label_path in label_files:
        image_path = find_image_for_label(label_path.stem)
        if image_path is None:
            missing.append(label_path.name)
            continue
        pairs.append((image_path, label_path))

    print(f"Matched {len(pairs)} image/label pairs.")
    if missing:
        print(f"WARNING: {len(missing)} label files had no matching image:")
        for name in missing:
            print(f"  - {name}")

    random.seed(RANDOM_SEED)
    random.shuffle(pairs)

    split_idx = int(len(pairs) * (1 - VAL_FRACTION))
    train_pairs = pairs[:split_idx]
    val_pairs = pairs[split_idx:]
    print(f"Train: {len(train_pairs)}  Val: {len(val_pairs)}")

    for split_name, split_pairs in [("train", train_pairs), ("val", val_pairs)]:
        images_out = OUTPUT_DIR / "images" / split_name
        labels_out = OUTPUT_DIR / "labels" / split_name
        images_out.mkdir(parents=True, exist_ok=True)
        labels_out.mkdir(parents=True, exist_ok=True)

        for image_path, label_path in split_pairs:
            shutil.copy2(image_path, images_out / image_path.name)
            shutil.copy2(label_path, labels_out / label_path.name)

    data_yaml = OUTPUT_DIR / "data.yaml"
    data_yaml.write_text(
        f"path: {OUTPUT_DIR.as_posix()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"names:\n"
        f"  0: plate\n",
        encoding="utf-8",
    )
    print(f"Wrote {data_yaml}")
    print("Done.")


if __name__ == "__main__":
    main()