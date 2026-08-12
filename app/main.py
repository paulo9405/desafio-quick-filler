"""Ponto de entrada da aplicação.

Contrato HTTP oficial (README da Quick Filler) — obrigatório e literal:

    POST /api/transcricoes
    GET  /api/transcricoes/{id}
    PUT  /api/transcricoes/{id}
    GET  /api/transcricoes/{id}/planilha?formato=xlsx|csv|json
    GET  /healthz
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import transcriptions
from app.api.deps import get_repository
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepara o ambiente antes de aceitar requisições."""
    settings.ensure_directories()
    get_repository().init_db()
    logger.info("aplicacao iniciada")
    yield


app = FastAPI(
    title="Quick Filler — Transcrição de documentos trabalhistas",
    description=(
        "Transcreve cartões de ponto e holerites em PDF para dados "
        "estruturados e planilhas."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(transcriptions.router)


@app.get("/healthz")
def healthz() -> dict:
    """200 quando a aplicação está de pé (exigido pelo contrato oficial)."""
    return {"status": "ok"}
