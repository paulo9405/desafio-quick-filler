"""Fecha o ciclo da Fase 1: um PDF real atravessa toda a aplicação.

Por que este caso: é o critério de conclusão da fase — "pelo menos um PDF real
produz dados corretos". Testa o caminho de produção inteiro, sem nenhuma peça
substituída: HTTP → validação → persistência → extração → registry → parser →
GET → planilha.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from tests.conftest import upload

EXEMPLOS = Path(__file__).resolve().parents[2] / "exemplos"


def test_pdf_real_atravessa_o_pipeline_completo(client):
    conteudo = (EXEMPLOS / "time-card-01.pdf").read_bytes()

    criado = client.post("/api/transcricoes", **upload(conteudo, "cartao-ponto"))
    assert criado.status_code == 202
    transcricao_id = criado.json()["id"]

    corpo = client.get(f"/api/transcricoes/{transcricao_id}").json()

    assert corpo["status"] == "concluido"
    assert corpo["erro"] is None

    paginas = corpo["value"]["pages"]
    assert len(paginas) == 5
    assert [p["page"] for p in paginas] == [1, 2, 3, 4, 5]
    assert len(paginas[0]["days"]) == 31
    assert paginas[0]["days"][0]["date_raw"] == "01/07/2012"


def test_planilha_do_pdf_real_sai_com_as_colunas_certas(client):
    conteudo = (EXEMPLOS / "time-card-01.pdf").read_bytes()
    criado = client.post("/api/transcricoes", **upload(conteudo, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    resposta = client.get(
        f"/api/transcricoes/{transcricao_id}/planilha", params={"formato": "csv"}
    )
    assert resposta.status_code == 200

    linhas = list(
        csv.reader(io.StringIO(resposta.content.decode("utf-8-sig")), delimiter=";")
    )

    # o dia com mais batidas do documento define a quantidade de pares
    assert linhas[0][0] == "Data"
    assert linhas[0][1:5] == ["Entrada 1", "Saída 1", "Entrada 2", "Saída 2"]

    # uma linha por dia, somando os 5 meses: 31+31+30+31+30
    assert len(linhas) - 1 == 153

    # primeiro dia é domingo sem batida — linha presente, células vazias
    assert linhas[1][0] == "01/07/2012"
    assert linhas[1][1] == ""


def test_documento_de_layout_ainda_nao_suportado_falha_de_forma_honesta(client):
    """`payroll-01` é uma ficha financeira — parser é da Fase 2.

    Enquanto não existir, a resposta correta é dizer que não sabe ler, e não
    devolver uma transcrição vazia como se estivesse tudo bem.
    """
    conteudo = (EXEMPLOS / "payroll-01.pdf").read_bytes()

    criado = client.post("/api/transcricoes", **upload(conteudo, "holerite"))
    transcricao_id = criado.json()["id"]

    corpo = client.get(f"/api/transcricoes/{transcricao_id}").json()

    assert corpo["status"] == "erro"
    assert corpo["value"] is None
    assert "reconhecer o layout" in corpo["erro"]
