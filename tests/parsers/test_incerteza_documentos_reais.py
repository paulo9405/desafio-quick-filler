"""Calibração da incerteza medida contra os documentos oficiais.

Por que estes casos: o risco de uma regra de incerteza é errar para os dois
lados — marcar demais (a saída deixa de transcrever) ou de menos (erro passa
como certo). Estes testes fixam a medição real dos dois lados.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction.native_text import extract_native_pages
from app.parsers.payslip.demonstrativo_mensal import DemonstrativoMensalParser
from app.parsers.timesheet.cartao_ponto_tabular import CartaoPontoTabularParser
from app.parsers.timesheet.sipon import SiponTimesheetParser
from tests.fixtures import carregar

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


@pytest.fixture(scope="module")
def ocr():
    return CartaoPontoTabularParser().parse(carregar("time-card-03"))


def _batidas(value):
    return [
        batida
        for pagina in value["pages"]
        for dia in pagina["days"]
        for batida in dia["punches"]
    ]


def test_batidas_perdidas_em_silencio_foram_recuperadas(ocr):
    """REGRESSÃO: `23:00€` e `15:12€` eram descartados por não casar o padrão.

    O documento perdia 4 batidas sem qualquer sinal — o erro que o INSTRUCOES
    chama de "perder linhas em silêncio". Agora elas aparecem, marcadas.
    """
    batidas = _batidas(ocr)

    assert len(batidas) == 826  # eram 822 antes da correção

    marcadas = [b for b in batidas if "?" in b["time_raw"]]
    assert len(marcadas) == 4
    assert {b["time_raw"] for b in marcadas} == {"23:00?", "15:12?"}


def test_os_digitos_das_batidas_marcadas_continuam_disponiveis(ocr):
    """A incerteza é do caractere, não da batida inteira.

    O marcador de sistema não deu para ler, mas o horário deu — e é o horário
    que vai para a planilha.
    """
    marcadas = [b for b in _batidas(ocr) if "?" in b["time_raw"]]

    assert {b["time_hhmm"] for b in marcadas} == {"23:00", "15:12"}


def test_a_marcacao_nao_contamina_o_resto_do_documento(ocr):
    """Falso positivo é tão grave quanto falso negativo.

    Das 826 batidas lidas por OCR, apenas 4 têm evidência concreta de leitura
    falha. Se este número crescer sem uma mudança deliberada, a calibração
    piorou.
    """
    batidas = _batidas(ocr)
    marcadas = [b for b in batidas if "?" in b["time_raw"] or "?" in b["time_hhmm"]]

    assert len(marcadas) / len(batidas) < 0.01


def test_baixa_confianca_sozinha_nao_marca_nada(ocr):
    """O ponto central da estratégia.

    47 batidas CORRETAS deste documento têm confiança abaixo de 30 — entre elas
    `07:00d` com confiança 10. Nenhuma delas pode ser marcada, porque confiança
    baixa não é evidência de erro.

    Contra-prova direta: a batida de 19/12/2019 tem confiança 10 e sai limpa.
    """
    dia = next(
        dia
        for pagina in ocr["pages"]
        for dia in pagina["days"]
        if dia["date_raw"] == "19/12/2019"
    )

    assert len(dia["punches"]) == 4
    assert all("?" not in batida["time_raw"] for batida in dia["punches"])
    assert dia["punches"][0]["time_raw"] == "07:00d"


def test_texto_nativo_nunca_recebe_marcacao():
    """Sem OCR não há leitura duvidosa — marcar seria ruído puro."""
    cartao = SiponTimesheetParser().parse(
        extract_native_pages(str(EXEMPLOS / "time-card-01.pdf"))
    )
    batidas = _batidas(cartao)

    assert len(batidas) == 369
    assert not any("?" in b["time_raw"] or "?" in b["time_hhmm"] for b in batidas)


def test_valores_de_holerite_em_texto_nativo_nao_sao_marcados():
    holerite = DemonstrativoMensalParser().parse(
        extract_native_pages(str(EXEMPLOS / "payroll-03.pdf"))
    )
    campos = [c for p in holerite["pages"] for c in p["fields"]]

    assert len(campos) == 44
    assert not any("?" in campo["value"] for campo in campos)
    assert campos[0]["value"] == "1.678,61"
