"""
app/analysis/duplicate.py — Perceptual-hash duplicate detection.

Algorithm
---------
We use pHash (perceptual hash) from the `imagehash` library, which produces
a 64-bit hash that is robust to minor colour shifts, resizing, and JPEG
compression artefacts.  Two images are considered duplicates if their
Hamming distance (number of differing bits) is ≤ HAMMING_THRESHOLD.

Scope
-----
We compare against ALL previously-completed images in the database, not
just recent ones.  At demo scale (hundreds of images) this is acceptable;
at production scale you would maintain an index structure (e.g. VP-tree or
a dedicated near-duplicate service) and scope to a time window or
vehicle-ID-keyed subset.  This trade-off is documented in the README.

Score interpretation (0.0–1.0):
  1.0 → unique image (distance from nearest neighbour = 64 bits)
  0.0 → exact duplicate (distance = 0)
  score = (min_distance / 64), clamped to [0, 1]
`passed` = True when min_distance > HAMMING_THRESHOLD.
"""
from __future__ import annotations

from io import BytesIO
import imagehash
from PIL import Image

# ── Configurable ─────────────────────────────────────────────────────────────
HAMMING_THRESHOLD = 5   # ≤ 5 differing bits → duplicate


def compute_phash(image_bytes: bytes) -> str:
    """Compute the pHash of image_bytes and return it as a hex string."""
    pil_image = Image.open(BytesIO(image_bytes))
    return str(imagehash.phash(pil_image))


def detect_duplicate(image_bytes: bytes, existing_hashes: list[str]) -> dict:
    """
    Compute pHash of image_bytes and compare against existing_hashes.

    Parameters
    ----------
    image_bytes    : raw bytes of the image under test
    existing_hashes: list of pHash hex strings from previously-processed images

    Returns passed, score, details, and the computed hash.
    """
    current_hash = imagehash.phash(Image.open(BytesIO(image_bytes)))
    current_hash_str = str(current_hash)

    min_distance = 64  # maximum possible Hamming distance for a 64-bit hash
    nearest_hash: str | None = None

    for h_str in existing_hashes:
        try:
            other_hash = imagehash.hex_to_hash(h_str)
            distance = current_hash - other_hash
            if distance < min_distance:
                min_distance = distance
                nearest_hash = h_str
        except Exception:
            # Malformed stored hash — skip gracefully
            continue

    passed = min_distance > HAMMING_THRESHOLD
    # score: 1.0 = unique, 0.0 = exact duplicate
    score = round(min(min_distance / 64.0, 1.0), 4)

    return {
        "passed": passed,
        "score": score,
        "details": {
            "computed_hash": current_hash_str,
            "nearest_hash": nearest_hash,
            "hamming_distance": min_distance,
            "hamming_threshold": HAMMING_THRESHOLD,
            "compared_against": len(existing_hashes),
            "verdict": "unique" if passed else "duplicate",
            "scope_note": (
                "Compared against all previously-completed images. "
                "At large scale, scope this to a rolling window or indexed structure."
            ),
        },
    }
