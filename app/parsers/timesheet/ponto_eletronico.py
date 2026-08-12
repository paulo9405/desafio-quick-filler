"""Parser do cartão de ponto "Ponto Eletrônico / Relatório Mensal" —
`time-card-02`. Lido via OCR.

LAYOUT

    Mês/Ano: 05/2010
    Dia │ Entrada  Saida │ Intervalo 1 │ Intervalo 2 │ Intervalo 3 │ HE … ATN …
    01 SAB │ Feriado
    17 SEG │ 12:00 - 18:15 │ 15:00 - 15:15
    18 TER │ 09:00 - 18:00 │ 12:00 - 13:00

PARTICULARIDADES

1. As batidas vêm como INTERVALO dentro da célula (`09:00 - 18:00`), e não uma
   por coluna. A coluna `Entrada Saida` são duas faixas — o primeiro horário
   cai em `Entrada` e o segundo em `Saida`. Já cada `Intervalo N` é uma faixa
   só, com os dois horários dentro.

2. O separador `-` às vezes vem colado no horário (`08:56- 17:58`). Sem
   remover o separador antes de ler, o `-` seria interpretado como caractere
   ilegível e produziria um `?` falso.

3. A linha traz apenas o dia (`01 SAB`); a competência está no cabeçalho da
   página. A data é composta conforme a regra P1.

4. Dias sem batida trazem texto (`Feriado`, `Descanso Semanal`,
   `Sem Registro de Ponto`). A linha permanece, com `punches: []`.

5. As colunas `HE Diurno` e `HE Noturno` não são declaradas no cabeçalho: o
   OCR as lê como `tela` e `ala`, com confiança 26, e exigi-las tornaria a
   detecção frágil. Elas contêm valores decimais (`2,0`), não horários, então
   não há risco de virarem batida.

SEMÂNTICA DE IN/OUT NO INTERVALO

Numa coluna de intervalo, o primeiro horário é a SAÍDA para o intervalo e o
segundo é o RETORNO. Portanto `OUT` e depois `IN` — o `kind` sai do significado
da coluna, não da posição na lista. Decisão registrada em docs/PROCESSO.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.columns import ColumnLayout, detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_horario

# `ATN` fecha a faixa de `Intervalo 3`; sem ela a última coluna se estenderia
# até a borda da página.
COLUNAS = (
    "Dia",
    "Entrada",
    "Saida",
    "Intervalo",
    "Intervalo",
    "Intervalo",
    "ATN",
)

# (índice da coluna, kinds na ordem em que os horários aparecem na célula)
COLUNAS_DE_BATIDA: Tuple[Tuple[int, Tuple[str, ...]], ...] = (
    (1, ("IN",)),  # Entrada
    (2, ("OUT",)),  # Saida
    (3, ("OUT", "IN")),  # Intervalo 1 — sai e volta
    (4, ("OUT", "IN")),  # Intervalo 2
    (5, ("OUT", "IN")),  # Intervalo 3
)

PADRAO_COMPETENCIA = re.compile(r"(\d{1,2})\s*/\s*(\d{4})")

# Separadores de intervalo que o OCR pode colar no horário.
SEPARADORES = "-–—"

# O dia pode vir colado no dia da semana: `18QUA`.
PADRAO_DIA = re.compile(r"^(\d{1,2})")

DIA_MINIMO, DIA_MAXIMO = 1, 31


class PontoEletronicoParser(LayoutParser):
    tipo = "cartao-ponto"
    nome = "ponto_eletronico"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0
        if not any(detect_columns(pagina, COLUNAS) is not None for pagina in pages):
            return 0.0
        titulo = any(
            "relatorio mensal" in normalizar(pagina.text()) for pagina in pages
        )
        return 1.0 if titulo else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        return {"pages": [self._parse_page(pagina) for pagina in pages]}

    def _parse_page(self, page: ExtractedPage) -> Dict[str, Any]:
        layout = detect_columns(page, COLUNAS)
        if layout is None:
            return {"page": page.page, "days": []}

        competencia = self._ler_competencia(page)

        dias: List[Dict[str, Any]] = []
        for linha in page.lines():
            if linha.top <= layout.header_top:
                continue

            numero = self._ler_numero_do_dia(linha, layout)
            if numero is None:
                continue

            dias.append(
                {
                    "date_raw": self._montar_date_raw(numero, competencia),
                    "punches": self._ler_batidas(linha, layout),
                }
            )

        return {"page": page.page, "days": dias}

    # ------------------------------------------------------------- por linha

    @staticmethod
    def _ler_numero_do_dia(linha: Line, layout: ColumnLayout) -> Optional[int]:
        """Extrai o dia do início da célula, mesmo colado no dia da semana.

        O OCR às vezes junta os dois: `18QUA`, `18SAB`. Exigir um token
        puramente numérico fazia esses dias sumirem da saída sem qualquer
        sinal — dois dias perdidos nas páginas 4 e 5.
        """
        for palavra in layout.cell_words(linha, "Dia"):
            casado = PADRAO_DIA.match(palavra.text)
            if not casado:
                continue
            numero = int(casado.group(1))
            if DIA_MINIMO <= numero <= DIA_MAXIMO:
                return numero
        return None

    def _ler_batidas(self, linha: Line, layout: ColumnLayout) -> List[Dict[str, str]]:
        """Lê as batidas na ordem das colunas do documento."""
        batidas: List[Dict[str, str]] = []
        colunas = layout.columns

        for indice, kinds in COLUNAS_DE_BATIDA:
            if indice >= len(colunas):
                continue

            coluna = colunas[indice]
            horarios = []
            for palavra in linha.words_between(coluna.x0, coluna.x1):
                for fragmento in self._separar_horarios(palavra.text):
                    leitura = ler_horario(fragmento)
                    if leitura is not None:
                        horarios.append(leitura)

            for posicao, leitura in enumerate(horarios):
                # Mais horários na célula do que kinds previstos: mantém o
                # último kind em vez de descartar a batida.
                kind = kinds[posicao] if posicao < len(kinds) else kinds[-1]
                batidas.append(
                    {
                        "kind": kind,
                        "time_raw": leitura.raw,
                        "time_hhmm": leitura.normalizado,
                    }
                )

        return batidas

    @staticmethod
    def _separar_horarios(texto: str) -> List[str]:
        """Separa um token do intervalo nos horários que ele contém.

        O OCR trata o espaço em volta do `-` de forma inconsistente, e os três
        casos aparecem no mesmo documento:

            "09:00"        horário isolado
            "08:56-"       separador colado no fim
            "09:52-16:07"  os DOIS horários num único token

        O terceiro custava uma batida por ocorrência, silenciosamente. Sem o
        tratamento do segundo, o `-` viraria um `?` falso — o marcador de
        incerteza acusaria um caractere que na verdade foi lido corretamente.
        """
        fragmentos = re.split(f"[{SEPARADORES}]", texto)
        return [f for f in (frag.strip() for frag in fragmentos) if f]

    # ------------------------------------------------------------- auxiliares

    @staticmethod
    def _ler_competencia(page: ExtractedPage) -> Optional[Tuple[int, int]]:
        """Lê `Mês/Ano: 05/2010`."""
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
    def _montar_date_raw(numero: int, competencia: Optional[Tuple[int, int]]) -> str:
        """Regra P1: compõe quando a competência é legível; senão, só o dia."""
        if competencia is None:
            return str(numero)
        mes, ano = competencia
        return f"{numero:02d}/{mes:02d}/{ano}"
