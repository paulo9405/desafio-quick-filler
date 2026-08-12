"""Testes dos quatro avisos derivados e da regra de destaque.

Por que estes casos: os avisos são o mecanismo que faz "um número errado nunca
passar despercebido". Errar para mais enche a planilha de alarme e a pessoa
para de olhar; errar para menos deixa o erro chegar ao cliente.

As regras finas — dezembro→janeiro e competência ilegível — vêm literalmente do
README e são fáceis de quebrar sem perceber.
"""

from __future__ import annotations

from app.services.warnings_service import (
    Severidade,
    avaliar_cartao_ponto,
    avaliar_holerite,
)


def _dia(date_raw, horarios=()):
    return {
        "date_raw": date_raw,
        "punches": [
            {"kind": "IN", "time_raw": h, "time_hhmm": h} for h in horarios
        ],
    }


def _cartao(dias):
    return {"pages": [{"page": 1, "days": dias}]}


def _pagina(page, mes, ano, fields=None, bases=None):
    return {
        "page": page,
        "month": mes,
        "year": ano,
        "fields": fields if fields is not None else [],
        "bases": bases if bases is not None else [],
    }


def _codigos(avaliacoes):
    return [[a.codigo for a in av.avisos] for av in avaliacoes]


# ------------------------------------------------------------ batidas ímpares


def test_batidas_impares_geram_aviso_amarelo():
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("21/05/2019", ["08:00", "12:00", "13:00"])])
    )

    assert _codigos(avaliacoes) == [["batidas_impares"]]
    assert avaliacoes[0].severidade is Severidade.AMARELO
    assert "falta uma entrada ou uma saída" in avaliacoes[0].motivos[0]


def test_batidas_pares_nao_geram_aviso():
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("21/05/2019", ["08:00", "12:00", "13:00", "18:00"])])
    )
    assert _codigos(avaliacoes) == [[]]


def test_dia_sem_batida_nao_e_impar():
    """Zero é par. Um domingo sem batida não é problema de leitura."""
    avaliacoes = avaliar_cartao_ponto(_cartao([_dia("21/05/2019", [])]))
    assert _codigos(avaliacoes) == [[]]


# ------------------------------------------------------------ sequência de data


def test_datas_consecutivas_nao_geram_aviso():
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("30/04/2019"), _dia("01/05/2019"), _dia("02/05/2019")])
    )
    assert _codigos(avaliacoes) == [[], [], []]


def test_salto_na_data_gera_aviso_vermelho():
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("01/05/2019"), _dia("05/05/2019")])
    )

    assert _codigos(avaliacoes) == [[], ["data_nao_sequencial"]]
    assert avaliacoes[1].severidade is Severidade.VERMELHO


def test_data_impossivel_e_sinalizada():
    """O enunciado usa `38/07` como exemplo de erro de leitura."""
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("01/07/2019"), _dia("38/07/2019"), _dia("03/07/2019")])
    )

    assert "data_nao_sequencial" in _codigos(avaliacoes)[1]


def test_data_ilegivel_nao_quebra_a_cadeia():
    """Mesmo princípio que o README define para competências.

    A data do meio não dá para interpretar; as duas legíveis continuam
    consecutivas e não devem gerar alarme falso.
    """
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("01/07/2019"), _dia("0?/07/2019"), _dia("02/07/2019")])
    )

    assert _codigos(avaliacoes)[0] == []
    assert "data_nao_sequencial" not in _codigos(avaliacoes)[2]


# --------------------------------------------------------------- incerteza


def test_interrogacao_apenas_no_raw_dispara_o_amarelo():
    """O CASO REAL de `time-card-03`, e o ponto mais fácil de errar.

    `time_raw = "23:00?"` com `time_hhmm = "23:00"`: a célula exibida na
    planilha não tem `?` nenhum. Procurar a marcação no texto da célula não
    encontraria nada e a linha nunca seria destacada.
    """
    dia = {
        "date_raw": "27/01/2020",
        "punches": [
            {"kind": "IN", "time_raw": "14:56", "time_hhmm": "14:56"},
            {"kind": "OUT", "time_raw": "23:00?", "time_hhmm": "23:00"},
        ],
    }

    avaliacoes = avaliar_cartao_ponto(_cartao([dia]))

    assert _codigos(avaliacoes) == [["leitura_incerta"]]
    assert avaliacoes[0].severidade is Severidade.AMARELO


