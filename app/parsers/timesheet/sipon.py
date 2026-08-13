"""Parser do cartão de ponto SIPON — `time-card-01`.

LAYOUT

    Mes/Ano             : 7 / 2012           Tipo de Jornada: FLEXIVEL
        Dia Semana   Jornada   Entrada    Saida      Ocorrencia         Qtde
          1 - DOM     08:00
          2 - SEG     08:00     09:03     14:05      HE-BCO DE HORAS    00:13
                                15:12     18:36      HE-REMUNERADA      00:13

Uma competência por página, no cabeçalho. Uma linha por dia, com as batidas
seguintes em linhas de continuação.

AS TRÊS ARMADILHAS DESTE DOCUMENTO

1. Quatro valores `HH:MM` por linha, e só dois são batidas.
   `Jornada` (jornada prevista) e `Qtde` (quantidade de hora extra) têm o
   mesmo formato das batidas. A distinção é a coluna, detectada a partir do
   cabeçalho — ver `app/extraction/columns.py`.

2. Linhas de continuação.
   O segundo par de batidas vem na linha seguinte, normalmente SEM o número do
   dia. Tratá-la como um dia novo produziria dias fantasma sem data.

3. Linhas de continuação que REPETEM o número do dia.
   Medido nos 5 páginas do documento: 33, 33, 34, 32 e 32 linhas de dia para
   31, 31, 30, 31 e 30 dias reais. Sem tratar isso, a saída teria dias
   duplicados e o aviso de "data não sequencial" dispararia em cascata sobre
   dados corretos.

ONDE MEXER PARA UM LAYOUT NOVO

Este arquivo não é reutilizado por outro layout. Um cartão de ponto diferente
ganha o seu próprio arquivo em `app/parsers/timesheet/` e uma linha em
`app/parsers/registry.py`. O que é genérico — detecção de coluna, agrupamento
em linhas — já está fora daqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.columns import ColumnLayout, detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_horario

# Títulos da tabela, na ordem em que aparecem. É a impressão digital do layout
# e a origem das faixas de coluna.
COLUNAS = ("Dia", "Semana", "Jornada", "Entrada", "Saida", "Ocorrencia", "Qtde")

# Colunas que contêm batidas — e a semântica de cada uma.
# `kind` vem DA COLUNA, não da posição na lista de batidas.
# Ver SOLUCAO.md, "`kind` (IN/OUT) vem da coluna".
COLUNAS_DE_BATIDA = (("Entrada", "IN"), ("Saida", "OUT"))

# `Mes/Ano : 7 / 2012` — o mês pode vir com um ou dois dígitos.
PADRAO_COMPETENCIA = re.compile(r"(\d{1,2})\s*/\s*(\d{4})")

DIA_MINIMO, DIA_MAXIMO = 1, 31


@dataclass
class _DiaEmConstrucao:
    """Estado intermediário: um dia sendo montado a partir de várias linhas."""

    numero: int
    date_raw: str
    punches: List[Dict[str, str]] = field(default_factory=list)


class SiponTimesheetParser(LayoutParser):
    tipo = "cartao-ponto"
    nome = "sipon"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        """Reconhece o layout pelo cabeçalho da tabela e pelo sistema emissor.

        NÃO procura pelo título "FOLHA DE FREQUENCIA": ele é impresso letra a
        letra (`F O L H A  DE  F R E Q U E N C I A`) e essa busca nunca
        encontraria nada. Está coberto por teste.
        """
        if not pages:
            return 0.0

        tem_cabecalho = any(
            detect_columns(pagina, COLUNAS) is not None for pagina in pages
        )
        if not tem_cabecalho:
            return 0.0

        tem_sipon = any("sipon" in normalizar(pagina.text()) for pagina in pages)
        return 1.0 if tem_sipon else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        return {"pages": [self._parse_page(pagina) for pagina in pages]}

    def _parse_page(self, page: ExtractedPage) -> Dict[str, Any]:
        layout = detect_columns(page, COLUNAS)
        if layout is None:
            # Página sem tabela (capa, anexo). Continua na saída, vazia — nunca
            # sumir com uma página em silêncio.
            return {"page": page.page, "days": []}

        competencia = self._ler_competencia(page)
        linhas_da_tabela = [
            linha for linha in page.lines() if linha.top > layout.header_top
        ]

        dias: List[_DiaEmConstrucao] = []
        for linha in linhas_da_tabela:
            self._consumir_linha(linha, layout, competencia, dias)

        return {
            "page": page.page,
            "days": [
                {"date_raw": dia.date_raw, "punches": dia.punches} for dia in dias
            ],
        }

    # ------------------------------------------------------------- por linha

    def _consumir_linha(
        self,
        linha: Line,
        layout: ColumnLayout,
        competencia: Optional[tuple],
        dias: List[_DiaEmConstrucao],
    ) -> None:
        numero_do_dia = self._ler_numero_do_dia(linha, layout)

        if numero_do_dia is None:
            # Linha de continuação: as batidas pertencem ao último dia aberto.
            destino = dias[-1] if dias else None
        elif dias and dias[-1].numero == numero_do_dia:
            # Continuação que repete o número do dia — armadilha 3.
            destino = dias[-1]
        else:
            destino = _DiaEmConstrucao(
                numero=numero_do_dia,
                date_raw=self._montar_date_raw(numero_do_dia, competencia),
            )
            dias.append(destino)

        if destino is None:
            # Linha antes do primeiro dia (resto de cabeçalho). Nada a fazer.
            return

        destino.punches.extend(self._ler_batidas(linha, layout))

    def _ler_numero_do_dia(
        self, linha: Line, layout: ColumnLayout
    ) -> Optional[int]:
        """Devolve o número do dia se esta linha abre/retoma um dia."""
        for palavra in layout.cell_words(linha, "Dia"):
            if palavra.text.isdigit():
                numero = int(palavra.text)
                if DIA_MINIMO <= numero <= DIA_MAXIMO:
                    return numero
        return None

    def _ler_batidas(self, linha: Line, layout: ColumnLayout) -> List[Dict[str, str]]:
        """Lê as batidas da linha, na ordem das colunas do documento.

        `kind` vem da coluna. Uma célula vazia simplesmente não produz batida —
        não desloca a paridade das seguintes, que é a fragilidade de determinar
        IN/OUT por posição.
        """
        batidas: List[Dict[str, str]] = []

        for nome_da_coluna, kind in COLUNAS_DE_BATIDA:
            for palavra in layout.cell_words(linha, nome_da_coluna):
                leitura = ler_horario(palavra.text)
                if leitura is None:
                    continue
                batidas.append(
                    {
                        "kind": kind,
                        "time_raw": leitura.raw,
                        "time_hhmm": leitura.normalizado,
                    }
                )

        return batidas

    # ------------------------------------------------------------- auxiliares

    @staticmethod
    def _ler_competencia(page: ExtractedPage) -> Optional[tuple]:
        """Lê `Mes/Ano : 7 / 2012` do cabeçalho da página.

        Devolve `None` quando não encontra ou quando o mês é impossível —
        e nesse caso o `date_raw` NÃO é composto.
        """
        for linha in page.lines():
            if "mes/ano" not in normalizar(linha.text):
                continue
            casado = PADRAO_COMPETENCIA.search(linha.text)
            if not casado:
                return None
            mes, ano = int(casado.group(1)), int(casado.group(2))
            if not 1 <= mes <= 12:
                return None
            return mes, ano
        return None

    @staticmethod
    def _montar_date_raw(numero_do_dia: int, competencia: Optional[tuple]) -> str:
        """Aplica a regra de `date_raw` decidida com a Quick Filler (P1).

        Resposta oficial: quando dia, mês e ano puderem ser associados à linha
        com segurança, a data completa é o melhor resultado. Quando houver
        ambiguidade ou incerteza, não completar.

        Neste layout a competência é impressa e legível no cabeçalho da própria
        página, e cada página cobre um único mês — a associação é segura, então
        compõe. Se a competência não puder ser lida, devolve só o dia impresso,
        sem inventar mês nem ano.
        """
        if competencia is None:
            return str(numero_do_dia)
        mes, ano = competencia
        return f"{numero_do_dia:02d}/{mes:02d}/{ano}"
