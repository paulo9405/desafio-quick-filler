"""Testes do contrato HTTP oficial.

Por que estes casos: o README avisa que divergir do contrato significa "nota
zero em precisão, mesmo com a extração perfeita", e há avaliação automatizada.
São os testes que protegem o que mais pesa e que quebrariam em silêncio.
"""

from __future__ import annotations

import io

from tests.conftest import upload


def test_post_devolve_202_e_id(client, pdf_valido):
    """POST precisa devolver 202 (não 200/201) com um id no corpo."""
    resposta = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))

    assert resposta.status_code == 202
    corpo = resposta.json()
    assert set(corpo) == {"id"}
    assert isinstance(corpo["id"], str) and corpo["id"]


def test_get_devolve_envelope_oficial_completo(client, pdf_valido):
    """As cinco chaves precisam existir sempre, inclusive quando são null."""
    criado = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    resposta = client.get(f"/api/transcricoes/{transcricao_id}")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"id", "tipo", "status", "erro", "value"}
    assert corpo["id"] == transcricao_id
    assert corpo["tipo"] == "cartao-ponto"
    assert corpo["status"] in {"processando", "concluido", "erro"}


def test_status_erro_traz_mensagem_legivel(client, pdf_valido):
    """Enquanto nenhum parser existe, o documento termina em erro explicado.

    Protege duas coisas: `erro` não pode ser null quando o status é `erro`, e a
    mensagem precisa ser legível — não um traceback nem um código interno.
    """
    criado = client.post("/api/transcricoes", **upload(pdf_valido, "cartao-ponto"))
    transcricao_id = criado.json()["id"]

    corpo = client.get(f"/api/transcricoes/{transcricao_id}").json()

    assert corpo["status"] == "erro"
    assert corpo["value"] is None
    assert isinstance(corpo["erro"], str) and corpo["erro"].strip()
    assert "Traceback" not in corpo["erro"]


def test_get_inexistente_devolve_404(client):
    assert client.get("/api/transcricoes/nao-existe").status_code == 404


def test_tipo_invalido_e_recusado(client, pdf_valido):
    """`tipo` só aceita os dois valores oficiais."""
    resposta = client.post("/api/transcricoes", **upload(pdf_valido, "ficha-financeira"))
    assert 400 <= resposta.status_code < 500


def test_healthz(client):
    resposta = client.get("/healthz")
    assert resposta.status_code == 200
