"""Testes do contrato interno `ExtractedPage`.

Por que estes casos: o agrupamento em linhas é a base de todo parser. Se ele
juntar duas linhas ou partir uma, todo layout lê errado — e o sintoma aparece
longe da causa.
"""

from __future__ import annotations

from app.extraction.extracted_page import (
    ExtractedPage,
    ExtractionSource,
    Word,
)


def _word(text: str, x0: float, top: float, altura: float = 10.0) -> Word:
    return Word(text=text, x0=x0, x1=x0 + 20, top=top, bottom=top + altura)


def _page(words) -> ExtractedPage:
    return ExtractedPage(
        page=1,
        width=595.0,
        height=842.0,
        source=ExtractionSource.TEXTO_NATIVO,
        words=list(words),
    )


def test_palavras_da_mesma_linha_ficam_juntas_e_ordenadas():
    """Ordem de leitura é esquerda para direita, independente da ordem de entrada."""
    pagina = _page(
        [
            _word("Saida", x0=300, top=100),
            _word("Entrada", x0=100, top=100),
            _word("Dia", x0=10, top=100.4),  # leve variação vertical
        ]
    )

    linhas = pagina.lines()

    assert len(linhas) == 1
    assert linhas[0].text == "Dia Entrada Saida"


def test_linhas_diferentes_nao_se_misturam():
    pagina = _page(
        [
            _word("linha1", x0=10, top=100),
            _word("linha2", x0=10, top=130),
            _word("linha3", x0=10, top=160),
        ]
    )

    assert [linha.text for linha in pagina.lines()] == ["linha1", "linha2", "linha3"]


def test_words_between_le_uma_coluna_por_faixa():
    """Ler coluna por faixa horizontal é o que substitui coordenada fixa."""
    pagina = _page(
        [
            _word("08:00", x0=100, top=100),  # coluna Jornada
            _word("09:03", x0=200, top=100),  # coluna Entrada
            _word("14:05", x0=300, top=100),  # coluna Saida
        ]
    )
    linha = pagina.lines()[0]

    # faixa da coluna "Entrada" apenas
    dentro = linha.words_between(190, 290)

    assert [w.text for w in dentro] == ["09:03"]


def test_pagina_vazia_nao_quebra():
    pagina = _page([])
    assert pagina.is_empty
    assert pagina.lines() == []
    assert pagina.text() == ""


def test_texto_nativo_nao_inventa_confianca():
    """`None` significa "não se aplica", nunca 100.

    Preencher com um valor inventado destruiria a informação que permite
    calibrar incerteza mais adiante.
    """
    pagina = _page([_word("teste", x0=10, top=10)])
    assert pagina.words[0].confidence is None
