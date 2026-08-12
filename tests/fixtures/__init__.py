"""Fixtures de extração gravadas.

POR QUE ISTO EXISTE

Rodar OCR nas 5 páginas de `time-card-03` leva mais de dois minutos. Repetir
isso a cada execução da suíte tornaria os testes caros demais para serem
rodados com frequência — e teste que não se roda não protege nada.

A solução é a mesma que o roadmap descreve para receber um layout novo na
sessão ao vivo: gravar a extração como fixture e testar o PARSER contra ela.

O que cada camada testa:

- o caminho de OCR de verdade continua coberto por um teste de integração que
  processa UMA página real (`tests/extraction/test_ocr.py`);
- os parsers são testados contra a extração gravada, que é a saída real do
  Tesseract sobre o documento oficial — não um dado inventado.

REGERAR

    python tests/fixtures/gerar.py

Regerar é necessário quando a extração mudar de comportamento. Se a fixture
mudar sem que a extração tenha mudado de propósito, é sinal de regressão.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import List

from app.extraction.extracted_page import ExtractedPage, ExtractionSource, Word

DIRETORIO = Path(__file__).resolve().parent


def salvar(nome: str, paginas: List[ExtractedPage]) -> Path:
    destino = DIRETORIO / f"{nome}.json.gz"
    dados = [
        {
            "page": pagina.page,
            "width": pagina.width,
            "height": pagina.height,
            "source": pagina.source.value,
            "words": [
                {
                    "text": palavra.text,
                    "x0": round(palavra.x0, 2),
                    "x1": round(palavra.x1, 2),
                    "top": round(palavra.top, 2),
                    "bottom": round(palavra.bottom, 2),
                    "confidence": palavra.confidence,
                }
                for palavra in pagina.words
            ],
        }
        for pagina in paginas
    ]
    with gzip.open(destino, "wt", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False)
    return destino


def carregar(nome: str) -> List[ExtractedPage]:
    origem = DIRETORIO / f"{nome}.json.gz"
    with gzip.open(origem, "rt", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    return [
        ExtractedPage(
            page=item["page"],
            width=item["width"],
            height=item["height"],
            source=ExtractionSource(item["source"]),
            words=[Word(**palavra) for palavra in item["words"]],
        )
        for item in dados
    ]
