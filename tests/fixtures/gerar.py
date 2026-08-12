"""Regera as fixtures de extração a partir dos PDFs oficiais.

    docker run --rm -v "$PWD":/srv -w /srv quick-filler-app \
        python tests/fixtures/gerar.py

Só precisa ser rodado quando a extração mudar de comportamento de propósito.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from app.extraction.extractor import extract_document  # noqa: E402
from tests.fixtures import salvar  # noqa: E402

EXEMPLOS = RAIZ / "exemplos"

# Só documentos cuja extração é cara (OCR). Documentos com camada de texto são
# extraídos direto no teste — é rápido e evita fixture desnecessária.
DOCUMENTOS = ("time-card-03",)


def main() -> None:
    for nome in DOCUMENTOS:
        inicio = time.monotonic()
        paginas = extract_document(
            pdf_path=str(EXEMPLOS / f"{nome}.pdf"),
            min_words_text_layer=40,
            ocr_lang="por",
            ocr_dpi=300,
            ocr_psm=6,
        )
        destino = salvar(nome, paginas)
        palavras = sum(len(pagina.words) for pagina in paginas)
        print(
            f"{nome}: {len(paginas)} páginas, {palavras} palavras, "
            f"{time.monotonic() - inicio:.1f}s -> {destino.name}"
        )


if __name__ == "__main__":
    main()
