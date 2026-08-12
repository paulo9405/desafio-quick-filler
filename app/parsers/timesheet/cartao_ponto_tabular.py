"""Parser do "Cartão de Ponto" tabular — `time-card-03`. Lido via OCR.

LAYOUT

    Data       Ent1    Sai1    Ent2    Sai2   ...  | H.Ext | Atraso | ...
    16/12/2019 SEG 07:00d 12:00d 13:00d 17:00d     |       |        |
    21/12/2019 SAB                                 |       |        |
    25/12/2019 QUA NATAL                           |       |        |
    28/12/2019 SAB 22:59d +03:00d +04:00d +06:59d  |       |        |

Uma linha por dia, com a data COMPLETA impressa. Sem linhas de continuação.

É o primeiro parser que roda sobre OCR, e por isso ele valida na prática a
promessa do `ExtractedPage`: o código abaixo não sabe se o texto veio da camada
nativa ou do Tesseract.

QUATRO PARTICULARIDADES DESTE DOCUMENTO

1. O OCR erra o próprio cabeçalho, de forma idêntica nas 5 páginas:
   `Ent1`→`Entl`, `Sai1`→`Sail`, `Sai2`→`Sai?`. Por isso a detecção de coluna
   tolera similaridade — ver `app/extraction/columns.py`.

2. As colunas `H.Ext`, `Atraso`, `Falta`, `Ad.Not` e `Abono` contêm valores
   `HH:MM` que NÃO são batidas. Elas são declaradas no cabeçalho de propósito:
   sem isso a faixa de `Sai4` se estenderia até a borda da página e engoliria
   a hora extra.

3. Horários trazem sufixo de marcação e prefixo de virada de dia:
   `07:00d`, `23:00c`, `+03:00d`. `time_raw` guarda como impresso;
   `time_hhmm` guarda o horário normalizado. É exatamente o caso que o par
   raw/normalizado do contrato existe para resolver.

4. Dias sem batida trazem texto no lugar dos horários (`NATAL`,
   `CONFRATERNIZAÇÃO UNIVERSAL`, `ABONO JORNADA ENT/SAIDA`) ou nada. Nos dois
   casos a linha permanece, com `punches: []`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.extraction.columns import ColumnLayout, detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_horario

# Todas as colunas da tabela, na ordem impressa.
#
# As cinco últimas não são lidas como batida — existem aqui só para LIMITAR a
# faixa de `Sai4`. Sem elas, `07:00` da coluna `H.Ext` viraria batida.
COLUNAS = (
    "Data",
    "Ent1",
    "Sai1",
    "Ent2",
    "Sai2",
    "Ent3",
    "Sai3",
    "Ent4",
    "Sai4",
    "H.Ext",
    "Atraso",
    "Falta",
    "Ad.Not",
    "Abono",
)

# Colunas de batida e a semântica de cada uma. `kind` vem da coluna.
COLUNAS_DE_BATIDA = (
    ("Ent1", "IN"),
    ("Sai1", "OUT"),
    ("Ent2", "IN"),
    ("Sai2", "OUT"),
    ("Ent3", "IN"),
    ("Sai3", "OUT"),
    ("Ent4", "IN"),
    ("Sai4", "OUT"),
)

# `16/12/2019` — data completa impressa na própria linha.
PADRAO_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")


class CartaoPontoTabularParser(LayoutParser):
    tipo = "cartao-ponto"
    nome = "cartao_ponto_tabular"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0

        tem_cabecalho = any(
            detect_columns(pagina, COLUNAS) is not None for pagina in pages
        )
        if not tem_cabecalho:
            return 0.0

        titulo = any(
            "cartao de ponto" in normalizar(pagina.text()) for pagina in pages
        )
        return 1.0 if titulo else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        return {"pages": [self._parse_page(pagina) for pagina in pages]}

    def _parse_page(self, page: ExtractedPage) -> Dict[str, Any]:
        layout = detect_columns(page, COLUNAS)
        if layout is None:
            return {"page": page.page, "days": []}

        dias: List[Dict[str, Any]] = []
        for linha in page.lines():
            if linha.top <= layout.header_top:
                continue

            date_raw = self._ler_data(linha, layout)
            if date_raw is None:
                # Linha sem data na coluna `Data` não é linha de dia. Este
                # layout não tem continuação: cada dia ocupa uma linha só.
                continue

            dias.append(
                {"date_raw": date_raw, "punches": self._ler_batidas(linha, layout)}
            )

        return {"page": page.page, "days": dias}

    # ------------------------------------------------------------- por linha

    @staticmethod
    def _ler_data(linha: Line, layout: ColumnLayout) -> Optional[str]:
        """Devolve a data impressa na linha, exatamente como lida.

        Regra P1: a data completa já está impressa na linha, então não há nada
        a compor nem a inferir — preserva-se o que o documento mostra.
        """
        for palavra in layout.cell_words(linha, "Data"):
            if PADRAO_DATA.match(palavra.text):
                return palavra.text
        return None

    def _ler_batidas(self, linha: Line, layout: ColumnLayout) -> List[Dict[str, str]]:
        """Lê as 8 colunas de batida, na ordem do documento.

        Texto que não tem forma de horário (`NATAL`, `ATESTADO MEDICO`,
        `SEG`) não vira batida. A linha continua existindo com `punches: []`,
        porque um dia sem batida é uma linha válida.

        Já um token COM forma de horário nunca é descartado, mesmo imperfeito:
        ele volta com `?` nas posições ilegíveis. Ver `app/parsers/uncertainty.py`.

        Isto corrigiu uma perda silenciosa real: `23:00€` e `15:12€` — o
        marcador `c` lido como `€` — eram jogados fora, e o documento perdia 4
        batidas sem nenhum sinal.
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
