"""Detecção de colunas a partir do cabeçalho da tabela.

O INSTRUCOES oficial lista "coordenadas fixas" entre os erros que derrubam
entregas: "amarrar a leitura a posições x/y absolutas quebra na primeira
variação de layout — inclusive entre páginas do mesmo documento. Prefira
localizar as colunas a partir do cabeçalho".

É o que este módulo faz. Nenhuma coordenada é gravada no código: as faixas
saem das posições reais das palavras do cabeçalho, medidas na própria página.

POR QUE ISSO É NECESSÁRIO, E NÃO REFINAMENTO

Em `time-card-01` a linha de um dia é:

    2 - SEG   08:00   09:03   14:05   HE-BCO DE HORAS   00:13
              ^^^^^   ^^^^^   ^^^^^                     ^^^^^
              Jornada Entrada Saida                     Qtde

Quatro valores no formato `HH:MM`, dos quais **apenas dois são batidas**. Um
regex de `\\d{2}:\\d{2}` na linha captura 100% de falsos positivos nas colunas
`Jornada` e `Qtde`. Só a posição horizontal distingue.

COMO A FAIXA É CALCULADA

O limite entre duas colunas vizinhas é o ponto médio entre o fim de um título e
o começo do próximo. A primeira coluna se estende até a margem esquerda e a
última até a direita, para não perder valor que transborde o título.

Uma palavra pertence à coluna cujo intervalo contém o seu **centro
horizontal** — mais estável que a borda esquerda quando o valor é centralizado
ou alinhado à direita sob o título.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.extraction.extracted_page import ExtractedPage, Line, Word


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento, para comparar títulos de coluna.

    OCR erra acento com frequência (`Saída` vira `Saida`), e o texto nativo
    deste documento já vem sem acento. Comparar normalizado evita que a
    detecção dependa disso.
    """
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


@dataclass(frozen=True)
class Column:
    """Uma coluna, com a faixa horizontal que lhe pertence."""

    name: str
    x0: float
    x1: float  # limite direito, exclusivo


@dataclass(frozen=True)
class ColumnLayout:
    """Faixas de coluna detectadas numa página."""

    columns: Tuple[Column, ...]
    header_top: float

    def column(self, name: str) -> Optional[Column]:
        alvo = normalizar(name)
        for coluna in self.columns:
            if normalizar(coluna.name) == alvo:
                return coluna
        return None

    def cell_words(self, line: Line, name: str) -> List[Word]:
        """Palavras da linha que caem na coluna pedida."""
        coluna = self.column(name)
        if coluna is None:
            return []
        return line.words_between(coluna.x0, coluna.x1)

    def cell_text(self, line: Line, name: str) -> str:
        return " ".join(w.text for w in self.cell_words(line, name))


def detect_columns(
    page: ExtractedPage,
    header_names: Sequence[str],
) -> Optional[ColumnLayout]:
    """Procura a linha de cabeçalho e devolve as faixas de coluna.

    Exige que TODOS os títulos apareçam na mesma linha visual, na ordem dada.
    Ser exigente aqui é proposital: um cabeçalho parcial significa que este não
    é o layout esperado, e é melhor o parser não reconhecer o documento do que
    ler as colunas erradas.

    Devolve `None` quando o cabeçalho não é encontrado.
    """
    alvos = [normalizar(nome) for nome in header_names]

    for line in page.lines():
        encontrados = _match_header_words(line, alvos)
        if encontrados is None:
            continue
        return ColumnLayout(
            columns=_build_columns(encontrados, header_names, page.width),
            header_top=line.top,
        )

    return None


def _match_header_words(line: Line, alvos: Sequence[str]) -> Optional[List[Word]]:
    """Casa os títulos, em ordem, com as palavras da linha.

    Percorre a linha uma vez só: cada título precisa aparecer depois do
    anterior. Palavras entre títulos são ignoradas, o que tolera cabeçalho com
    texto extra sem exigir que ele seja exatamente igual.
    """
    encontrados: List[Word] = []
    indice_alvo = 0

    for palavra in line.words:
        if indice_alvo >= len(alvos):
            break
        if normalizar(palavra.text) == alvos[indice_alvo]:
            encontrados.append(palavra)
            indice_alvo += 1

    return encontrados if indice_alvo == len(alvos) else None


def _build_columns(
    header_words: Sequence[Word],
    header_names: Sequence[str],
    page_width: float,
) -> Tuple[Column, ...]:
    """Converte as palavras do cabeçalho em faixas contíguas."""
    colunas: List[Column] = []

    for indice, palavra in enumerate(header_words):
        # Primeira coluna começa na margem esquerda para não perder valor
        # alinhado à esquerda do próprio título.
        if indice == 0:
            inicio = 0.0
        else:
            anterior = header_words[indice - 1]
            inicio = (anterior.x1 + palavra.x0) / 2

        if indice == len(header_words) - 1:
            fim = max(page_width, palavra.x1)
        else:
            proxima = header_words[indice + 1]
            fim = (palavra.x1 + proxima.x0) / 2

        colunas.append(Column(name=header_names[indice], x0=inicio, x1=fim))

    return tuple(colunas)
