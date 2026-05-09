FROM python:3.11-slim AS model-exporter

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[export]"

COPY models/ models/
RUN python models/download_model.py


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[quantize]"

COPY --from=model-exporter /app/models/ models/

COPY easycount/ easycount/
COPY migrations/ migrations/
COPY alembic.ini .
COPY frontend/ frontend/
COPY config/ config/

CMD alembic upgrade head && uvicorn easycount.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
