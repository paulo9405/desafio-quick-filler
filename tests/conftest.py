"""Fixtures compartilhadas.

Cada teste roda contra um banco SQLite e um diretório de PDFs próprios, em
`tmp_path`. Nada é compartilhado entre testes, e nada toca o volume real.
"""

from __future__ import annotations

import importlib
import io
from pathlib import Path
from typing import Any, Callable, Dict

import pytest
from fastapi.testclient import TestClient

EXEMPLOS = Path(__file__).resolve().parents[1] / "exemplos"


def _preparar_ambiente(tmp_path, monkeypatch, sufixo: str = ""):
    """Isola configuração e recarrega a app com o ambiente do teste.

    A configuração é resolvida na importação de `app.main`, então as variáveis
    precisam existir antes do reload.
    """
    monkeypatch.setenv("QF_DATABASE_PATH", str(tmp_path / f"test{sufixo}.db"))
    monkeypatch.setenv("QF_STORAGE_DIR", str(tmp_path / f"pdfs{sufixo}"))
    monkeypatch.setenv("QF_LOG_LEVEL", "WARNING")

    from app.api import deps
    from app.core import config

    config.reset_settings_cache()
    deps.reset_dependency_cache()

    from app import main as main_module

    importlib.reload(main_module)
    return main_module


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """Cliente HTTP com o pipeline real (que ainda não tem parser)."""
    main_module = _preparar_ambiente(tmp_path, monkeypatch)

    with TestClient(main_module.app) as test_client:
        yield test_client

    from app.api import deps
    from app.core import config

    config.reset_settings_cache()
    deps.reset_dependency_cache()


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    """Cria um cliente com um pipeline substituído.

    Necessário para exercitar o ciclo completo (upload → revisão → correção →
    download) antes de existir um parser real. O pipeline é o único ponto
    trocado; todo o resto é o código de produção.
    """

    def _factory(pipeline: Callable[[str, str], Dict[str, Any]]) -> TestClient:
        main_module = _preparar_ambiente(tmp_path, monkeypatch, sufixo="-fake")

        from app.api import deps
        from app.core.config import get_settings
        from app.repositories.transcription_repository import TranscriptionRepository
        from app.services.document_service import DocumentService
        from app.services.transcription_service import TranscriptionService

        settings = get_settings()
        settings.ensure_directories()

        repository = TranscriptionRepository(settings.database_path)
        repository.init_db()

        service = TranscriptionService(
            repository=repository,
            documents=DocumentService(
                storage_dir=settings.storage_dir,
                max_upload_bytes=settings.max_upload_bytes,
                max_pdf_pages=settings.max_pdf_pages,
            ),
            pipeline=pipeline,
            retention_hours=settings.retention_hours,
        )

        main_module.app.dependency_overrides[deps.get_transcription_service] = (
            lambda: service
        )
        return TestClient(main_module.app)

    return _factory


@pytest.fixture
def pdf_valido() -> bytes:
    """Um PDF real do conjunto oficial fornecido pela Quick Filler."""
    return (EXEMPLOS / "time-card-01.pdf").read_bytes()


def upload(conteudo: bytes, tipo: str, filename: str = "documento.pdf"):
    """Monta o multipart do POST no formato exato do contrato."""
    return {
        "files": {"arquivo": (filename, io.BytesIO(conteudo), "application/pdf")},
        "data": {"tipo": tipo},
    }
