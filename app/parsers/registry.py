"""Registry de parsers: descobre qual layout sabe ler o documento.

Substitui a suposição de `layout_a` / `layout_b` do plano original. Cada parser
responde `matches()` com um score, e vence o maior acima de zero.

Quando nenhum reconhece, o documento termina em `status: "erro"` com mensagem
legível. Isso não é uma falha do sistema: o README oficial afirma que responder
"não sei ler este documento" é melhor que devolver lixo.

ADICIONAR UM LAYOUT NOVO

1. criar o arquivo em `app/parsers/timesheet/` ou `app/parsers/payslip/`;
2. acrescentar uma linha em `PARSERS` abaixo.

Nenhuma outra parte da aplicação muda.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from app.core.logging import get_logger
from app.extraction.extracted_page import ExtractedPage
from app.parsers.base import LayoutParser
from app.parsers.payslip.declaracao_remuneracao import DeclaracaoRemuneracaoParser
from app.parsers.payslip.demonstrativo_mensal import DemonstrativoMensalParser
from app.parsers.payslip.ficha_financeira import FichaFinanceiraParser
from app.parsers.payslip.recibo_pagamento import ReciboPagamentoParser
from app.parsers.timesheet.cartao_ponto_tabular import CartaoPontoTabularParser
from app.parsers.timesheet.ponto_eletronico import PontoEletronicoParser
from app.parsers.timesheet.sipon import SiponTimesheetParser

logger = get_logger(__name__)

# Todos os parsers conhecidos. A ordem não importa: a escolha é pelo score.
PARSERS: Sequence[LayoutParser] = (
    SiponTimesheetParser(),
    CartaoPontoTabularParser(),
    PontoEletronicoParser(),
    DemonstrativoMensalParser(),
    ReciboPagamentoParser(),
    DeclaracaoRemuneracaoParser(),
    FichaFinanceiraParser(),
)


class ParserRegistry:
    def __init__(self, parsers: Sequence[LayoutParser] = PARSERS) -> None:
        self._parsers = tuple(parsers)

    def parsers_para(self, tipo: str) -> List[LayoutParser]:
        return [parser for parser in self._parsers if parser.tipo == tipo]

    def select(
        self, tipo: str, pages: List[ExtractedPage]
    ) -> Optional[LayoutParser]:
        """Escolhe o parser de maior score para o tipo pedido.

        Só considera parsers do `tipo` informado no upload. Detectar o tipo
        sozinho é bônus e não está implementado — o campo `tipo` é obrigatório
        no contrato.
        """
        candidatos = [
            (parser.matches(pages), parser) for parser in self.parsers_para(tipo)
        ]
        candidatos = [(score, parser) for score, parser in candidatos if score > 0]

        if not candidatos:
            return None

        score, vencedor = max(candidatos, key=lambda item: item[0])
        logger.info("parser selecionado nome=%s score=%.2f", vencedor.nome, score)
        return vencedor
