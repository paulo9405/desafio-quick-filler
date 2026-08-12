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
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import transcriptions
from app.api.deps import get_repository
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

DIRETORIO_ESTATICO = Path(__file__).resolve().parent / "static"

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

# Interface de revisão: HTML + Bootstrap + JavaScript puro, sem build step e
# sem framework de frontend. O Bootstrap está versionado em `static/` em vez de
# vir de CDN, para a aplicação funcionar sem depender de rede externa.
app.mount(
    "/static", StaticFiles(directory=DIRETORIO_ESTATICO), name="static"
)


@app.get("/", include_in_schema=False)
def interface() -> FileResponse:
    """Página única da interface de revisão."""
    return FileResponse(DIRETORIO_ESTATICO / "index.html")


@app.get("/healthz")
def healthz() -> dict:
    """200 quando a aplicação está de pé (exigido pelo contrato oficial)."""
    return {"status": "ok"}
