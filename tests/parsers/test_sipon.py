"""Testes do parser SIPON contra o documento real `time-card-01.pdf`.

Por que estes casos: cada um trava uma armadilha concreta medida no documento,
não um comportamento hipotético. São os erros que o INSTRUCOES nomeia —
perder linhas em silêncio, ordenar registros, coordenadas fixas — verificados
contra o PDF que a Quick Filler forneceu.
"""

from __future__ import annotations

import calendar
import re
from pathlib import Path

import pytest

from app.extraction.extracted_page import ExtractedPage, ExtractionSource, Word
from app.extraction.native_text import extract_native_pages
from app.parsers.timesheet.sipon import SiponTimesheetParser

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


@pytest.fixture(scope="module")
def value():
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    return SiponTimesheetParser().parse(paginas)


# ------------------------------------------------------- estrutura e contagem


def test_todas_as_paginas_do_pdf_aparecem_na_saida(value):
    assert [pagina["page"] for pagina in value["pages"]] == [1, 2, 3, 4, 5]


def test_cada_pagina_tem_exatamente_os_dias_do_mes(value):
    """A prova mais forte contra perda silenciosa e contra dia duplicado.

    O documento traz 33, 33, 34, 32 e 32 LINHAS de dia, por causa das linhas de
    continuação — algumas repetindo o número do dia. Os dias reais são 31, 31,
    30, 31 e 30, e isso é conferido contra o calendário, não contra um número
    copiado da amostra.
    """
    for pagina in value["pages"]:
        datas = [dia["date_raw"] for dia in pagina["days"]]
        casado = re.match(r"^\d{2}/(\d{2})/(\d{4})$", datas[0])
        assert casado, f"date_raw inesperado: {datas[0]!r}"

        mes, ano = int(casado.group(1)), int(casado.group(2))
        dias_no_mes = calendar.monthrange(ano, mes)[1]

        assert len(pagina["days"]) == dias_no_mes
        assert len(set(datas)) == len(datas), "dia duplicado na saída"


def test_ordem_do_documento_e_preservada(value):
    """A saída segue o documento, de cima para baixo. Nunca ordenada."""
    for pagina in value["pages"]:
        numeros = [int(dia["date_raw"][:2]) for dia in pagina["days"]]
        assert numeros == sorted(numeros)  # neste documento coincidem
        assert numeros[0] == 1


def test_dias_sem_batida_permanecem_como_linha(value):
    """`punches: []` é linha válida — descartar seria perder dia."""
    primeira = value["pages"][0]
    vazios = [dia for dia in primeira["days"] if dia["punches"] == []]

    assert len(vazios) == 10  # fins de semana e feriado de julho/2012
    assert vazios[0]["date_raw"] == "01/07/2012"  # domingo


# ----------------------------------------------------------------- armadilhas


def test_coluna_jornada_nunca_vira_batida(value):
    """A jornada prevista (`08:00`) aparece em TODA linha do documento.

    Um regex de `HH:MM` na linha capturaria 153 falsas batidas. Só a detecção
    de coluna evita isso.
    """
    batidas_de_jornada = [
        batida
        for pagina in value["pages"]
        for dia in pagina["days"]
        for batida in dia["punches"]
        if batida["time_raw"] == "08:00"
    ]

    assert batidas_de_jornada == []


def test_coluna_qtde_nunca_vira_batida(value):
    """`Qtde` traz valores como `00:13`, no mesmo formato das batidas.

    Nenhuma batida real deste documento começa com `00:`, porque a jornada é
    diurna — então qualquer `00:MM` na saída denunciaria vazamento da coluna.
    """
    vazadas = [
        batida
        for pagina in value["pages"]
        for dia in pagina["days"]
        for batida in dia["punches"]
        if batida["time_raw"].startswith("00:")
    ]

    assert vazadas == []


def test_linha_de_continuacao_que_repete_o_dia_e_mesclada(value):
    """Dia 17 de julho ocupa DUAS linhas, ambas com "17 - TER" impresso.

    Sem tratar isso, a saída teria dois dias 17, e o aviso de data não
    sequencial dispararia em cascata sobre dados corretos.
    """
    julho = value["pages"][0]["days"]
    dia_17 = [dia for dia in julho if dia["date_raw"] == "17/07/2012"]

    assert len(dia_17) == 1
    assert [batida["time_raw"] for batida in dia_17[0]["punches"]] == [
        "09:09",
        "13:01",
        "14:16",
        "18:50",
    ]


