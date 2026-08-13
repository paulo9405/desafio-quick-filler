"""Marcação de incerteza por caractere — a regra `?` do contrato oficial.

    "Quando um caractere não deu para ler com segurança, use `?` no lugar
     dele. (...) A incerteza é por caractere, não por linha."

ESTRATÉGIA: VALIDAÇÃO ESTRUTURAL POR POSIÇÃO

Um campo com formato conhecido — horário, valor monetário — tem uma classe de
caractere esperada em cada posição. Quando o que foi lido viola essa classe,
aquela posição, e **somente ela**, vira `?`.

É exatamente o que os exemplos do README oficial mostram:

    { "time_raw": "0?:25", "time_hhmm": "0?:25" }
    { "value": "2.3?9,77" }

POR QUE NÃO USAR A CONFIANÇA DO TESSERACT

Foi medido nos documentos oficiais, não suposto. Em `time-card-03`, sobre 822
horários lidos corretamente numa coluna de batida:

    confiança mínima ......... 0
    percentil 10 ............. 55
    mediana .................. 91
    lidos certo com conf < 30 . 47

E os 4 tokens realmente errados do documento têm confiança 25, 41, 44 e 53 —
dentro da mesma faixa dos corretos. Um corte por confiança em 50 marcaria
dezenas de valores corretos para pegar 4 errados.

Há ainda dois contraexemplos diretos, registrados em `PROCESSO.md`:

- `07:00d`, `15:00d` e `06:59d` lidos CORRETAMENTE com confiança 10, 16 e 9;
- `Sai1` lido ERRADO como `Sail` com confiança 95.

Conclusão: a confiança do Tesseract não separa certo de errado nestes
documentos. A estrutura do campo separa.

O QUE ESTA ESTRATÉGIA NÃO PEGA

Um dígito trocado por outro dígito — `07:00` lido como `01:00` — passa pela
validação estrutural, porque `1` é um dígito válido naquela posição. Não há
como detectar isso sem uma segunda fonte de leitura. Está registrado como
limitação conhecida, e é o principal ponto onde a solução não é confiável.

O QUE ELA GARANTE

Nada é descartado. Um token com formato de valor nunca é jogado fora por estar
imperfeito: ele volta com `?` nas posições ilegíveis. Antes desta mudança, 4
batidas reais de `time-card-03` eram silenciosamente perdidas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MARCADOR = "?"

# Proporção mínima de dígitos para um token ser considerado candidato a valor
# monetário. Abaixo disso não é um número mal lido — é outra coisa.
PROPORCAO_MINIMA_DE_DIGITOS = 0.6


@dataclass(frozen=True)
class ValorLido:
    """Resultado da leitura de um campo com formato conhecido."""

    raw: str
    """O que foi lido, com `?` nas posições que não deram para ler."""

    normalizado: str
    """A interpretação. Igual ao raw quando não foi possível normalizar."""

    incerto: bool
    """True quando há `?` no raw OU no normalizado.

    Precisa olhar os dois: `25:00` é lido sem ambiguidade (raw limpo), mas é um
    horário impossível, então o normalizado sai como `??:00`. A linha é
    duvidosa mesmo com o raw íntegro.
    """


def contem_incerteza(texto: str) -> bool:
    return MARCADOR in texto


# --------------------------------------------------------------------- horário


def ler_horario(token: str) -> Optional[ValorLido]:
    """Lê um horário no formato `HH:MM`, com `+` e marcador opcionais.

    Devolve `None` quando o token não tem forma de horário — aí ele não é uma
    batida, e não deve virar uma. Textos como `SEG`, `NATAL` ou
    `ATESTADO MEDICO` caem aqui.

    Aceita e marca:

        "12:00"    -> raw "12:00"   normalizado "12:00"
        "07:00d"   -> raw "07:00d"  normalizado "07:00"   (marcador é letra)
        "+03:00d"  -> raw "+03:00d" normalizado "03:00"   (virada de dia)
        "23:00€"   -> raw "23:00?"  normalizado "23:00"   (marcador ilegível)
        "0?:25"    -> raw "0?:25"   normalizado "0?:25"   (dígito ilegível)
        "25:00"    -> raw "25:00"   normalizado "??:00"   (hora impossível)
    """
    if not token:
        return None

    prefixo = ""
    resto = token
    if resto.startswith("+"):
        prefixo, resto = "+", resto[1:]

    # O marcador de sistema é um caractere solto no fim (`07:00d`). Ele só é
    # separado quando o que sobra realmente tem forma de horário — assim
    # `0?:2?` não perde o último `?` achando que é marcador.
    marcador = ""
    partes = _partir_horario(resto)
    if partes is None and len(resto) >= 4:
        marcador, candidato = resto[-1], resto[:-1]
        partes = _partir_horario(candidato)
        if partes is None:
            return None
    elif partes is None:
        return None

    horas_lidas, minutos_lidos = partes

    horas_marcadas = _marcar_nao_digitos(horas_lidas)
    minutos_marcados = _marcar_nao_digitos(minutos_lidos)

    # Um marcador que não é letra não foi lido: `23:00€` no lugar de `23:00c`.
    marcador_marcado = marcador
    if marcador and not marcador.isalpha():
        marcador_marcado = MARCADOR

    raw = f"{prefixo}{horas_marcadas}:{minutos_marcados}{marcador_marcado}"
    normalizado = _normalizar_horario(horas_marcadas, minutos_marcados)

    return ValorLido(
        raw=raw,
        normalizado=normalizado,
        incerto=contem_incerteza(raw) or contem_incerteza(normalizado),
    )


def _partir_horario(texto: str):
    """Separa `HH:MM`. Devolve `None` se não tiver essa forma.

    Aceita hora com um ou dois dígitos: um documento que imprime `9:03` não
    pode ser descartado só por isso.
    """
    if texto.count(":") != 1:
        return None

    horas, _, minutos = texto.partition(":")
    if len(minutos) != 2 or len(horas) not in (1, 2):
        return None

    return horas, minutos


def _marcar_nao_digitos(texto: str) -> str:
    return "".join(c if c.isdigit() else MARCADOR for c in texto)


def _normalizar_horario(horas: str, minutos: str) -> str:
    """`HH:MM` em 24 horas, ou a marcação da parte que não fecha.

    Um horário impossível (`25:00`, `12:75`) é erro de leitura, não horário. O
    componente impossível vira `?`, porque sabemos que ele está errado mas não
    sabemos qual dígito é o certo — e chutar seria o pior desfecho possível.
    O valor original continua íntegro em `time_raw`.
    """
    if MARCADOR in horas:
        hora_texto = MARCADOR * 2
    else:
        valor = int(horas)
        hora_texto = f"{valor:02d}" if valor <= 23 else MARCADOR * 2

    if MARCADOR in minutos:
        minuto_texto = MARCADOR * 2
    else:
        valor = int(minutos)
        minuto_texto = f"{valor:02d}" if valor <= 59 else MARCADOR * 2

    return f"{hora_texto}:{minuto_texto}"


# ------------------------------------------------------------ valor monetário


def ler_valor_monetario(token: str) -> Optional[ValorLido]:
    """Lê um valor no formato brasileiro (`2.389,77`, `-433,20`, `0,00`).

    Devolve `None` quando o token não tem forma de valor monetário.

    O valor permanece STRING, sempre. Converter para float perderia o formato
    e introduziria erro de arredondamento — o INSTRUCOES lista isso entre os
    erros que derrubam entregas.

        "2.389,77"  -> raw "2.389,77"  (limpo)
        "2.3?9,77"  -> raw "2.3?9,77"  (dígito ilegível preservado)
        "2.3O9,77"  -> raw "2.3?9,77"  (letra O onde deveria haver dígito)
    """
    if token.count(",") != 1:
        return None

    parte_inteira, parte_decimal = token.split(",")
    if len(parte_decimal) != 2 or not parte_inteira:
        return None

    negativo = parte_inteira.startswith("-")
    corpo = parte_inteira[1:] if negativo else parte_inteira
    if not corpo:
        return None

    # Posições que deveriam ser dígito: tudo menos os separadores de milhar.
    posicoes = [caractere for caractere in corpo if caractere != "."] + list(
        parte_decimal
    )
    if not posicoes:
        return None

    proporcao = sum(c.isdigit() for c in posicoes) / len(posicoes)
    if proporcao < PROPORCAO_MINIMA_DE_DIGITOS:
        # Poucos dígitos para ser um número mal lido. É outra coisa.
        return None

    corpo_marcado = "".join(
        caractere if (caractere == "." or caractere.isdigit()) else MARCADOR
        for caractere in corpo
    )
    decimal_marcado = "".join(
        caractere if caractere.isdigit() else MARCADOR for caractere in parte_decimal
    )

    raw = f"{'-' if negativo else ''}{corpo_marcado},{decimal_marcado}"

    return ValorLido(raw=raw, normalizado=raw, incerto=contem_incerteza(raw))
