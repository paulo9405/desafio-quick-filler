"""Pipeline de processamento: PDF → ExtractedPage → parser → JSON oficial.

    PDF
     ↓  extração (texto nativo ou OCR, decidido por página)
    ExtractedPage[]
     ↓  registry (qual layout sabe ler isto?)
    parser do layout
     ↓
    value no formato oficial

Nenhuma camada acima daqui conhece pdfplumber, Tesseract ou layout de
documento. Nenhum parser conhece HTTP, banco ou planilha.
"""

from __future__ import annotations

from typing import Any, Dict

from app.core.config import get_settings
from app.core.logging import get_logger
from app.extraction.extractor import extract_document
from app.parsers.registry import ParserRegistry
from app.services.transcription_service import LayoutNaoReconhecido

logger = get_logger(__name__)

MENSAGEM_LAYOUT_DESCONHECIDO = (
    "Não foi possível reconhecer o layout deste documento."
)

_registry = ParserRegistry()


def processar_documento(pdf_path: str, tipo: str) -> Dict[str, Any]:
    """Transforma um PDF no `value` do formato oficial.

    Levanta `LayoutNaoReconhecido` quando nenhum parser registrado sabe ler o
    documento — o que vira `status: "erro"` com mensagem legível, em vez de uma
    transcrição inventada.
    """
    settings = get_settings()

    paginas = extract_document(
        pdf_path=pdf_path,
        min_words_text_layer=settings.min_words_text_layer,
        ocr_lang=settings.ocr_lang,
        ocr_dpi=settings.ocr_dpi,
        ocr_psm=settings.ocr_psm,
    )

    parser = _registry.select(tipo, paginas)
    if parser is None:
        logger.info("nenhum parser reconheceu tipo=%s paginas=%d", tipo, len(paginas))
        raise LayoutNaoReconhecido(MENSAGEM_LAYOUT_DESCONHECIDO)

    return parser.parse(paginas)
