"""Testes de validação de upload.

Por que estes casos: o endpoint é público e recebe documento com PII. O
INSTRUCOES nomeia "aceitar qualquer coisa no upload" entre os erros que
derrubam entregas, e cita exatamente o caso do `.txt` renomeado para `.pdf`.
"""

from __future__ import annotations

from tests.conftest import upload


def test_txt_renomeado_para_pdf_e_recusado(client):
    """O caso citado literalmente pelo INSTRUCOES.

    Extensão e content-type vêm do cliente; só a assinatura do arquivo vale.
    """
    conteudo = b"isto nao e um pdf, e apenas um texto qualquer\n" * 10

    resposta = client.post(
        "/api/transcricoes", **upload(conteudo, "holerite", filename="holerite.pdf")
    )

    assert resposta.status_code == 400
    assert "PDF" in resposta.json()["detail"]


def test_pdf_corrompido_e_recusado(client, pdf_valido):
    """Assinatura correta, conteúdo quebrado — precisa falhar na abertura."""
    corrompido = pdf_valido[:200] + b"\x00" * 500

    resposta = client.post("/api/transcricoes", **upload(corrompido, "cartao-ponto"))

    assert resposta.status_code == 400


def test_arquivo_vazio_e_recusado(client):
    resposta = client.post("/api/transcricoes", **upload(b"", "cartao-ponto"))
    assert resposta.status_code == 400


def test_arquivo_acima_do_limite_e_recusado(client, monkeypatch, tmp_path):
    """Limite de tamanho, exigido pela seção de segurança do desafio."""
    monkeypatch.setenv("QF_MAX_UPLOAD_BYTES", "1024")

    from app.api import deps
    from app.core import config

    config.reset_settings_cache()
    deps.reset_dependency_cache()
    monkeypatch.setenv("QF_DATABASE_PATH", str(tmp_path / "limite.db"))
    monkeypatch.setenv("QF_STORAGE_DIR", str(tmp_path / "limite-pdfs"))

    grande = b"%PDF-" + b"x" * 5000
    resposta = client.post("/api/transcricoes", **upload(grande, "cartao-ponto"))

    assert resposta.status_code in {400, 413}


def test_pdf_recusado_nao_deixa_arquivo_no_disco(client, tmp_path):
    """Arquivo recusado não pode ficar ocupando disco com PII."""
    client.post("/api/transcricoes", **upload(b"nao e pdf", "holerite"))

    pdfs = list((tmp_path / "pdfs").glob("*.pdf")) if (tmp_path / "pdfs").exists() else []
    assert pdfs == []
