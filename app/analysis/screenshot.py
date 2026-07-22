"""
app/analysis/screenshot.py — Screenshot / photo-of-photo heuristic.

This check combines two independent signals.  It is explicitly a heuristic —
it cannot definitively prove an image is a screenshot — and the `details`
field communicates this uncertainty to consumers.

Signals
-------
1. Missing EXIF metadata
   Real camera photos almost always embed EXIF (shutter speed, GPS, camera
   model, etc.).  Screenshots taken from phones/desktops typically have no
   EXIF at all, or only a timestamp from the screen-capture tool.
   → fires when `_getexif()` returns None or an empty dict.

2. Aspect ratio matches a common screen ratio
   We check if the image width/height ratio is within ±2 % of any of these
   common screen aspect ratios:
     16:9  (1.7778) — most Android phones landscape / desktop
     19.5:9 (2.1667) — modern tall smartphones
     4:3   (1.3333) — iPad, older phones
     9:16  (0.5625) — portrait phone screenshot
     9:19.5 (0.4615) — portrait tall phone

Score
-----
  0 signals fired → score 1.0  (likely genuine photo)
  1 signal  fired → score 0.5  (uncertain — flagged as potential screenshot)
  2 signals fired → score 0.0  (strong indication of screenshot)

`passed` = True when score > 0.4  (i.e. at most 1 signal fired — single
signal alone is not enough to call it a definitive failure, but is surfaced
as a warning in `issues_found`).

NOTE: This is a heuristic.  False positives (genuine photos that happen to
lack EXIF or have a 16:9 crop) are possible and acknowledged.
"""
from __future__ import annotations

from PIL import Image, ExifTags
from PIL.ExifTags import TAGS

# ── Configurable ─────────────────────────────────────────────────────────────
SCREEN_ASPECT_RATIOS = {
    "16:9": 16 / 9,
    "19.5:9": 19.5 / 9,
    "4:3": 4 / 3,
    "9:16": 9 / 16,
    "9:19.5": 9 / 19.5,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
}
ASPECT_RATIO_TOLERANCE = 0.02  # ±2 %
# Score below which `passed` flips to False (two signals must fire)
FAIL_THRESHOLD = 0.4


def _has_camera_exif(pil_image: Image.Image) -> bool:
    """Return True if the image contains non-trivial camera EXIF data."""
    try:
        exif_data = pil_image._getexif()  # type: ignore[attr-defined]
    except (AttributeError, Exception):
        exif_data = None

    if not exif_data:
        return False

    # Look for camera-specific tags: Make, Model, FocalLength, ISOSpeedRatings
    camera_tags = {"Make", "Model", "FocalLength", "ISOSpeedRatings", "ExposureTime"}
    tag_names = {TAGS.get(k, k) for k in exif_data.keys()}
    return bool(camera_tags & tag_names)


def _matches_screen_ratio(width: int, height: int) -> str | None:
    """
    Return the matched ratio name if the image dimensions match a common
    screen aspect ratio within tolerance, else None.
    """
    if height == 0:
        return None
    actual_ratio = width / height
    for name, ratio in SCREEN_ASPECT_RATIOS.items():
        if abs(actual_ratio - ratio) / ratio <= ASPECT_RATIO_TOLERANCE:
            return name
    return None


def detect_screenshot(image_bytes: bytes) -> dict:
    """
    Run screenshot heuristic on raw image bytes.

    Returns passed, score (0–1), details.
    """
    from io import BytesIO

    pil_image = Image.open(BytesIO(image_bytes))
    width, height = pil_image.size

    has_exif = _has_camera_exif(pil_image)
    matched_ratio = _matches_screen_ratio(width, height)

    signals_fired = 0
    if not has_exif:
        signals_fired += 1
    if matched_ratio is not None:
        signals_fired += 1

    score = max(0.0, 1.0 - signals_fired * 0.5)
    passed = score > FAIL_THRESHOLD

    return {
        "passed": passed,
        "score": round(score, 4),
        "details": {
            "has_camera_exif": has_exif,
            "matched_screen_ratio": matched_ratio,
            "signals_fired": signals_fired,
            "image_dimensions": {"width": width, "height": height},
            "disclaimer": (
                "This is a heuristic check based on EXIF metadata and aspect ratio. "
                "False positives are possible (e.g. photos with stripped EXIF or common crop ratios). "
                "A score ≤ 0.4 strongly suggests a screenshot; a score of 0.5 warrants manual review."
            ),
        },
    }
