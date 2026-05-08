FROM python:3.11-slim

# Instala dependências de sistema para OpenCV + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala dependências Python primeiro (camada de cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[quantize]"

# Copia código fonte
COPY easycount/ easycount/
COPY migrations/ migrations/
COPY alembic.ini .
COPY frontend/ frontend/
COPY config/ config/

# Aplica migrations e inicia a aplicação
CMD alembic upgrade head && uvicorn easycount.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