def test_incerteza_na_data_dispara_o_amarelo():
    avaliacoes = avaliar_cartao_ponto(_cartao([_dia("2?/05/2019", ["08:00", "12:00"])]))
    assert "leitura_incerta" in _codigos(avaliacoes)[0]


# ------------------------------------------------------------- precedência


def test_vermelho_ganha_de_amarelo_na_mesma_linha():
    """Regra literal do README."""
    avaliacoes = avaliar_cartao_ponto(
        _cartao([_dia("01/05/2019"), _dia("09/05/2019", ["08:00"])])
    )

    segunda = avaliacoes[1]
    assert {a.codigo for a in segunda.avisos} == {
        "batidas_impares",
        "data_nao_sequencial",
    }
    assert segunda.severidade is Severidade.VERMELHO


# ------------------------------------------------------------------ holerite


def test_competencias_consecutivas_nao_geram_aviso():
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "10", "2019", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "11", "2019", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )
    assert _codigos(avaliacoes) == [[], []]


def test_dezembro_para_janeiro_e_sequencia_valida():
    """Regra literal do README, e o caso real de `payroll-03`."""
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "12", "2019", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "01", "2020", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )

    assert _codigos(avaliacoes) == [[], []]


def test_dezembro_para_janeiro_do_mesmo_ano_e_invalido():
    """A virada precisa somar um ano — senão a checagem seria só do mês."""
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "12", "2019", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "01", "2019", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )

    assert "mes_nao_sequencial" in _codigos(avaliacoes)[1]


def test_mes_com_salto_gera_aviso_vermelho():
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "01", "2020", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "03", "2020", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )

    assert _codigos(avaliacoes)[1] == ["mes_nao_sequencial"]
    assert avaliacoes[1].severidade is Severidade.VERMELHO


def test_competencia_ilegivel_nao_quebra_a_cadeia():
    """Regra literal do README, e a mais fácil de implementar errado.

    "páginas cuja competência não deu para ler não quebram a cadeia,
     comparam-se as próximas legíveis entre si"

    Sem isso, a página ilegível geraria um aviso e a seguinte geraria outro —
    alarme falso em cascata sobre dados corretos.
    """
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "03", "2020", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "", "", [{"label": "x", "value": "1,00"}]),
                _pagina(3, "04", "2020", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )

    assert "mes_nao_sequencial" not in _codigos(avaliacoes)[1]
    assert "mes_nao_sequencial" not in _codigos(avaliacoes)[2]


def test_mes_impossivel_conta_como_ilegivel():
    """Um `13` no meio não precisa de flag própria — precisa não quebrar a
    comparação entre as vizinhas legíveis."""
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "03", "2020", [{"label": "x", "value": "1,00"}]),
                _pagina(2, "13", "2020", [{"label": "x", "value": "1,00"}]),
                _pagina(3, "04", "2020", [{"label": "x", "value": "1,00"}]),
            ]
        }
    )

    assert "mes_nao_sequencial" not in _codigos(avaliacoes)[2]


def test_pagina_vazia_gera_aviso_amarelo():
    avaliacoes = avaliar_holerite({"pages": [_pagina(1, "01", "2020")]})

    assert _codigos(avaliacoes) == [["pagina_vazia"]]
    assert avaliacoes[0].severidade is Severidade.AMARELO


def test_pagina_com_apenas_bases_nao_e_vazia():
    """Saiu dado da página, mesmo que nenhuma verba."""
    avaliacoes = avaliar_holerite(
        {"pages": [_pagina(1, "01", "2020", [], [{"label": "Base", "value": "1,00"}])]}
    )
    assert _codigos(avaliacoes) == [[]]


def test_incerteza_em_valor_de_holerite_dispara_amarelo():
    avaliacoes = avaliar_holerite(
        {
            "pages": [
                _pagina(1, "01", "2020", [{"label": "Salário", "value": "2.3?9,77"}])
            ]
        }
    )
    assert "leitura_incerta" in _codigos(avaliacoes)[0]
