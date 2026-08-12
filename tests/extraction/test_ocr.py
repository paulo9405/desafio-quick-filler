"""Testes do caminho de OCR.

O primeiro é uma REGRESSÃO de um bug real: um limiar de confiança apagava
batidas corretas em silêncio. Ver o comentário em `app/extraction/ocr.py` e
`docs/PROCESSO.md`.
"""

from __future__ import annotations

from pathlib import Path

from app.extraction.extracted_page import ExtractionSource
from app.extraction.ocr import _words_from_tesseract, ocr_pages

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


def test_palavra_de_baixa_confianca_e_preservada():
    """REGRESSÃO: confiança baixa é informação, não motivo para apagar.

    No `time-card-03`, batidas corretas vinham com confiança 9, 10 e 16. Um
    limiar de 30 as descartava, e a página perdia batidas sem nenhum sinal —
    exatamente o "perder linhas em silêncio" que o desafio proíbe.
    """
    dados = {
        "text": ["19/12/2019", " 07:00d", "12:00d", ""],
        "conf": ["95", "10", "91", "-1"],
        "left": [67, 396, 518, 0],
        "top": [100, 100, 100, 0],
        "width": [120, 60, 60, 0],
        "height": [12, 12, 12, 0],
    }

    palavras = _words_from_tesseract(dados, escala=1.0)

    textos = [w.text for w in palavras]
    assert textos == ["19/12/2019", "07:00d", "12:00d"]

    # a confiança baixa continua acessível para a marcação de `?` na Fase 2
    duvidosa = next(w for w in palavras if w.text == "07:00d")
    assert duvidosa.confidence == 10.0


def test_linhas_estruturais_do_tesseract_sao_ignoradas():
    """conf = -1 marca bloco/parágrafo, não palavra. É o único descarte."""
    dados = {
        "text": ["", "palavra"],
        "conf": ["-1", "80"],
        "left": [0, 10],
        "top": [0, 10],
        "width": [0, 50],
        "height": [0, 12],
    }

    palavras = _words_from_tesseract(dados, escala=1.0)

    assert len(palavras) == 1
    assert palavras[0].text == "palavra"


def test_coordenadas_sao_convertidas_para_pontos_de_pdf():
    """Sem a conversão, um parser precisaria saber a origem do dado.

    A 300dpi a escala é 300/72 ≈ 4.1667, então 417 pixels ≈ 100 pontos.
    """
    escala = 300 / 72
    dados = {
        "text": ["x"],
        "conf": ["90"],
        "left": [int(100 * escala)],
        "top": [int(200 * escala)],
        "width": [int(50 * escala)],
        "height": [int(12 * escala)],
    }

    palavra = _words_from_tesseract(dados, escala)[0]

    assert abs(palavra.x0 - 100) < 1
    assert abs(palavra.top - 200) < 1
    assert abs((palavra.x1 - palavra.x0) - 50) < 1


def test_ocr_le_um_pdf_real_sem_camada_de_texto():
    """Integração: uma página real, vetorial, atravessa o caminho de imagem.

    `payroll-04` tem camada de texto só no rodapé; o conteúdo é vetorial.
    Só a página 1 é processada para o teste não custar caro.
    """
    resultado = ocr_pages(
        pdf_path=str(EXEMPLOS / "payroll-04.pdf"),
        page_numbers=[1],
        lang="por",
        dpi=300,
        psm=6,
    )

    pagina = resultado[1]
    assert pagina.source is ExtractionSource.OCR
    assert pagina.page == 1
    assert len(pagina.words) > 50

    texto = pagina.text()
    assert "Recibo de Pagamento" in texto
    assert "SETEMBRO/2019" in texto
    # valores monetários chegam com a vírgula decimal preservada
    assert "953,36" in texto

    # toda palavra de OCR carrega confiança
    assert all(w.confidence is not None for w in pagina.words)
