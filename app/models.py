"""
app/models.py — SQLAlchemy ORM models for images and analysis_results.
"""
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum, Text, Uuid,
)
from sqlalchemy.orm import relationship

from app.db import Base


class ImageStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Image(Base):
    __tablename__ = "images"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(String(512), nullable=False)
    stored_path = Column(String(1024), nullable=False)
    content_type = Column(String(128), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    image_hash = Column(String(64), nullable=True)   # perceptual hash, set by worker
    status = Column(
        SAEnum(ImageStatus, name="imagestatus", create_type=True),
        nullable=False,
        default=ImageStatus.pending,
        index=True,
    )
    failure_reason = Column(Text, nullable=True)
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)

    results = relationship(
        "AnalysisResult",
        back_populates="image",
        cascade="all, delete-orphan",
        order_by="AnalysisResult.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Image id={self.id} status={self.status}>"


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Uuid(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    check_name = Column(String(64), nullable=False)
    passed = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False)   # 0.0–1.0, meaning varies per check (see README)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    image = relationship("Image", back_populates="results")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AnalysisResult image_id={self.image_id} check={self.check_name} passed={self.passed}>"
