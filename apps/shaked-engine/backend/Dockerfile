# Backend image for Render. Build context is the repo root, because the Layer A
# seed reads POC/layer_a/data relative to the repo (seed_layer_a.py: parents[6]).
#   docker build -f apps/shaked-engine/backend/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

# tesseract + Hebrew for OCR, DejaVu for the Hebrew PDF export, libgl/glib for OpenCV.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-heb fonts-dejavu-core libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /repo/apps/shaked-engine/backend

COPY apps/shaked-engine/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY POC/layer_a/data /repo/POC/layer_a/data
COPY apps/shaked-engine/backend/ .

# Render injects $PORT. Migrations run on every start; they are idempotent.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
