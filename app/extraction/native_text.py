"""Extração da camada de texto nativa, via pdfplumber.

Usa `extract_words()` — palavras com bounding box — e não `extract_text()`.

O motivo está nos documentos reais: em `payroll-01` a extração linear colapsa
espaços (`REMUNERAÇÃOMES`, `BASEDECALCULODOINSS`). Como `label` vira nome de
coluna na planilha, um label corrompido contamina o export inteiro. Palavras
com coordenadas permitem reconstruir o texto corretamente e, mais importante,
identificar a qual coluna cada valor pertence.
"""

from __future__ import annotations

from typing import List

import pdfplumber

from app.extraction.extracted_page import (
    ExtractedPage,
    ExtractionSource,
    Word,
    build_page,
)


def extract_native_pages(pdf_path: str) -> List[ExtractedPage]:
    """Extrai todas as páginas pela camada de texto.

    Páginas sem camada de texto voltam com `words` vazia — cabe ao chamador
    decidir enviá-las para OCR.
    """
    paginas: List[ExtractedPage] = []
    with pdfplumber.open(pdf_path) as pdf:
        for indice, page in enumerate(pdf.pages, start=1):
            paginas.append(_extract_page(page, indice))
    return paginas


def _extract_page(page, page_number: int) -> ExtractedPage:
    palavras = [
        Word(
            text=item["text"],
            x0=float(item["x0"]),
            x1=float(item["x1"]),
            top=float(item["top"]),
            bottom=float(item["bottom"]),
            confidence=None,  # texto nativo não tem confiança — ver ExtractedPage
        )
        for item in page.extract_words(use_text_flow=False, keep_blank_chars=False)
        if item["text"].strip()
    ]

    return build_page(
        page_number=page_number,
        width=float(page.width),
        height=float(page.height),
        source=ExtractionSource.TEXTO_NATIVO,
        words=palavras,
    )
