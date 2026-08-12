"""Parsers do bloco 2.5, validados contra os PDFs oficiais.

Cada caso trava uma armadilha real medida no documento correspondente. Vários
deles são REGRESSÃO de perda silenciosa encontrada durante a implementação.
"""

from __future__ import annotations

import calendar
from pathlib import Path

import pytest

from app.extraction.extractor import extract_document
from app.extraction.native_text import extract_native_pages
from app.parsers.payslip.declaracao_remuneracao import DeclaracaoRemuneracaoParser
from app.parsers.payslip.ficha_financeira import FichaFinanceiraParser
from app.parsers.payslip.recibo_pagamento import ReciboPagamentoParser
from app.parsers.timesheet.ponto_eletronico import PontoEletronicoParser

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


def _ocr(nome):
    return extract_document(
        str(EXEMPLOS / f"{nome}.pdf"),
        min_words_text_layer=40,
        ocr_lang="por",
        ocr_dpi=300,
        ocr_psm=6,
    )


# ============================================================ time-card-02


@pytest.fixture(scope="module")
def ponto_eletronico():
    return PontoEletronicoParser().parse(_ocr("time-card-02"))


def test_time_card_02_tem_todos_os_dias_do_mes(ponto_eletronico):
    """REGRESSÃO de perda silenciosa.

    O OCR cola o dia no dia da semana (`18QUA`, `18SAB`). Exigir um token
    puramente numérico fazia esses dias sumirem: agosto saía com 30 dias e
    setembro com 29. Conferido contra o calendário, não contra a amostra.
    """
    for pagina in ponto_eletronico["pages"]:
        datas = [d["date_raw"] for d in pagina["days"]]
        _dia, mes, ano = datas[0].split("/")
        assert len(datas) == calendar.monthrange(int(ano), int(mes))[1]
        assert len(set(datas)) == len(datas)


def test_time_card_02_le_batidas_em_intervalo(ponto_eletronico):
    """`12:00 - 18:15` na coluna Entrada/Saída e `15:00 - 15:15` no intervalo."""
    dia = next(
        d
        for d in ponto_eletronico["pages"][0]["days"]
        if d["date_raw"] == "17/05/2010"
    )

    assert [(p["kind"], p["time_hhmm"]) for p in dia["punches"]] == [
        ("IN", "12:00"),
        ("OUT", "18:15"),
        ("OUT", "15:00"),  # saiu para o intervalo
        ("IN", "15:15"),  # voltou
    ]


def test_time_card_02_separador_colado_nao_vira_incerteza(ponto_eletronico):
    """`08:56-` e `09:52-16:07` aparecem no documento.

    O `-` é separador de intervalo, não caractere ilegível. Marcá-lo com `?`
    seria acusar erro onde a leitura foi correta; ignorar o token colado
    custava uma batida.
    """
    marcadas = [
        p
        for pagina in ponto_eletronico["pages"]
        for d in pagina["days"]
        for p in d["punches"]
        if "?" in p["time_raw"]
    ]
    assert marcadas == []


def test_time_card_02_dias_sem_batida_permanecem(ponto_eletronico):
    dias = {d["date_raw"]: d["punches"] for d in ponto_eletronico["pages"][0]["days"]}
    assert dias["01/05/2010"] == []  # Feriado
    assert dias["02/05/2010"] == []  # Descanso Semanal


# ============================================================= payroll-04


@pytest.fixture(scope="module")
def recibo():
    return ReciboPagamentoParser().parse(_ocr("payroll-04"))


def test_payroll_04_emite_uma_entrada_por_pagina(recibo):
    """REGRESSÃO: cada página traz DUAS vias idênticas do mesmo recibo.

    Sem cortar na segunda via, toda verba e toda base saíam duplicadas.
    """
    assert len(recibo["pages"]) == 5
    assert [p["page"] for p in recibo["pages"]] == [1, 2, 3, 4, 5]
    assert len(recibo["pages"][0]["bases"]) == 8  # eram 16 antes do corte


def test_payroll_04_le_competencia_por_extenso(recibo):
    """`SETEMBRO/2019` → `09`. O OCR danifica os nomes, então a leitura é por
    similaridade: `PUTUBRO` ainda é reconhecido como outubro."""
    assert (recibo["pages"][0]["month"], recibo["pages"][0]["year"]) == ("09", "2019")
    assert recibo["pages"][1]["month"] == "10"


def test_payroll_04_label_nao_vaza_para_reference(recibo):
    """REGRESSÃO: `DESC ASS MEDICA AMIL` é largo e a última palavra caía na
    coluna `Qtde`, virando `reference`. Dois campos errados de uma vez."""
    campos = {c["label"]: c for c in recibo["pages"][0]["fields"]}
    assert "ESC ASS MEDICA AMIL" in campos
    assert campos["ESC ASS MEDICA AMIL"]["reference"] == ""


