"""Decide, por página, entre camada de texto e OCR.

O critério é a **presença de camada de texto útil na página**, nunca o nome do
arquivo nem o tipo do documento. O INSTRUCOES lista "assumir que todo PDF tem
camada de texto" entre os erros que derrubam entregas.

POR QUE A DECISÃO É POR PÁGINA E NÃO POR DOCUMENTO

Um PDF pode misturar páginas nativas e digitalizadas. Decidir por documento
faria uma página escaneada no meio de um documento nativo voltar vazia — que é
exatamente o "perder linhas em silêncio" que o desafio proíbe.

POR QUE UM LIMIAR, E POR QUE ESTE

`payroll-04` tem camada de texto, mas ela contém **apenas o rodapé** — o
carimbo de assinatura eletrônica. O conteúdo do recibo é vetorial. Testar
"tem alguma palavra?" mandaria essa página para o caminho nativo e devolveria
uma transcrição vazia.

Medição nos 8 documentos oficiais, palavras por página:

    conteúdo real ............ 158 a 701
    payroll-04 (só rodapé) ... 12
    sem camada de texto ...... 0

O limiar padrão de 40 fica confortavelmente entre os dois regimes. Não é um
número ajustado ao exemplo: é a distinção entre "uma página de documento
trabalhista, que tem dezenas de linhas de dados" e "uma página cujo texto é um
carimbo". Continua configurável por `QF_MIN_WORDS_TEXT_LAYER`.

Consequência de errar para o lado seguro: uma página realmente vazia vai para o
OCR, o OCR não encontra nada, e ela continua vazia — mais lenta, mas correta.
"""

from __future__ import annotations

from typing import List

from app.core.logging import get_logger
from app.extraction.extracted_page import ExtractedPage
from app.extraction.native_text import extract_native_pages
from app.extraction.ocr import ocr_pages

logger = get_logger(__name__)


def extract_document(
    pdf_path: str,
    min_words_text_layer: int,
    ocr_lang: str,
    ocr_dpi: int,
    ocr_psm: int,
) -> List[ExtractedPage]:
    """Extrai todas as páginas, escolhendo o caminho página a página."""
    paginas = extract_native_pages(pdf_path)

    precisam_ocr = [
        pagina.page for pagina in paginas if len(pagina.words) < min_words_text_layer
    ]

    if precisam_ocr:
        logger.info(
            "ocr necessario em %d de %d paginas", len(precisam_ocr), len(paginas)
        )
        resultado_ocr = ocr_pages(
            pdf_path=pdf_path,
            page_numbers=precisam_ocr,
            lang=ocr_lang,
            dpi=ocr_dpi,
            psm=ocr_psm,
        )
        paginas = [resultado_ocr.get(pagina.page, pagina) for pagina in paginas]

    return paginas