def test_linha_de_continuacao_sem_numero_do_dia_e_mesclada(value):
    """Caso comum: o segundo par vem na linha seguinte, sem o dia."""
    dia_2 = value["pages"][0]["days"][1]

    assert dia_2["date_raw"] == "02/07/2012"
    assert [batida["time_raw"] for batida in dia_2["punches"]] == [
        "09:03",
        "14:05",
        "15:12",
        "18:36",
    ]


def test_anomalia_real_do_documento_e_preservada(value):
    """29/10/2012 tem UMA batida no documento: `29 - SEG  08:00  09:23`.

    O parser não pode completar, descartar nem esconder. A linha fica com
    número ímpar de batidas, que é o que o aviso da Fase 2 vai destacar.
    """
    outubro = value["pages"][3]["days"]
    dia_29 = next(dia for dia in outubro if dia["date_raw"] == "29/10/2012")

    assert len(dia_29["punches"]) == 1
    assert dia_29["punches"][0]["time_raw"] == "09:23"
    assert dia_29["punches"][0]["kind"] == "IN"


# --------------------------------------------------------------- IN/OUT e raw


def test_kind_vem_da_coluna(value):
    """`Entrada` → IN, `Saida` → OUT, lido do cabeçalho.

    Neste documento as colunas se alternam, então o resultado coincide com a
    alternância por posição — mas a origem é semântica, e é isso que sustenta
    layouts com célula vazia no meio.
    """
    dia_2 = value["pages"][0]["days"][1]
    assert [batida["kind"] for batida in dia_2["punches"]] == [
        "IN",
        "OUT",
        "IN",
        "OUT",
    ]


def test_time_raw_e_preservado_e_hhmm_normalizado(value):
    for pagina in value["pages"]:
        for dia in pagina["days"]:
            for batida in dia["punches"]:
                assert re.match(r"^\d{1,2}:\d{2}$", batida["time_raw"])
                assert re.match(r"^\d{2}:\d{2}$", batida["time_hhmm"])


# ------------------------------------------------------------------ date_raw


def test_date_raw_compoe_a_data_completa(value):
    """Regra P1, confirmada oficialmente pela Quick Filler.

    A competência está impressa e legível no cabeçalho da página, e cada página
    cobre um único mês — a associação é segura, então compõe.
    """
    assert value["pages"][0]["days"][0]["date_raw"] == "01/07/2012"
    assert value["pages"][1]["days"][0]["date_raw"] == "01/08/2012"
    assert value["pages"][4]["days"][-1]["date_raw"] == "30/11/2012"


def test_date_raw_nao_compoe_quando_a_competencia_nao_e_legivel():
    """Regra P1: nunca completar mês/ano sob ambiguidade ou incerteza.

    Página sintética com a tabela, mas sem a linha `Mes/Ano`. O parser tem que
    devolver só o dia impresso, sem inventar competência.
    """

    def palavra(texto, x0, top):
        return Word(text=texto, x0=x0, x1=x0 + len(texto) * 5.0, top=top, bottom=top + 10)

    pagina = ExtractedPage(
        page=1,
        width=595.0,
        height=842.0,
        source=ExtractionSource.TEXTO_NATIVO,
        words=[
            palavra("Dia", 122, 90),
            palavra("Semana", 142, 90),
            palavra("Jornada", 188, 90),
            palavra("Entrada", 239, 90),
            palavra("Saida", 295, 90),
            palavra("Ocorrencia", 345, 90),
            palavra("Qtde", 442, 90),
            palavra("5", 132, 110),
            palavra("-", 142, 110),
            palavra("QUI", 152, 110),
            palavra("08:00", 193, 110),
            palavra("09:16", 244, 110),
            palavra("13:02", 295, 110),
        ],
    )

    resultado = SiponTimesheetParser().parse([pagina])
    dia = resultado["pages"][0]["days"][0]

    assert dia["date_raw"] == "5"
    assert len(dia["punches"]) == 2


# ------------------------------------------------------------------ detecção


def test_matches_reconhece_o_documento_certo():
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    assert SiponTimesheetParser().matches(paginas) == 1.0


def test_matches_recusa_um_holerite():
    paginas = extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))
    assert SiponTimesheetParser().matches(paginas) == 0.0


def test_matches_nao_procura_o_titulo_com_letras_espacadas():
    """O título é impresso `F O L H A  DE  F R E Q U E N C I A`.

    Procurar "FOLHA DE FREQUENCIA" nunca encontraria nada. Este teste trava a
    restrição para quem for mexer na impressão digital depois.
    """
    paginas = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    assert "FOLHA DE FREQUENCIA" not in paginas[0].text()
    assert SiponTimesheetParser().matches(paginas) > 0
