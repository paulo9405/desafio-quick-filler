"""Configuração da aplicação, lida de variáveis de ambiente.

O README oficial exige "configuração por variável de ambiente" e "nenhum
segredo no repositório". Nenhum valor aqui é segredo — são limites operacionais
e caminhos — mas todos podem ser sobrescritos sem alterar código.

Optamos por uma dataclass simples lida de `os.environ` em vez de
`pydantic-settings`: são poucas opções, o comportamento é óbvio de ler, e evita
uma dependência a mais.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} precisa ser um inteiro, recebido: {raw!r}") from exc


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name) or default).expanduser()


@dataclass(frozen=True)
class Settings:
    """Configuração imutável, resolvida uma vez na inicialização."""

    # Persistência
    database_path: Path
    storage_dir: Path

    # Limites de upload (segurança — ver README oficial, seção de segurança)
    max_upload_bytes: int
    max_pdf_pages: int

    # Política de retenção: por quanto tempo o PDF e a transcrição permanecem.
    retention_hours: int

    # OCR
    ocr_lang: str
    ocr_dpi: int

    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=_env_path("QF_DATABASE_PATH", "./data/quickfiller.db"),
            storage_dir=_env_path("QF_STORAGE_DIR", "./data/pdfs"),
            max_upload_bytes=_env_int("QF_MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            max_pdf_pages=_env_int("QF_MAX_PDF_PAGES", 50),
            retention_hours=_env_int("QF_RETENTION_HOURS", 24),
            ocr_lang=os.environ.get("QF_OCR_LANG", "por"),
            ocr_dpi=_env_int("QF_OCR_DPI", 300),
            log_level=os.environ.get("QF_LOG_LEVEL", "INFO").upper(),
        )

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Devolve a configuração da aplicação (resolvida uma única vez)."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings_cache() -> None:
    """Limpa o cache — usado apenas em testes que mexem no ambiente."""
    global _settings
    _settings = None
