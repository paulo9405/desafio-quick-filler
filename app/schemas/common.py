"""Schemas do contrato HTTP oficial.

ATENÇÃO: nomes de campos, valores de enum e shape são LITERAIS do README da
Quick Filler. Há avaliação automatizada comparando esta saída. Não renomear,
não acrescentar campos ao envelope, não mudar tipos.

Referência: docs/roadmap.md seções 3 e 8.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    """Valores aceitos no campo `tipo` do upload."""

    CARTAO_PONTO = "cartao-ponto"
    HOLERITE = "holerite"


class StatusTranscricao(str, Enum):
    """Valores possíveis de `status`."""

    PROCESSANDO = "processando"
    CONCLUIDO = "concluido"
    ERRO = "erro"


class TranscricaoCriada(BaseModel):
    """Corpo da resposta do POST — HTTP 202."""

    id: str


class TranscricaoResponse(BaseModel):
    """Corpo da resposta do GET.

    `erro` e `value` são sempre serializados, mesmo quando `None`: o contrato
    mostra `"erro": null` explicitamente.
    """

    id: str
    tipo: TipoDocumento
    status: StatusTranscricao
    erro: Optional[str] = None
    value: Optional[Dict[str, Any]] = None


class TranscricaoUpdate(BaseModel):
    """Corpo do PUT: `{ "value": { ... } }`.

    `value` é aceito como objeto livre de propósito. Ele carrega as correções
    feitas por uma pessoa na interface de revisão, e validar rigidamente contra
    o schema do parser arriscaria rejeitar uma correção legítima — inclusive a
    correção de um campo que a máquina leu com formato inesperado.

    A honestidade dos dados vale mais que a rigidez do schema neste ponto.
    """

    value: Dict[str, Any] = Field(...)
