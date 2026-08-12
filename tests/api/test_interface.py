"""Endpoints auxiliares da interface e a projeção de revisão.

Por que estes casos: a interface precisa das colunas da planilha, dos avisos e
do caminho de cada célula. Se a projeção divergir da planilha, a pessoa corrige
uma coisa na tela e baixa outra no arquivo — que é o pior desfecho possível
para uma ferramenta de revisão.

Nada aqui testa Bootstrap ou aparência.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.services.export_service import montar_tabela
from app.services.review_service import montar_revisao
from tests.conftest import upload

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"

VALUE_CARTAO = {
    "pages": [
        {
            "page": 1,
            "days": [
                {
                    "date_raw": "01/05/2019",
                    "punches": [
                        {"kind": "IN", "time_raw": "08:00", "time_hhmm": "08:00"},
                        {"kind": "OUT", "time_raw": "12:00", "time_hhmm": "12:00"},
                    ],
                },
                {
                    "date_raw": "02/05/2019",
                    "punches": [
                        {"kind": "IN", "time_raw": "23:00?", "time_hhmm": "23:00"}
                    ],
                },
            ],
        }
    ]
}


def _pipeline(value):
    return lambda pdf_path, tipo: json.loads(json.dumps(value))


# ------------------------------------------------------- projeção de revisão


def test_revisao_usa_as_mesmas_colunas_da_planilha():
    """Exigência do README: a tabela segue as colunas da planilha."""
    revisao = montar_revisao("cartao-ponto", VALUE_CARTAO)
    tabela = montar_tabela("cartao-ponto", VALUE_CARTAO)

    assert revisao["colunas"] == tabela.header
    assert len(revisao["linhas"]) == len(tabela.rows)
    for linha, esperado in zip(revisao["linhas"], tabela.rows):
        assert [c["valor"] for c in linha["celulas"]] == esperado


def test_revisao_traz_severidade_e_motivo_legivel():
    """A interface não recalcula aviso — recebe pronto, com o motivo."""
    revisao = montar_revisao("cartao-ponto", VALUE_CARTAO)

    primeira, segunda = revisao["linhas"]
    assert primeira["severidade"] is None
    assert primeira["motivos"] == []

    # batida ímpar + `?` no raw
    assert segunda["severidade"] == "amarelo"
    assert len(segunda["motivos"]) == 2
    assert all(isinstance(m, str) and m for m in segunda["motivos"])


def test_incerteza_apenas_no_raw_chega_marcada_na_interface():
    """A célula mostra `23:00`, sem `?`, e a linha vem marcada mesmo assim."""
    revisao = montar_revisao("cartao-ponto", VALUE_CARTAO)
    segunda = revisao["linhas"][1]

    assert segunda["celulas"][1]["valor"] == "23:00"
    assert "?" not in segunda["celulas"][1]["valor"]
    assert segunda["severidade"] == "amarelo"


def test_caminho_da_celula_aponta_para_o_campo_certo():
    revisao = montar_revisao("cartao-ponto", VALUE_CARTAO)
    celulas = revisao["linhas"][0]["celulas"]

    assert celulas[0]["caminho"] == "pages.0.days.0.date_raw"
    assert celulas[1]["caminho"] == "pages.0.days.0.punches.0.time_hhmm"
    assert celulas[2]["caminho"] == "pages.0.days.0.punches.1.time_hhmm"


def test_celula_sem_campo_correspondente_nao_tem_caminho():
    """Dia com menos batidas que o dia mais cheio: a célula vazia não é editável."""
    revisao = montar_revisao("cartao-ponto", VALUE_CARTAO)
    segunda = revisao["linhas"][1]

    assert segunda["celulas"][2]["valor"] == ""
    assert segunda["celulas"][2]["caminho"] == ""


def test_caminho_do_holerite_aponta_para_a_verba_certa():
    value = {
        "pages": [
            {
                "page": 1,
                "year": "2020",
                "month": "01",
                "fields": [
                    {"code": "1", "label": "Salário", "reference": "", "value": "10,00"},
                    {"code": "2", "label": "INSS", "reference": "", "value": "2,00"},
                ],
                "bases": [],
            }
        ]
    }
    revisao = montar_revisao("holerite", value)
    celulas = revisao["linhas"][0]["celulas"]

    assert revisao["colunas"] == ["Pág.", "Mês", "Ano", "Salário", "INSS"]
    assert celulas[0]["caminho"] == ""  # `Pág.` vem do índice do PDF
    assert celulas[1]["caminho"] == "pages.0.month"
    assert celulas[3]["caminho"] == "pages.0.fields.0.value"
    assert celulas[4]["caminho"] == "pages.0.fields.1.value"


# ------------------------------------------------------------- endpoints


def test_endpoint_de_revisao_responde(client_factory, pdf_valido):
    client = client_factory(_pipeline(VALUE_CARTAO))
    criado = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    resposta = client.get(f"/api/transcricoes/{transcricao_id}/revisao")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tipo"] == "cartao-ponto"
    assert corpo["colunas"][0] == "Data"
    assert len(corpo["linhas"]) == 2


def test_endpoint_de_revisao_404_e_409(client_factory, client, pdf_valido):
    assert client.get("/api/transcricoes/naoexiste/revisao").status_code == 404

    from app.api.deps import get_repository

    get_repository().create(
        transcricao_id="emprocesso", tipo="holerite", status="processando", pdf_path=None
    )
    assert client.get("/api/transcricoes/emprocesso/revisao").status_code == 409


def test_endpoint_de_arquivo_devolve_o_pdf_original(client_factory, pdf_valido):
    """A interface precisa exibir o PDF ao lado da tabela."""
    client = client_factory(_pipeline(VALUE_CARTAO))
    criado = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    resposta = client.get(f"/api/transcricoes/{transcricao_id}/arquivo")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF-")
    # servido inline, para poder ser embutido
    assert "inline" in resposta.headers["content-disposition"]
    # o nome do upload original nunca é exposto
    assert "documento.pdf" not in resposta.headers["content-disposition"]


def test_endpoint_de_arquivo_404_para_id_inexistente(client):
    assert client.get("/api/transcricoes/naoexiste/arquivo").status_code == 404


# --------------------------------------------- ciclo de correção pela interface


def test_correcao_pela_tabela_chega_na_planilha(client_factory, pdf_valido):
    """Simula o que a interface faz: usa o caminho da célula para gravar.

    É o fluxo completo do produto — corrigir na tela e baixar o arquivo já
    corrigido — exercitado exatamente como o JavaScript o executa.
    """
    client = client_factory(_pipeline(VALUE_CARTAO))
    criado = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    value = client.get(f"/api/transcricoes/{transcricao_id}").json()["value"]
    revisao = client.get(f"/api/transcricoes/{transcricao_id}/revisao").json()

    # a interface pega o caminho da célula e aplica o valor digitado
    caminho = revisao["linhas"][0]["celulas"][1]["caminho"]
    assert caminho == "pages.0.days.0.punches.0.time_hhmm"
    value["pages"][0]["days"][0]["punches"][0]["time_hhmm"] = "07:15"

    assert (
        client.put(f"/api/transcricoes/{transcricao_id}", json={"value": value}).status_code
        == 200
    )

    import csv

    resposta = client.get(
        f"/api/transcricoes/{transcricao_id}/planilha", params={"formato": "csv"}
    )
    linhas = list(
        csv.reader(io.StringIO(resposta.content.decode("utf-8-sig")), delimiter=";")
    )
    assert linhas[1][1] == "07:15"


def test_pagina_da_interface_e_servida(client):
    resposta = client.get("/")

    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "Quick Filler" in resposta.text


def test_recursos_estaticos_sao_servidos(client):
    for caminho in ("/static/app.js", "/static/style.css", "/static/bootstrap.min.css"):
        assert client.get(caminho).status_code == 200
