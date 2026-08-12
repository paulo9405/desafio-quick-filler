"""Rotas do contrato HTTP oficial.

CONTRATO LITERAL — não renomear rota, campo, status ou valor de enum.
Há avaliação automatizada. Ver docs/roadmap.md seções 3 e 8.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.deps import get_transcription_service
from app.schemas.common import (
    StatusTranscricao,
    TipoDocumento,
    TranscricaoCriada,
    TranscricaoResponse,
    TranscricaoUpdate,
)
from app.services.document_service import UploadInvalido, UploadMuitoGrande
from app.services.export_service import FormatoInvalido, gerar_planilha
from app.services.transcription_service import TranscriptionService

router = APIRouter(prefix="/api", tags=["transcricoes"])


def _to_response(transcricao) -> TranscricaoResponse:
    """Converte o registro persistido no envelope oficial.

    `value` é forçado a `None` enquanto o status for `processando`. O contrato
    garante isso, e garantir aqui evita depender de o repositório nunca ter
    gravado nada antes da hora.
    """
    value = transcricao.value
    if transcricao.status == StatusTranscricao.PROCESSANDO.value:
        value = None
    return TranscricaoResponse(
        id=transcricao.id,
        tipo=transcricao.tipo,
        status=transcricao.status,
        erro=transcricao.erro,
        value=value,
    )


@router.post(
    "/transcricoes",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TranscricaoCriada,
)
def criar_transcricao(
    background: BackgroundTasks,
    arquivo: UploadFile = File(...),
    tipo: TipoDocumento = Form(...),
    service: TranscriptionService = Depends(get_transcription_service),
) -> TranscricaoCriada:
    """Recebe o PDF, agenda o processamento e devolve 202 imediatamente.

    O processamento NÃO acontece aqui: em produção o proxy da plataforma
    cortaria a conexão antes de a extração terminar.

    Rota síncrona de propósito — o FastAPI a executa em threadpool, então a
    leitura do arquivo (I/O bloqueante) não trava o event loop.
    """
    try:
        transcricao_id = service.criar(tipo=tipo.value, source=arquivo.file)
    except UploadMuitoGrande as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except UploadInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    background.add_task(service.processar, transcricao_id)
    # Retenção aplicada de forma oportunista, sem agendador dedicado.
    background.add_task(service.limpar_expiradas)

    return TranscricaoCriada(id=transcricao_id)


@router.get("/transcricoes/{transcricao_id}", response_model=TranscricaoResponse)
def obter_transcricao(
    transcricao_id: str,
    service: TranscriptionService = Depends(get_transcription_service),
) -> TranscricaoResponse:
    transcricao = service.obter(transcricao_id)
    if transcricao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcrição não encontrada.",
        )
    return _to_response(transcricao)


@router.put("/transcricoes/{transcricao_id}", response_model=TranscricaoResponse)
def atualizar_transcricao(
    transcricao_id: str,
    payload: TranscricaoUpdate,
    service: TranscriptionService = Depends(get_transcription_service),
) -> TranscricaoResponse:
    """Substitui a transcrição pelas correções feitas na interface."""
    atual = service.obter(transcricao_id)
    if atual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcrição não encontrada.",
        )

    # Aceitar correção durante o processamento seria enganoso: o pipeline
    # sobrescreveria o que a pessoa acabou de digitar.
    if atual.status == StatusTranscricao.PROCESSANDO.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A transcrição ainda está sendo processada.",
        )

    atualizada = service.substituir_value(transcricao_id, payload.value)
    if atualizada is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcrição não encontrada.",
        )
    return _to_response(atualizada)


@router.get("/transcricoes/{transcricao_id}/planilha")
def baixar_planilha(
    transcricao_id: str,
    formato: str = Query("xlsx", description="xlsx | csv | json"),
    service: TranscriptionService = Depends(get_transcription_service),
) -> Response:
    """Devolve a planilha já com as correções aplicadas.

    A planilha sai do `value` persistido — o mesmo que o PUT substitui.
    """
    transcricao = service.obter(transcricao_id)
    if transcricao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcrição não encontrada.",
        )

    if transcricao.status != StatusTranscricao.CONCLUIDO.value or transcricao.value is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A transcrição ainda não está concluída. "
                f"Status atual: {transcricao.status}."
            ),
        )

    try:
        planilha = gerar_planilha(
            transcricao_id=transcricao.id,
            tipo=transcricao.tipo,
            value=transcricao.value,
            formato=formato,
        )
    except FormatoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return Response(
        content=planilha.conteudo,
        media_type=planilha.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{planilha.filename}"'
        },
    )
