"""OCR das páginas sem camada de texto: pypdfium2 renderiza, Tesseract lê.

DUAS DECISÕES QUE IMPORTAM

1. `image_to_data`, não `image_to_string`.
   `image_to_string` devolve só texto. `image_to_data` devolve, por palavra, o
   texto, a bounding box e a **confiança**. Sem confiança e sem coordenadas não
   há como calibrar a marcação de `?` nem detectar coluna pelo cabeçalho — que
   são exatamente os dois pontos que a avaliação mede.

2. As coordenadas são convertidas de pixels para pontos de PDF.
   O Tesseract responde em pixels da imagem renderizada, que dependem do DPI.
   Converter aqui (`pontos = pixels * 72 / dpi`) mantém o `ExtractedPage`
   idêntico ao do texto nativo, e é o que permite que o mesmo parser funcione
   nos dois caminhos.

NOTA SOBRE QUALIDADE (ver docs/roadmap.md seção 2.1)

Dos quatro documentos sem camada de texto, três (`time-card-02`,
`time-card-03`, `payroll-04`) são PDFs vetoriais nítidos — o texto foi desenhado
como paths, sem objetos de fonte. Renderizados a 300dpi, o OCR tende a acertar
quase tudo. Só `time-card-04` é um scan real de baixa qualidade.

A calibração fina do OCR é trabalho da Fase 2; aqui o objetivo é produzir um
`ExtractedPage` válido pelo caminho de imagem.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

import pypdfium2 as pdfium
import pytesseract
from pytesseract import Output

from app.extraction.extracted_page import (
    ExtractedPage,
    ExtractionSource,
    Word,
    build_page,
)

PONTOS_POR_POLEGADA = 72.0

# NÃO EXISTE LIMIAR DE CONFIANÇA AQUI. É proposital, e custou um bug.
#
# A primeira versão descartava palavras com confiança abaixo de 30, sob a
# justificativa de que seriam ruído de borda ou artefato de digitalização.
# Medindo a saída real do Tesseract em `time-card-03`, essa regra apagava
# batidas CORRETAS:
#
#     '07:00d'  conf=10   leitura correta, descartada
#     '15:00d'  conf=16   leitura correta, descartada
#     '06:59d'  conf=9    leitura correta, descartada
#     '23:00€'  conf=25   leitura errada — caso de `?`, não de descarte
#
# Uma página perdia batidas em silêncio, que é exatamente o erro que o
# INSTRUCOES nomeia ("perder linhas em silêncio") e o oposto da regra central
# do desafio.
#
# Confiança baixa é INFORMAÇÃO, não motivo para apagar. Todas as palavras lidas
# são preservadas com sua confiança, e a Fase 2 decide o que marcar com `?`.
# Glifos de borda de tabela ('|', '—') também ficam: o parser os ignora por
# posição de coluna, e mantê-los é mais seguro que arriscar descartar dado.


def ocr_pages(
    pdf_path: str,
    page_numbers: Iterable[int],
    lang: str,
    dpi: int,
    psm: int,
) -> Dict[int, ExtractedPage]:
    """Roda OCR apenas nas páginas pedidas.

    Devolve um dicionário `numero_da_pagina -> ExtractedPage`, para o chamador
    encaixar no lugar certo sem depender de ordem.

    Recebe só as páginas necessárias de propósito: renderizar e passar OCR em
    página que já tem texto seria desperdício, e o próprio roadmap alerta para
    nunca aplicar OCR cegamente.
    """
    alvos = sorted(set(page_numbers))
    if not alvos:
        return {}

    escala = dpi / PONTOS_POR_POLEGADA
    resultado: Dict[int, ExtractedPage] = {}

    documento = pdfium.PdfDocument(pdf_path)
    try:
        for numero in alvos:
            pagina = documento[numero - 1]
            largura_pt = pagina.get_width()
            altura_pt = pagina.get_height()

            imagem = pagina.render(scale=escala).to_pil()
            try:
                dados = pytesseract.image_to_data(
                    imagem,
                    lang=lang,
                    config=f"--psm {psm}",
                    output_type=Output.DICT,
                )
            finally:
                imagem.close()

            resultado[numero] = build_page(
                page_number=numero,
                width=largura_pt,
                height=altura_pt,
                source=ExtractionSource.OCR,
                words=_words_from_tesseract(dados, escala),
            )
    finally:
        documento.close()

    return resultado


def _words_from_tesseract(dados: Dict[str, list], escala: float) -> List[Word]:
    """Converte a saída do Tesseract em `Word`, já em pontos de PDF."""
    palavras: List[Word] = []

    for indice, texto in enumerate(dados["text"]):
        texto = texto.strip()
        if not texto:
            continue

        try:
            confianca = float(dados["conf"][indice])
        except (TypeError, ValueError):
            continue

        # O Tesseract usa -1 para linhas de estrutura (bloco, parágrafo), que
        # não são palavras. É o único descarte feito aqui.
        if confianca < 0:
            continue

        esquerda = dados["left"][indice] / escala
        topo = dados["top"][indice] / escala
        largura = dados["width"][indice] / escala
        altura = dados["height"][indice] / escala

        palavras.append(
            Word(
                text=texto,
                x0=esquerda,
                x1=esquerda + largura,
                top=topo,
                bottom=topo + altura,
                confidence=confianca,
            )
        )

    return palavras
