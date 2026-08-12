"""Orquestração do ciclo de vida de uma transcrição.

Fluxo do POST, conforme exigido pelo desafio:

    validar → criar registro → disparar processamento → retornar 202

O INSTRUCOES é explícito sobre por que NÃO processar dentro do request:
"funciona local e quebra em produção, quando o proxy da plataforma corta a
conexão antes de a extração terminar".

Aqui o processamento roda via `BackgroundTasks` do FastAPI, e o `status` no
banco é a fonte de verdade que o frontend consulta por polling.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from app.core.logging import get_logger
from app.repositories.transcription_repository import (
    Transcricao,
    TranscriptionRepository,
)
from app.services.document_service import DocumentService

logger = get_logger(__name__)

# Assinatura do pipeline de processamento. Recebe o caminho do PDF e o tipo,
# devolve o `value` no formato oficial. Injetado para que a API não conheça a
# extração, e para que o teste possa substituí-lo.
Pipeline = Callable[[str, str], Dict[str, Any]]


class LayoutNaoReconhecido(Exception):
    """Nenhum parser registrado reconheceu o documento.

    Não é um bug: é a resposta correta quando a aplicação recebe um layout que
    não conhece. O README oficial diz que responder "não sei ler este
    documento" é melhor que devolver lixo.
    """


class TranscriptionService:
    def __init__(
        self,
        repository: TranscriptionRepository,
        documents: DocumentService,
        pipeline: Pipeline,
        retention_hours: int,
        max_simultaneos: int = 2,
    ) -> None:
        self._repository = repository
        self._documents = documents
        self._pipeline = pipeline
        self._retention_hours = retention_hours

        # Limita quantos documentos são processados ao mesmo tempo.
        #
        # MEDIDO, não suposto. Com 6 uploads simultâneos de um documento que
        # leva 19 s sozinho, o total foi 189 s — pior que os ~114 s que os
        # mesmos 6 levariam em fila. Os jobs de OCR disputam CPU entre si e a
        # vazão cai ABAIXO do sequencial.
        #
        # O README exige "comportamento definido para (...) uploads
        # simultâneos". Sem limite o comportamento não é definido: degrada de
        # forma imprevisível, e num ambiente de 1 CPU vira timeout ou falta de
        # memória.
        #
        # A fila é o próprio semáforo: o excedente espera com `status`
        # `processando`, que é exatamente o que o contrato descreve. O `202` do
        # POST continua imediato, porque o semáforo é adquirido dentro da
        # tarefa de fundo e não na requisição.
        self._vagas = threading.BoundedSemaphore(max(1, max_simultaneos))

    # ------------------------------------------------------------------ criação

    def criar(self, tipo: str, source, transcricao_id: Optional[str] = None) -> str:
        """Valida o upload, cria o registro e devolve o id.

        Levanta as exceções de validação de `document_service`, que a camada
        HTTP traduz para 4xx.
        """
        transcricao_id = transcricao_id or self._documents.new_id()
        caminho = self._documents.store_upload(source, transcricao_id)

        self._repository.create(
            transcricao_id=transcricao_id,
            tipo=tipo,
            status="processando",
            pdf_path=str(caminho),
        )
        logger.info("transcricao criada id=%s tipo=%s", transcricao_id, tipo)
        return transcricao_id

    # ------------------------------------------------------------- processamento

    def processar(self, transcricao_id: str) -> None:
        """Executa o pipeline e grava o resultado.

        Roda em background. Nunca levanta: qualquer falha vira
        `status = "erro"` com mensagem legível, porque o cliente descobre o
        desfecho pelo GET, não pela exceção.
        """
        transcricao = self._repository.get(transcricao_id)
        if transcricao is None:
            logger.warning("transcricao inexistente id=%s", transcricao_id)
            return

        inicio = time.monotonic()
        try:
            with self._vagas:
                value = self._pipeline(transcricao.pdf_path, transcricao.tipo)
        except LayoutNaoReconhecido as exc:
            self._repository.set_erro(transcricao_id, str(exc))
            logger.info("layout nao reconhecido id=%s", transcricao_id)
            return
        except Exception:
            # `exc_info=False` de propósito: o traceback pode conter trechos do
            # documento, e o desafio proíbe PII em log.
            logger.error(
                "falha ao processar id=%s tipo=%s",
                transcricao_id,
                transcricao.tipo,
                exc_info=False,
            )
            self._repository.set_erro(
                transcricao_id,
                "Não foi possível processar este documento.",
            )
            return

        self._repository.set_concluido(transcricao_id, value)
        logger.info(
            "transcricao concluida id=%s duracao_s=%.1f",
            transcricao_id,
            time.monotonic() - inicio,
        )

    # ------------------------------------------------------------------ leitura

    def obter(self, transcricao_id: str) -> Optional[Transcricao]:
        return self._repository.get(transcricao_id)

    def substituir_value(
        self, transcricao_id: str, value: Dict[str, Any]
    ) -> Optional[Transcricao]:
        """Aplica as correções feitas na interface (PUT)."""
        if not self._repository.replace_value(transcricao_id, value):
            return None
        logger.info("transcricao corrigida id=%s", transcricao_id)
        return self._repository.get(transcricao_id)

    # ---------------------------------------------------------------- retenção

    def limpar_expiradas(self) -> int:
        """Remove transcrições e PDFs além da janela de retenção.

        Disparada em dois momentos, ambos sem agendador:

        - na inicialização da aplicação;
        - a cada upload, em background.

        A primeira cobre a instância ociosa, que era a lacuna real: um free
        tier que dorme e acorda executa a limpeza ao acordar. A segunda cobre a
        instância em uso.

        O desafio pede política de retenção definida e aplicada, não
        infraestrutura de cron — e cron/Celery/Redis seriam três serviços a
        mais para uma consulta que custa milissegundos.

        Limitação residual: uma instância que fica de pé por semanas sem
        nenhum upload só limpa no próximo reinício. Registrado em SOLUCAO.md.
        """
        expiradas = self._repository.find_expired(self._retention_hours)
        for transcricao in expiradas:
            self._documents.remove(transcricao.pdf_path)
            self._repository.delete(transcricao.id)
        if expiradas:
            logger.info("retencao removeu %d transcricoes", len(expiradas))
        return len(expiradas)
