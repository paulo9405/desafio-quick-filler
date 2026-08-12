"""Testes da detecção de coluna por cabeçalho.

Por que estes casos: é o mecanismo que substitui coordenada absoluta, que o
INSTRUCOES nomeia como erro que quebra "na primeira variação de layout". Se ele
errar a faixa, todo parser lê a coluna errada.
"""

from __future__ import annotations

from app.extraction.columns import detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, ExtractionSource, Word


def _word(text: str, x0: float, top: float) -> Word:
    # largura proporcional ao texto, aproximando uma fonte monoespaçada
    return Word(text=text, x0=x0, x1=x0 + len(text) * 5.0, top=top, bottom=top + 10)


def _page(words) -> ExtractedPage:
    return ExtractedPage(
        page=1,
        width=595.0,
        height=842.0,
        source=ExtractionSource.TEXTO_NATIVO,
        words=list(words),
    )


def test_faixas_saem_do_cabecalho_e_nao_de_numero_fixo():
    pagina = _page(
        [
            _word("Dia", x0=100, top=50),
            _word("Entrada", x0=200, top=50),
            _word("Saida", x0=300, top=50),
        ]
    )

    layout = detect_columns(pagina, ("Dia", "Entrada", "Saida"))

    assert layout is not None
    entrada = layout.column("Entrada")
    # limite esquerdo é o meio do vão entre "Dia" e "Entrada"
    assert entrada.x0 == (115 + 200) / 2
    # limite direito é o meio do vão entre "Entrada" e "Saida"
    assert entrada.x1 == (235 + 300) / 2


def test_valor_e_atribuido_a_coluna_pelo_centro():
    """O caso que importa: separar batida de jornada e de quantidade."""
    pagina = _page(
        [
            _word("Dia", x0=100, top=50),
            _word("Jornada", x0=180, top=50),
            _word("Entrada", x0=280, top=50),
            _word("Qtde", x0=400, top=50),
            # linha de dados
            _word("2", x0=105, top=70),
            _word("08:00", x0=185, top=70),
            _word("09:03", x0=285, top=70),
            _word("00:13", x0=405, top=70),
        ]
    )

    layout = detect_columns(pagina, ("Dia", "Jornada", "Entrada", "Qtde"))
    linha_de_dados = [l for l in pagina.lines() if l.top > layout.header_top][0]

    assert layout.cell_text(linha_de_dados, "Dia") == "2"
    assert layout.cell_text(linha_de_dados, "Jornada") == "08:00"
    assert layout.cell_text(linha_de_dados, "Entrada") == "09:03"
    assert layout.cell_text(linha_de_dados, "Qtde") == "00:13"


def test_cabecalho_incompleto_nao_e_reconhecido():
    """Melhor não reconhecer o layout do que ler colunas erradas."""
    pagina = _page([_word("Dia", x0=100, top=50), _word("Entrada", x0=200, top=50)])

    assert detect_columns(pagina, ("Dia", "Entrada", "Saida")) is None


def test_deteccao_ignora_acento_e_caixa():
    """OCR erra acento com frequência; `Saída` e `Saida` são o mesmo título."""
    pagina = _page([_word("DIA", x0=100, top=50), _word("Saída", x0=200, top=50)])

    assert detect_columns(pagina, ("Dia", "Saida")) is not None
    assert normalizar("Saída") == "saida"


def test_tolera_erro_de_ocr_no_titulo_da_coluna():
    """Caso real e medido: o OCR erra o próprio cabeçalho.

    Em `time-card-03`, nas 5 páginas: `Ent1`→`Entl`, `Sai1`→`Sail`,
    `Sai2`→`Sai?`. Exigir igualdade exata tornaria o layout indetectável.
    """
    pagina = _page(
        [
            _word("Data", x0=15, top=50),
            _word("Entl", x0=95, top=50),  # era Ent1
            _word("Sail", x0=131, top=50),  # era Sai1
            _word("Sai?", x0=184, top=50),  # era Sai2
        ]
    )

    layout = detect_columns(pagina, ("Data", "Ent1", "Sai1", "Sai2"))

    assert layout is not None
    assert [c.name for c in layout.columns] == ["Data", "Ent1", "Sai1", "Sai2"]


def test_palavra_diferente_demais_nao_casa():
    """A tolerância não pode virar "casa com qualquer coisa"."""
    pagina = _page(
        [
            _word("Data", x0=15, top=50),
            _word("Observacao", x0=95, top=50),
        ]
    )

    assert detect_columns(pagina, ("Data", "Ent1")) is None


def test_cabecalho_verdadeiro_ganha_de_casamento_marginal():
    """Com tolerância, mais de uma linha pode casar. Vence a mais parecida.

    Aqui a linha 2 casa exato e precisa vencer a linha 1, que casaria só no
    limite do limiar.
    """
    pagina = _page(
        [
            # linha 1: casamento fraco
            _word("Data", x0=15, top=50),
            _word("Ento", x0=95, top=50),
            # linha 2: cabeçalho de verdade
            _word("Data", x0=15, top=90),
            _word("Ent1", x0=95, top=90),
        ]
    )

    layout = detect_columns(pagina, ("Data", "Ent1"))

    assert layout is not None
    assert layout.header_top == 90


def test_ultima_coluna_vai_ate_a_borda_da_pagina():
    """Valor mais largo que o título não pode cair fora da última coluna."""
    pagina = _page(
        [
            _word("Dia", x0=100, top=50),
            _word("Qtde", x0=400, top=50),
            _word("2", x0=105, top=70),
            _word("00:13", x0=440, top=70),  # transborda o título à direita
        ]
    )

    layout = detect_columns(pagina, ("Dia", "Qtde"))
    linha = [l for l in pagina.lines() if l.top > layout.header_top][0]

    assert layout.cell_text(linha, "Qtde") == "00:13"
