"""
app/schemas.py — Pydantic request/response schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ─── Upload response ────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str = "Image uploaded successfully; processing queued."


# ─── Status ─────────────────────────────────────────────────────────────────

class ImageStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    failure_reason: Optional[str] = None


# ─── Analysis results ────────────────────────────────────────────────────────

class CheckResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_name: str
    passed: bool
    score: float
    details: dict[str, Any]
    created_at: datetime


class ImageResultsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    status: str
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    image_hash: Optional[str] = None
    issues_found: list[str]        # human-readable list of failed checks
    checks: list[CheckResult]


# ─── List endpoint ───────────────────────────────────────────────────────────

class ImageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    status: str
    content_type: str
    file_size_bytes: int
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class ImageListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ImageListItem]


# ─── Health ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
