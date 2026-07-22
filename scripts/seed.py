"""
scripts/seed.py — Generate sample images for demo and testing.

Creates 5 sample images in sample_images/ using PIL:
  1. normal.jpg       — well-exposed, sharp (the baseline "good" image)
  2. blurry.jpg       — very blurry (uniform grey)
  3. dark.jpg         — under-exposed
  4. overexposed.jpg  — blown-out highlights
  5. screenshot_like.jpg — 16:9 ratio, no EXIF (simulates a screenshot crop)

Run from the project root:
    python scripts/seed.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage, ImageDraw

OUTPUT_DIR = Path(__file__).parent.parent / "sample_images"
OUTPUT_DIR.mkdir(exist_ok=True)


def save_jpeg(arr: np.ndarray, filename: str, quality: int = 90) -> None:
    img = PILImage.fromarray(arr.astype(np.uint8))
    path = OUTPUT_DIR / filename
    img.save(path, format="JPEG", quality=quality)
    print(f"  Created {path}  ({path.stat().st_size:,} bytes)")


def make_normal() -> None:
    """Sharp, normally-exposed vehicle-like image with checkerboard body."""
    arr = np.zeros((300, 400, 3), dtype=np.uint8)
    # Sky gradient
    for y in range(150):
        v = int(135 + y * 0.5)
        arr[y, :] = [v, v + 20, min(v + 40, 255)]
    # Vehicle body (checkerboard for high Laplacian variance → sharp)
    for i in range(0, 150, 20):
        for j in range(0, 400, 20):
            if (i // 20 + j // 20) % 2 == 0:
                arr[150 + i:150 + i + 20, j:j + 20] = [200, 50, 50]
            else:
                arr[150 + i:150 + i + 20, j:j + 20] = [180, 40, 40]
    save_jpeg(arr, "normal.jpg")


def make_blurry() -> None:
    """Nearly uniform grey — very low Laplacian variance."""
    arr = np.full((300, 400, 3), 130, dtype=np.uint8)
    arr[100:200, 100:300] = 120   # one faint region
    save_jpeg(arr, "blurry.jpg")


def make_dark() -> None:
    """Severely under-exposed."""
    arr = np.full((300, 400, 3), 8, dtype=np.uint8)
    arr[140:160, 180:220] = 20    # barely-visible shape
    save_jpeg(arr, "dark.jpg")


def make_overexposed() -> None:
    """Blown-out highlights."""
    arr = np.full((300, 400, 3), 248, dtype=np.uint8)
    arr[100:200, 100:300] = 255
    save_jpeg(arr, "overexposed.jpg")


def make_screenshot_like() -> None:
    """16:9 aspect ratio image with no EXIF — both screenshot signals fire."""
    # 1280×720 is the canonical 16:9 resolution
    arr = np.full((720, 1280, 3), 235, dtype=np.uint8)
    # Draw a simple "browser chrome" suggestion
    arr[:40, :] = [50, 50, 50]    # dark top bar
    arr[40:80, :] = [240, 240, 240]  # address bar
    # Status bar icons (simple rectangles)
    arr[10:30, 20:120] = [80, 80, 80]
    save_jpeg(arr, "screenshot_like.jpg", quality=75)


if __name__ == "__main__":
    print(f"Generating sample images in {OUTPUT_DIR} …")
    make_normal()
    make_blurry()
    make_dark()
    make_overexposed()
    make_screenshot_like()
    print("Done.")