def test_payroll_04_separa_fields_de_bases(recibo):
    labels = {c["label"] for p in recibo["pages"] for c in p["fields"]}
    assert not any("TOTAL" in l.upper() or "LIQUIDO" in l.upper() for l in labels)

    bases = {b["label"] for b in recibo["pages"][0]["bases"]}
    assert "TOTAL DE PROVENTOS" in bases
    assert "LÍQUIDO A RECEBER" in bases


# ============================================================= payroll-02


@pytest.fixture(scope="module")
def declaracao():
    return DeclaracaoRemuneracaoParser().parse(
        extract_native_pages(str(EXEMPLOS / "payroll-02.pdf"))
    )


def test_payroll_02_dois_blocos_por_pagina_compartilham_a_pagina(declaracao):
    """`MÊS` e `ACERTO` na mesma página, com a mesma competência."""
    assert len(declaracao["pages"]) == 10
    assert [p["page"] for p in declaracao["pages"][:4]] == [1, 1, 2, 2]
    assert declaracao["pages"][0]["month"] == declaracao["pages"][1]["month"] == "08"


def test_payroll_02_nome_com_barra_nao_vira_reference(declaracao):
    """REGRESSÃO de perda silenciosa.

    A primeira versão distinguia referência de rótulo pela presença de `/`.
    A verba `192 ATFC-AD.TEMP.FATORES/COMI` tem barra NO NOME: o nome virou
    referência, o label ficou vazio e a linha desapareceu da saída.
    """
    campos = {c["code"]: c for c in declaracao["pages"][0]["fields"]}

    assert "192" in campos
    assert campos["192"]["label"] == "ATFC-AD.TEMP.FATORES/COMI"
    assert campos["192"]["reference"] == ""


def test_payroll_02_preserva_sinal_negativo(declaracao):
    campos = {c["code"]: c for c in declaracao["pages"][0]["fields"]}
    assert campos["803"]["value"] == "-433,20"
    assert campos["803"]["reference"] == "6.188,63"


def test_payroll_02_reference_textual(declaracao):
    """A coluna `Base / Saldo / Benefício` nem sempre traz número."""
    campos = {c["code"]: c for c in declaracao["pages"][1]["fields"]}
    assert campos["803"]["reference"] == "AC.SIST/0718"


# ============================================================= payroll-01


@pytest.fixture(scope="module")
def ficha():
    return FichaFinanceiraParser().parse(
        extract_native_pages(str(EXEMPLOS / "payroll-01.pdf"))
    )


def test_payroll_01_varias_competencias_por_pagina(ficha):
    """A ficha financeira empilha meses na mesma página.

    Todas as entradas de uma página compartilham o mesmo `page` — é o que o
    README descreve para este documento.
    """
    assert len(ficha["pages"]) == 30
    primeira_pagina = [p for p in ficha["pages"] if p["page"] == 1]
    assert len(primeira_pagina) == 6
    assert [p["month"] for p in primeira_pagina] == ["04", "05", "06", "07", "08", "09"]
    assert all(p["year"] == "2017" for p in primeira_pagina)


def test_payroll_01_le_os_tres_grupos_de_coluna(ficha):
    """REGRESSÃO: o valor do desconto vazava para o rótulo da base.

    Dividir por faixa derivada dos títulos colocava `30,67` no grupo
    RESULTADOS, produzindo a base `"30,67 BASEDECALCULODOINSS"`.
    """
    entrada = ficha["pages"][0]
    codigos = {c["code"] for c in entrada["fields"]}

    # rendimentos e descontos, ambos em `fields`
    assert {"", "40", "91"} <= codigos  # rendimentos
    assert {"290", "491", "499", "511"} <= codigos  # descontos

    bases = {b["label"]: b["value"] for b in entrada["bases"]}
    assert bases["BASEDECALCULODOINSS"] == "1.260,65"
    assert not any(b[0].isdigit() for b in bases)


def test_payroll_01_totais_vao_para_bases(ficha):
    """`TOT.RENDIMENTOS` e `TOTALDESCONTOS` são totais, não verbas —
    mesmo aparecendo dentro das colunas de verba."""
    entrada = ficha["pages"][0]
    labels_de_verba = {c["label"] for c in entrada["fields"]}
    bases = {b["label"] for b in entrada["bases"]}

    assert "TOT.RENDIMENTOS" not in labels_de_verba
    assert "TOTALDESCONTOS" not in labels_de_verba
    assert {"TOT.RENDIMENTOS", "TOTALDESCONTOS"} <= bases


def test_payroll_01_separa_codigo_colado_no_rotulo(ficha):
    """O documento imprime `40Reembolso VR` e `91Hr Adic Pericul`."""
    campos = {c["code"]: c for c in ficha["pages"][0]["fields"]}

    assert campos["40"]["label"] == "Reembolso VR"
    assert campos["91"]["label"] == "Hr Adic Pericul"
    assert campos["91"]["reference"] == "146,67"


def test_payroll_01_expande_ano_de_dois_digitos(ficha):
    """`abr-17` → `04/2017`."""
    assert (ficha["pages"][0]["month"], ficha["pages"][0]["year"]) == ("04", "2017")
