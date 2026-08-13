"""`ExtractedPage` — o contrato interno entre extração e parsing.

Esta é a decisão arquitetural central do projeto — ver SOLUCAO.md,
"`ExtractedPage` — a decisão central".

Os dois caminhos de extração — texto nativo e OCR — produzem exatamente esta
estrutura. Como consequência:

- todo parser funciona nos dois caminhos sem saber qual foi usado;
- a detecção de coluna pelo cabeçalho fica disponível nos dois, que é o que o
  INSTRUCOES recomenda no lugar de coordenadas absolutas;
- labels com espaços colapsados podem ser reconstruídos, porque as palavras vêm
  separadas e posicionadas;
- a confiança viaja junto com o dado, permitindo marcar `?` por caractere.

SISTEMA DE COORDENADAS

Tudo em **pontos de PDF** (1/72 de polegada), com origem no canto superior
esquerdo e `top` crescendo para baixo — a convenção do pdfplumber.

O caminho de OCR converte os pixels devolvidos pelo Tesseract para essa mesma
escala. Sem isso, um parser precisaria saber a origem do dado para interpretar
uma coordenada, e o contrato perderia o sentido.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple


class ExtractionSource(str, Enum):
    """De onde veio o texto desta página."""

    TEXTO_NATIVO = "texto_nativo"
    OCR = "ocr"


@dataclass(frozen=True)
class Word:
    """Uma palavra posicionada na página.

    `confidence` vai de 0 a 100 quando vem do OCR, e é `None` no texto nativo.
    `None` significa "não se aplica", NÃO significa "100". Preencher com um
    valor inventado destruiria a única informação que permite calibrar
    incerteza.
    """

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    confidence: Optional[float] = None

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True)
class Line:
    """Palavras agrupadas numa mesma linha visual, ordenadas da esquerda para a
    direita."""

    words: Tuple[Word, ...]

    @property
    def text(self) -> str:
        """Texto da linha, com um espaço entre palavras.

        Serve para inspeção e para reconhecer cabeçalho (`matches` dos
        parsers). Para ler VALOR de coluna, use as palavras e suas coordenadas
        — é justamente o colapso de espaços do texto linear que corrompe labels
        em documentos como `payroll-01`.
        """
        return " ".join(w.text for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    def words_between(self, x0: float, x1: float) -> List[Word]:
        """Palavras cujo centro horizontal cai na faixa [x0, x1).

        É a operação que permite ler uma coluna sem depender de posição fixa:
        a faixa vem do cabeçalho detectado, não de um número gravado no código.
        """
        return [w for w in self.words if x0 <= w.center_x < x1]


@dataclass
class ExtractedPage:
    """Uma página extraída, pronta para o parser."""

    page: int  # 1-based, índice REAL no PDF — nunca o número impresso na página
    width: float
    height: float
    source: ExtractionSource
    words: List[Word] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.words

    def text(self) -> str:
        """Texto da página, uma linha por linha visual."""
        return "\n".join(linha.text for linha in self.lines())

    def lines(self, tolerance: Optional[float] = None) -> List[Line]:
        """Agrupa palavras em linhas visuais.

        Duas palavras estão na mesma linha quando seus centros verticais estão
        a menos de `tolerance` pontos de distância.

        `tolerance` é derivado da altura mediana das palavras da própria página
        quando não informado. Isso evita fixar um número que funcionaria num
        corpo de 10pt e falharia noutro — e os documentos do desafio variam de
        tamanho de página e de fonte.
        """
        if not self.words:
            return []

        if tolerance is None:
            alturas = [w.height for w in self.words if w.height > 0]
            mediana = statistics.median(alturas) if alturas else 0.0
            tolerance = max(2.0, mediana * 0.6)

        ordenadas = sorted(self.words, key=lambda w: (w.center_y, w.x0))

        grupos: List[List[Word]] = []
        referencia: Optional[float] = None
        for palavra in ordenadas:
            if referencia is None or abs(palavra.center_y - referencia) > tolerance:
                grupos.append([palavra])
                referencia = palavra.center_y
            else:
                grupos[-1].append(palavra)

        return [
            Line(words=tuple(sorted(grupo, key=lambda w: w.x0))) for grupo in grupos
        ]


def build_page(
    page_number: int,
    width: float,
    height: float,
    source: ExtractionSource,
    words: Sequence[Word],
) -> ExtractedPage:
    return ExtractedPage(
        page=page_number,
        width=width,
        height=height,
        source=source,
        words=list(words),
    )
