"""Formato de saída do HOLERITE — literal do README oficial.

    {
      "pages": [
        {
          "page": 1,
          "year": "2020",
          "month": "01",
          "fields": [
            { "code": "0010", "label": "Salário Base", "reference": "220,00",
              "value": "2.389,77" }
          ],
          "bases": [
            { "label": "Base INSS", "value": "2.545,68" }
          ]
        }
      ]
    }

Pontos críticos, todos exigidos literalmente pela especificação:

- `fields` = SOMENTE verbas da tabela de vencimentos e descontos;
- `bases`  = SOMENTE bases e totais da seção separada.
  Base INSS, Total Descontos e Valor Líquido NÃO são verbas. Misturar
  contamina a planilha inteira, porque cada label de `fields` vira coluna.
- `code` e `reference` usam string vazia `""` quando ausentes — NUNCA `null`,
  nunca chave omitida.
- `label` é a descrição sem o código.
- `month` vai de `"01"` a `"12"`, com zero à esquerda, como string.
- Valores monetários são STRING em formato brasileiro (`"2.389,77"`).
  Converter para float perde o formato e introduz erro de arredondamento.
  Valores negativos preservam o sinal (`"-433,20"`).
- Qualquer campo pode conter `?` quando um caractere não foi lido.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class PayslipField(BaseModel):
    """Uma verba da tabela principal."""

    code: str = ""
    label: str
    reference: str = ""
    value: str


class PayslipBase(BaseModel):
    """Uma base ou total da seção separada."""

    label: str
    value: str


class PayslipPage(BaseModel):
    page: int
    year: str
    month: str
    fields: List[PayslipField] = Field(default_factory=list)
    bases: List[PayslipBase] = Field(default_factory=list)


class PayslipValue(BaseModel):
    pages: List[PayslipPage] = Field(default_factory=list)
