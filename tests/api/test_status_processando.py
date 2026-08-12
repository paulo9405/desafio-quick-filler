"""Garantia de que `value` é null enquanto `status` é `processando`.

Por que este caso: é uma das poucas regras do contrato que o cliente observa
com o polling, e é fácil de quebrar sem perceber ao mexer na serialização.

Por que não é testado via HTTP ponta a ponta: o `TestClient` executa as
background tasks antes de devolver a resposta do POST, então o estado
`processando` já passou quando o GET acontece. Testar a garantia diretamente é
mais honesto que fabricar uma corrida de threads no teste.
"""

from __future__ import annotations

from app.api.transcriptions import _to_response
from app.repositories.transcription_repository import (
    Transcricao,
    TranscriptionRepository,
)


def test_transcricao_recem_criada_fica_processando_sem_value(tmp_path):
    repository = TranscriptionRepository(tmp_path / "t.db")
    repository.init_db()

    repository.create(
        transcricao_id="abc123",
        tipo="cartao-ponto",
        status="processando",
        pdf_path=str(tmp_path / "abc123.pdf"),
    )

    guardada = repository.get("abc123")
    assert guardada.status == "processando"
    assert guardada.value is None
    assert guardada.erro is None


def test_value_e_omitido_enquanto_processa(tmp_path):
    """Mesmo que houvesse valor gravado, o envelope não pode expô-lo."""
    from datetime import datetime, timezone

    agora = datetime.now(timezone.utc)
    transcricao = Transcricao(
        id="abc123",
        tipo="cartao-ponto",
        status="processando",
        erro=None,
        value={"pages": [{"page": 1, "days": []}]},
        pdf_path=None,
        created_at=agora,
        updated_at=agora,
    )

    resposta = _to_response(transcricao)

    assert resposta.status.value == "processando"
    assert resposta.value is None


def test_put_e_recusado_enquanto_processa(client, pdf_valido, tmp_path):
    """Aceitar correção durante o processamento seria enganoso.

    O pipeline sobrescreveria o que a pessoa acabou de digitar.
    """
    from app.api.deps import get_repository

    repository = get_repository()
    repository.create(
        transcricao_id="emprocesso",
        tipo="holerite",
        status="processando",
        pdf_path=None,
    )

    resposta = client.put(
        "/api/transcricoes/emprocesso", json={"value": {"pages": []}}
    )

    assert resposta.status_code == 409


def test_planilha_e_recusada_enquanto_nao_concluida(client):
    from app.api.deps import get_repository

    repository = get_repository()
    repository.create(
        transcricao_id="emprocesso2",
        tipo="cartao-ponto",
        status="processando",
        pdf_path=None,
    )

    resposta = client.get("/api/transcricoes/emprocesso2/planilha")

    assert resposta.status_code == 409
