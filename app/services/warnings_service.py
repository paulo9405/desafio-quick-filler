"""Avisos derivados — calculados a partir do dado, nunca armazenados.

O README oficial é explícito: "Nenhum deles é campo no JSON: todos saem do
próprio dado, calculados na hora de exibir."

São quatro avisos, dois por tipo de documento:

    cartão de ponto ... batidas ímpares · data não sequencial
    holerite .......... página vazia · mês não sequencial

Mais a regra de destaque por incerteza: qualquer `?` na linha pinta de amarelo.

CORES E PRECEDÊNCIA (README oficial)

    amarelo  #FFF3CD  batidas ímpares, página vazia, ou algum `?` na linha
    vermelho #F8D7DA  data ou mês não sequencial
                      + borda esquerda #DC3545 na primeira célula

    "Quando as duas valem para a mesma linha, vermelho ganha."

POR QUE ISTO É UM MÓDULO SEPARADO

Interface e planilha precisam da MESMA decisão. Se cada uma calculasse a sua,
elas divergiriam — e o usuário veria um alerta na tela que não aparece no
arquivo baixado. Aqui as regras são funções puras, sem openpyxl, sem HTTP e sem
banco, então são testáveis isoladamente e reutilizáveis por qualquer consumidor.

O AVISO NÃO MODIFICA O DOCUMENTO

Nenhuma função deste módulo altera o `value` transcrito. Um dia com batida
ímpar continua com número ímpar de batidas; a saída sinaliza, não corrige.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

MARCADOR_INCERTEZA = "?"

# Cores oficiais, literais do README.
AMARELO = "FFF3CD"
VERMELHO = "F8D7DA"
BORDA_VERMELHA = "DC3545"


class Severidade(str, Enum):
    """Vermelho tem precedência sobre amarelo."""

    AMARELO = "amarelo"
    VERMELHO = "vermelho"


@dataclass(frozen=True)
class Aviso:
    codigo: str
    mensagem: str
    severidade: Severidade


@dataclass(frozen=True)
class LinhaAvaliada:
    """Avaliação de uma linha da planilha, na ordem do documento."""

    avisos: Tuple[Aviso, ...] = ()

    @property
    def severidade(self) -> Optional[Severidade]:
        """A severidade que vale para a linha. Vermelho ganha de amarelo."""
        if any(a.severidade is Severidade.VERMELHO for a in self.avisos):
            return Severidade.VERMELHO
        if self.avisos:
            return Severidade.AMARELO
        return None

    @property
    def motivos(self) -> List[str]:
        """Mensagens legíveis, para a interface mostrar o porquê."""
        return [aviso.mensagem for aviso in self.avisos]


# --------------------------------------------------------------- incerteza


def _textos_do_dia(dia: Dict[str, Any]) -> List[str]:
    """Todos os campos de texto de um dia, incluindo o `_raw`.

    Olhar o `time_raw` é ESSENCIAL e não é detalhe: a marcação de incerteza
    pode viver só nele. Em `time-card-03` existem batidas com
    `time_raw = "23:00?"` e `time_hhmm = "23:00"` — os dígitos foram lidos bem,
    o marcador não. Procurar `?` apenas no valor exibido não encontraria nada e
    a linha nunca seria destacada.
    """
    textos = [str(dia.get("date_raw", ""))]
    for batida in dia.get("punches", []):
        textos.append(str(batida.get("time_raw", "")))
        textos.append(str(batida.get("time_hhmm", "")))
    return textos


def _textos_da_pagina_de_holerite(pagina: Dict[str, Any]) -> List[str]:
    """Campos de texto de uma página de holerite.

    Inclui `bases` além de `fields`: uma base ilegível é um problema de leitura
    daquela página, e a pessoa que revisa precisa ser avisada — mesmo que a
    base não vire coluna da planilha.
    """
    textos = [str(pagina.get("month", "")), str(pagina.get("year", ""))]
    for campo in pagina.get("fields", []):
        textos.extend(
            str(campo.get(chave, ""))
            for chave in ("code", "label", "reference", "value")
        )
    for base in pagina.get("bases", []):
        textos.extend(str(base.get(chave, "")) for chave in ("label", "value"))
    return textos


def contem_incerteza(textos: Sequence[str]) -> bool:
    return any(MARCADOR_INCERTEZA in texto for texto in textos)


_AVISO_INCERTEZA = Aviso(
    codigo="leitura_incerta",
    mensagem="Algum caractere desta linha não pôde ser lido com segurança.",
    severidade=Severidade.AMARELO,
)


# ----------------------------------------------------------- cartão de ponto


_AVISO_BATIDAS_IMPARES = Aviso(
    codigo="batidas_impares",
    mensagem="Número ímpar de batidas: falta uma entrada ou uma saída.",
    severidade=Severidade.AMARELO,
)

_AVISO_DATA_NAO_SEQUENCIAL = Aviso(
    codigo="data_nao_sequencial",
    mensagem="A data quebra a sequência do documento, o que costuma indicar "
    "erro de leitura.",
    severidade=Severidade.VERMELHO,
)


def _interpretar_data(date_raw: str) -> Optional[date]:
    """`21/05/2019` → data. `None` quando não dá para comparar.

    Devolve `None` tanto para o que não tem forma de data (o dia solto de um
    documento que não imprime a competência) quanto para o que tem a forma mas
    é impossível (`38/07/2019`) — e o segundo caso é tratado à parte, porque
    ele é evidência de erro de leitura.
    """
    partes = date_raw.split("/")
    if len(partes) != 3:
        return None
    try:
        dia, mes, ano = (int(p) for p in partes)
        return date(ano, mes, dia)
    except ValueError:
        return None


def _tem_forma_de_data(date_raw: str) -> bool:
    partes = date_raw.split("/")
    return len(partes) == 3 and all(p.isdigit() for p in partes)


def avaliar_cartao_ponto(value: Dict[str, Any]) -> List[LinhaAvaliada]:
    """Uma avaliação por dia, na ordem do documento.

    Regras de sequência de data:

    - compara-se cada data legível com a anterior LEGÍVEL; a esperada é a
      anterior mais um dia;
    - uma data que não dá para interpretar não quebra a cadeia — as próximas
      legíveis se comparam entre si. É o mesmo princípio que o README define
      explicitamente para competências, aplicado aqui para não gerar alarme
      falso por causa de uma leitura ruim;
    - uma data com FORMA de data mas impossível (`38/07/2019`) é sinalizada:
      ela quebra a sequência por definição, e o próprio enunciado usa `38/07`
      como exemplo de erro de leitura.
    """
    avaliacoes: List[LinhaAvaliada] = []
    anterior: Optional[date] = None

    for pagina in value.get("pages", []):
        for dia in pagina.get("days", []):
            avisos: List[Aviso] = []

            if len(dia.get("punches", [])) % 2 == 1:
                avisos.append(_AVISO_BATIDAS_IMPARES)

            date_raw = str(dia.get("date_raw", ""))
            atual = _interpretar_data(date_raw)

            if atual is None:
                if _tem_forma_de_data(date_raw):
                    # Tem cara de data e não existe no calendário.
                    avisos.append(_AVISO_DATA_NAO_SEQUENCIAL)
                # Não atualiza `anterior`: a cadeia continua nas legíveis.
            else:
                if anterior is not None and atual != _dia_seguinte(anterior):
                    avisos.append(_AVISO_DATA_NAO_SEQUENCIAL)
                anterior = atual

            if contem_incerteza(_textos_do_dia(dia)):
                avisos.append(_AVISO_INCERTEZA)

            avaliacoes.append(LinhaAvaliada(avisos=tuple(avisos)))

    return avaliacoes


def _dia_seguinte(momento: date) -> date:
    from datetime import timedelta

    return momento + timedelta(days=1)


# ------------------------------------------------------------------ holerite


_AVISO_PAGINA_VAZIA = Aviso(
    codigo="pagina_vazia",
    mensagem="A página existe no PDF mas nenhum dado foi extraído dela.",
    severidade=Severidade.AMARELO,
)

_AVISO_MES_NAO_SEQUENCIAL = Aviso(
    codigo="mes_nao_sequencial",
    mensagem="A competência não é o mês seguinte ao da página anterior.",
    severidade=Severidade.VERMELHO,
)


def _interpretar_competencia(pagina: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """`("2020", "01")` → `(2020, 1)`. `None` quando não dá para comparar.

    Competência com `?`, vazia ou com mês fora de 1..12 é ilegível.
    """
    mes, ano = str(pagina.get("month", "")), str(pagina.get("year", ""))
    if not mes.isdigit() or not ano.isdigit():
        return None
    mes_int, ano_int = int(mes), int(ano)
    if not 1 <= mes_int <= 12:
        return None
    return ano_int, mes_int


def _competencia_seguinte(competencia: Tuple[int, int]) -> Tuple[int, int]:
    """Dezembro → janeiro do ano seguinte, conforme o README."""
    ano, mes = competencia
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def avaliar_holerite(value: Dict[str, Any]) -> List[LinhaAvaliada]:
    """Uma avaliação por entrada de página, na ordem do documento.

    Regras de sequência de competência, literais do README:

    - dezembro → janeiro conta como consecutivo;
    - "páginas cuja competência não deu para ler não quebram a cadeia,
      comparam-se as próximas legíveis entre si".

    A segunda regra é o que impede um alarme falso em cascata: uma página
    ilegível entre 03/2020 e 04/2020 não gera aviso, porque 03 → 04 continua
    consecutivo.
    """
    avaliacoes: List[LinhaAvaliada] = []
    anterior: Optional[Tuple[int, int]] = None

    for pagina in value.get("pages", []):
        avisos: List[Aviso] = []

        if not pagina.get("fields") and not pagina.get("bases"):
            avisos.append(_AVISO_PAGINA_VAZIA)

        atual = _interpretar_competencia(pagina)
        if atual is not None:
            if anterior is not None and atual != _competencia_seguinte(anterior):
                avisos.append(_AVISO_MES_NAO_SEQUENCIAL)
            anterior = atual

        if contem_incerteza(_textos_da_pagina_de_holerite(pagina)):
            avisos.append(_AVISO_INCERTEZA)

        avaliacoes.append(LinhaAvaliada(avisos=tuple(avisos)))

    return avaliacoes


# -------------------------------------------------------------------- fachada


def avaliar(tipo: str, value: Dict[str, Any]) -> List[LinhaAvaliada]:
    """Avalia as linhas de um documento, na ordem em que saem na planilha."""
    if tipo == "cartao-ponto":
        return avaliar_cartao_ponto(value)
    return avaliar_holerite(value)
