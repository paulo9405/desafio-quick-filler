"""Parser do cartão de ponto `time-card-03` — primeiro parser sobre OCR.

Roda contra a extração REAL do Tesseract, gravada em `tests/fixtures/`. Ver
`tests/fixtures/__init__.py` para o motivo de usar fixture em vez de rodar OCR
a cada execução.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.extraction.extracted_page import ExtractionSource
from app.extraction.native_text import extract_native_pages
from app.parsers.timesheet.cartao_ponto_tabular import CartaoPontoTabularParser
from tests.fixtures import carregar

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


@pytest.fixture(scope="module")
def paginas():
    return carregar("time-card-03")


@pytest.fixture(scope="module")
def value(paginas):
    return CartaoPontoTabularParser().parse(paginas)


def test_a_fixture_e_mesmo_saida_de_ocr(paginas):
    """Se isto falhar, a fixture foi gerada pelo caminho errado."""
    assert all(pagina.source is ExtractionSource.OCR for pagina in paginas)
    assert all(
        palavra.confidence is not None
        for pagina in paginas
        for palavra in pagina.words
    )


# ------------------------------------------------- ausência de perda silenciosa


def test_as_datas_formam_uma_sequencia_continua_sem_buraco(value):
    """A prova mais forte de que nenhuma linha se perdeu.

    O documento cobre 16/12/2019 a 20/09/2020, um dia por linha. Conferimos
    contra o calendário: cada data precisa ser exatamente a anterior mais um
    dia, sem repetição e sem salto — inclusive na virada de página.
    """
    datas = [
        dia["date_raw"] for pagina in value["pages"] for dia in pagina["days"]
    ]

    assert len(datas) == 280
    assert len(set(datas)) == 280

    def para_data(texto: str) -> date:
        dia, mes, ano = texto.split("/")
        return date(int(ano), int(mes), int(dia))

    primeira, ultima = para_data(datas[0]), para_data(datas[-1])
    assert primeira == date(2019, 12, 16)
    assert ultima == date(2020, 9, 20)
    assert (ultima - primeira).days + 1 == len(datas)

    for anterior, seguinte in zip(datas, datas[1:]):
        assert para_data(seguinte) - para_data(anterior) == timedelta(days=1)


def test_dias_sem_batida_permanecem(value):
    """Fins de semana e feriados continuam como linha, com `punches: []`."""
    dias = {
        dia["date_raw"]: dia["punches"]
        for pagina in value["pages"]
        for dia in pagina["days"]
    }

    assert dias["21/12/2019"] == []  # sábado
    assert dias["22/12/2019"] == []  # domingo
    assert dias["25/12/2019"] == []  # Natal — a linha traz o texto "NATAL"


# ------------------------------------------------------------ raw × normalizado


def test_sufixo_de_marcacao_fica_no_raw_e_sai_do_normalizado(value):
    """`07:00d` → `time_raw` preserva, `time_hhmm` normaliza."""
    dia = next(
        dia
        for pagina in value["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "16/12/2019"
    )

    assert [batida["time_raw"] for batida in dia["punches"]] == [
        "07:00d",
        "12:00d",
        "13:00d",
        "17:00d",
    ]
    assert [batida["time_hhmm"] for batida in dia["punches"]] == [
        "07:00",
        "12:00",
        "13:00",
        "17:00",
    ]


def test_virada_de_dia_e_preservada_no_raw(value):
    """`+03:00d` indica batida no dia seguinte.

    O `+` não cabe em `HH:MM`, e é exatamente por isso que o contrato guarda
    os dois valores: a informação não se perde.
    """
    dia = next(
        dia
        for pagina in value["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "28/12/2019"
    )

    brutos = [batida["time_raw"] for batida in dia["punches"]]
    normalizados = [batida["time_hhmm"] for batida in dia["punches"]]

    assert brutos == ["22:59d", "+03:00d", "+04:00d", "+06:59d"]
    assert normalizados == ["22:59", "03:00", "04:00", "06:59"]


def test_todo_time_hhmm_esta_em_hh_mm(value):
    for pagina in value["pages"]:
        for dia in pagina["days"]:
            for batida in dia["punches"]:
                assert re.match(r"^\d{2}:\d{2}$", batida["time_hhmm"])


# ------------------------------------------------------------------ armadilhas


def test_colunas_de_hora_extra_nao_viram_batida(value):
    """`H.Ext`, `Atraso`, `Falta`, `Ad.Not` e `Abono` também são `HH:MM`.

    Elas são declaradas no cabeçalho justamente para limitar a faixa de `Sai4`.
    Sem isso, a faixa da última coluna iria até a borda da página e engoliria
    a hora extra.

    Contra-prova: `01/01/2020` tem `07:00` na coluna `H.Ext` e apenas duas
    batidas reais.
    """
    dia = next(
        dia
        for pagina in value["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "01/01/2020"
    )

    assert len(dia["punches"]) == 2
    assert [batida["time_raw"] for batida in dia["punches"]] == ["07:00d", "15:00d"]


def test_batida_de_baixa_confianca_do_ocr_esta_presente(value):
    """REGRESSÃO do bug do bloco 3/4.

    `07:00d` de 19/12/2019 é lido com confiança 10. O filtro de confiança que
    existia antes o apagava, e o dia ficava com 3 batidas em vez de 4.
    """
    dia = next(
        dia
        for pagina in value["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "19/12/2019"
    )

    assert len(dia["punches"]) == 4
    assert dia["punches"][0]["time_raw"] == "07:00d"


def test_kind_vem_da_coluna(value):
    dia = next(
        dia
        for pagina in value["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "16/12/2019"
    )

    assert [batida["kind"] for batida in dia["punches"]] == ["IN", "OUT", "IN", "OUT"]


# ------------------------------------------------------------------- detecção


def test_matches_reconhece_apesar_do_erro_de_ocr_no_cabecalho(paginas):
    """O OCR lê `Ent1` como `Entl` e `Sai2` como `Sai?`, nas 5 páginas.

    Exigir cabeçalho exato tornaria este layout indetectável.
    """
    cabecalho = next(
        linha.text for linha in paginas[0].lines() if "Data" in linha.text and "Ent" in linha.text
    )
    assert "Entl" in cabecalho  # o erro de OCR está mesmo lá
    assert "Ent1" not in cabecalho

    assert CartaoPontoTabularParser().matches(paginas) == 1.0


def test_matches_recusa_outro_cartao_de_ponto():
    """`time-card-01` é cartão de ponto, mas de outro layout."""
    outras = extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    assert CartaoPontoTabularParser().matches(outras) == 0.0
