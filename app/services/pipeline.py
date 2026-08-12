"""Pipeline de processamento: PDF → ExtractedPage → parser → JSON oficial.

ESTADO ATUAL (bloco 2 da Fase 1): ainda não há extração nem parser
registrado, então todo documento termina como "layout não reconhecido".

Isso é intencional e não é um placeholder vazio: recusar honestamente um
documento que a aplicação não sabe ler é o comportamento CORRETO e final para
esse caso. O README oficial diz que responder "não sei ler este documento" é
melhor que devolver lixo.

Os blocos seguintes preenchem este caminho:

- bloco 3: extração (texto nativo e OCR) produzindo `ExtractedPage`;
- bloco 4: registry de parsers, que decide qual layout sabe ler o documento.

Quando um parser reconhecer o documento, este mesmo caminho passa a devolver
`value` e a transcrição termina como `concluido`. Nenhuma outra camada muda.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.transcription_service import LayoutNaoReconhecido

MENSAGEM_LAYOUT_DESCONHECIDO = (
    "Não foi possível reconhecer o layout deste documento."
)


def processar_documento(pdf_path: str, tipo: str) -> Dict[str, Any]:
    """Transforma um PDF no `value` do formato oficial.

    Levanta `LayoutNaoReconhecido` quando nenhum parser sabe ler o documento.
    """
    raise LayoutNaoReconhecido(MENSAGEM_LAYOUT_DESCONHECIDO)
