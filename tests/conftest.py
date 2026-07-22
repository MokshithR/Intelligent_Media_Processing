"""
tests/conftest.py — Shared pytest fixtures.

Uses an in-memory SQLite database for DB-touching tests and a real TestClient
for integration tests.  Analysis unit tests use synthesized PIL images and
don't touch the DB at all.
"""
from __future__ import annotations

import io
import os
import pytest
from unittest.mock import patch

# Point settings at SQLite for unit tests so no Postgres is needed
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("UPLOAD_DIR", "/tmp/test_uploads")

import numpy as np
from PIL import Image as PILImage


# ── Synthesized image factories ───────────────────────────────────────────────

def make_sharp_image_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create a sharp checkerboard image with high Laplacian variance."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    # Checkerboard pattern — maximises edge energy
    for i in range(0, height, 20):
        for j in range(0, width, 20):
            if (i // 20 + j // 20) % 2 == 0:
                arr[i:i+20, j:j+20] = 255
    return _ndarray_to_bytes(arr)


def make_blurry_image_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create a nearly uniform (very blurry) image."""
    arr = np.full((height, width, 3), 128, dtype=np.uint8)
    # Add tiny noise so it decodes as a valid image
    arr[0, 0] = [130, 130, 130]
    return _ndarray_to_bytes(arr)


def make_dark_image_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create an under-exposed (very dark) image."""
    arr = np.full((height, width, 3), 10, dtype=np.uint8)
    return _ndarray_to_bytes(arr)


def make_bright_image_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create an over-exposed (very bright) image."""
    arr = np.full((height, width, 3), 245, dtype=np.uint8)
    return _ndarray_to_bytes(arr)


def make_normal_image_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create a normally-exposed image."""
    arr = np.full((height, width, 3), 128, dtype=np.uint8)
    # Add some variation
    arr[50:150, 50:150] = [100, 120, 140]
    return _ndarray_to_bytes(arr)


def make_16_9_image_bytes() -> bytes:
    """Create a 16:9 image (matches a common screen ratio)."""
    return _ndarray_to_bytes(np.full((180, 320, 3), 128, dtype=np.uint8))


def _ndarray_to_bytes(arr: np.ndarray) -> bytes:
    """Convert an ndarray to JPEG bytes."""
    img = PILImage.fromarray(arr.astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sharp_image() -> bytes:
    return make_sharp_image_bytes()


@pytest.fixture
def blurry_image() -> bytes:
    return make_blurry_image_bytes()


@pytest.fixture
def dark_image() -> bytes:
    return make_dark_image_bytes()


@pytest.fixture
def bright_image() -> bytes:
    return make_bright_image_bytes()


@pytest.fixture
def normal_image() -> bytes:
    return make_normal_image_bytes()


@pytest.fixture
def screen_ratio_image() -> bytes:
    return make_16_9_image_bytes()
