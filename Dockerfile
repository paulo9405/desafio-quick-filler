FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract e o pacote de idioma português são dependências de SISTEMA:
# não vêm via pip. Instalados já na Fase 1 de propósito — é a dependência com
# maior chance de quebrar build e deploy, e descobrir isso cedo é barato.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app

# Diretório de dados (banco SQLite + PDFs). Montado como volume no compose.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /srv
USER appuser

EXPOSE 8000

# Um único worker, de propósito: o processamento roda via BackgroundTasks no
# mesmo processo e o estado vive em SQLite. Mais workers exigiriam fila externa,
# que a decisão 3.3 do PROCESSO.md descartou por não haver necessidade.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
