"""Formato de saída do CARTÃO DE PONTO — literal do README oficial.

    {
      "pages": [
        {
          "page": 1,
          "days": [
            {
              "date_raw": "21/05/2019",
              "punches": [
                { "kind": "IN",  "time_raw": "08:25", "time_hhmm": "08:25" },
                { "kind": "OUT", "time_raw": "18:25", "time_hhmm": "18:25" }
              ]
            },
            { "date_raw": "25/05/2019", "punches": [] }
          ]
        }
      ]
    }

Regras que estes modelos NÃO conseguem impor sozinhos, e que são
responsabilidade dos parsers (ver docs/roadmap.md seções 10, 10.1 e 10.2):

- `days` segue a ordem física do documento — nunca ordenar por data;
- dias sem batida permanecem, com `punches: []` — nunca descartar linha;
- `kind` deriva da coluna quando o layout permite; alternância é fallback;
- `page` vem do índice real do PDF, não do número impresso na página;
- `time_hhmm` pode conter `?` quando um caractere não foi lido com confiança —
  por isso é `str` livre, e não um horário validado.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class PunchKind(str, Enum):
    IN = "IN"
    OUT = "OUT"


class Punch(BaseModel):
    kind: PunchKind
    time_raw: str
    time_hhmm: str


class Day(BaseModel):
    date_raw: str
    punches: List[Punch] = Field(default_factory=list)


class TimesheetPage(BaseModel):
    page: int
    days: List[Day] = Field(default_factory=list)


class TimesheetValue(BaseModel):
    pages: List[TimesheetPage] = Field(default_factory=list)
