"""Interface comum a todos os parsers de layout.

Um parser sabe duas coisas, e só duas:

- `matches(pages)` — este é o meu layout? Devolve um score de 0 a 1.
- `parse(pages)`   — produz o `value` no formato oficial.

Tudo o mais (upload, persistência, API, avisos, planilha) é compartilhado entre
os tipos de documento e não conhece layout nenhum. Adicionar suporte a um
documento novo é criar um arquivo e registrá-lo — que é exatamente o movimento
esperado na sessão técnica ao vivo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.extraction.extracted_page import ExtractedPage


class LayoutParser(ABC):
    """Contrato de um parser de layout."""

    #: `cartao-ponto` ou `holerite`
    tipo: str = ""

    #: Nome curto e estável, usado em log e em teste.
    nome: str = ""

    @abstractmethod
    def matches(self, pages: List[ExtractedPage]) -> float:
        """Confiança de que este parser sabe ler o documento, de 0 a 1.

        `0` significa "não é meu layout". O registry escolhe o maior score
        acima de zero.

        A impressão digital deve vir de traços ESTRUTURAIS — títulos de coluna,
        texto característico do sistema emissor. Nunca de número de páginas,
        posição absoluta ou de uma data específica: isso resolveria o exemplo e
        quebraria em qualquer outro documento do mesmo layout.
        """

    @abstractmethod
    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        """Produz o `value` no formato oficial do tipo correspondente."""
