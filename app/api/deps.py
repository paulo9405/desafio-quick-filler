"""Montagem das dependências da API.

Os serviços são criados uma única vez (`lru_cache`) e injetados nas rotas via
`Depends`. Isso mantém a camada HTTP sem conhecer SQLite, pdfplumber ou
Tesseract — e permite trocar qualquer um deles em teste.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.repositories.transcription_repository import TranscriptionRepository
from app.services.document_service import DocumentService
from app.services.pipeline import processar_documento
from app.services.transcription_service import TranscriptionService


@lru_cache(maxsize=1)
def get_repository() -> TranscriptionRepository:
    settings = get_settings()
    repository = TranscriptionRepository(settings.database_path)
    repository.init_db()
    return repository


@lru_cache(maxsize=1)
def get_document_service() -> DocumentService:
    settings = get_settings()
    return DocumentService(
        storage_dir=settings.storage_dir,
        max_upload_bytes=settings.max_upload_bytes,
        max_pdf_pages=settings.max_pdf_pages,
    )


@lru_cache(maxsize=1)
def get_transcription_service() -> TranscriptionService:
    settings = get_settings()
    return TranscriptionService(
        repository=get_repository(),
        documents=get_document_service(),
        pipeline=processar_documento,
        retention_hours=settings.retention_hours,
        max_simultaneos=settings.max_processamento_simultaneo,
    )


def reset_dependency_cache() -> None:
    """Limpa os caches — usado apenas em testes."""
    get_repository.cache_clear()
    get_document_service.cache_clear()
    get_transcription_service.cache_clear()
