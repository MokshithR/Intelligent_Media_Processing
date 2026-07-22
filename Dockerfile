# ── Build stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Install system deps:
#   - tesseract-ocr + English language data (required by pytesseract)
#   - libgl1 / libglib2.0-0 (OpenCV runtime deps)
#   - libpq5 (psycopg2 runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached when requirements.txt unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create uploads directory (also mounted as a volume at runtime)
RUN mkdir -p /app/uploads

# ── API entrypoint ────────────────────────────────────────────────────────────
# Runs Alembic migrations, then starts uvicorn.
# Migrations are idempotent so this is safe to run on every restart.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]

EXPOSE 8000
