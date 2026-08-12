"""Testes da marcação de incerteza `?`.

Por que estes casos: "honestidade dos dados" vale 15% da nota e é, segundo o
próprio INSTRUCOES, "o critério que mais gente subestima". Os testes abaixo
protegem os dois lados da calibração — marcar o que é duvidoso E não marcar o
que foi lido bem.
"""

from __future__ import annotations

import pytest

from app.parsers.uncertainty import ler_horario, ler_valor_monetario


# --------------------------------------------------- leitura limpa não marca


@pytest.mark.parametrize(
    "token, esperado_hhmm",
    [
        ("12:00", "12:00"),
        ("07:00d", "07:00"),  # marcador de sistema é letra: legítimo
        ("+03:00d", "03:00"),  # virada de dia
        ("9:03", "09:03"),  # hora com um dígito
        ("23:59c", "23:59"),
    ],
)
def test_leitura_limpa_nao_recebe_marcacao(token, esperado_hhmm):
    """Encher a saída de `?` para se proteger também é erro.

    O INSTRUCOES é explícito: "se você diz que não leu nada, você não
    transcreveu nada". O que se mede é calibração, não cautela.
    """
    leitura = ler_horario(token)

    assert leitura is not None
    assert leitura.raw == token
    assert leitura.normalizado == esperado_hhmm
    assert leitura.incerto is False


# ------------------------------------------------------ incerteza por caractere


def test_marcador_ilegivel_vira_interrogacao_sem_perder_a_batida():
    """CASO REAL de `time-card-03`: `23:00c` lido como `23:00€`.

    Antes desta regra o token era descartado inteiro e o documento perdia a
    batida em silêncio. Agora ela é preservada, com o caractere ilegível
    marcado — e os dígitos, que foram lidos bem, continuam disponíveis.
    """
    leitura = ler_horario("23:00€")

    assert leitura is not None
    assert leitura.raw == "23:00?"
    assert leitura.normalizado == "23:00"
    assert leitura.incerto is True


def test_digito_ilegivel_marca_apenas_a_posicao_afetada():
    """Exemplo literal do README oficial: `0?:25`.

    A incerteza é por caractere, não por linha: os outros três dígitos
    continuam legíveis e são entregues.
    """
    leitura = ler_horario("0?:25")

    assert leitura.raw == "0?:25"
    assert leitura.normalizado == "??:25"
    assert leitura.incerto is True


def test_letra_no_lugar_de_digito_e_marcada():
    """`O` maiúsculo lido no lugar de zero é erro clássico de OCR."""
    leitura = ler_horario("O7:00")

    assert leitura.raw == "?7:00"
    assert leitura.incerto is True


def test_horario_impossivel_nao_e_normalizado_como_se_fosse_valido():
    """`25:00` é erro de leitura, não horário — a especificação é explícita.

    O componente impossível vira `?` no normalizado, porque sabemos que está
    errado mas não qual dígito é o certo. O valor lido continua íntegro no raw,
    que é o campo de auditoria.
    """
    leitura = ler_horario("25:00")

    assert leitura.raw == "25:00"
    assert leitura.normalizado == "??:00"
    assert leitura.incerto is True

    minutos = ler_horario("12:75")
    assert minutos.raw == "12:75"
    assert minutos.normalizado == "12:??"


def test_marcacao_nao_engole_o_ultimo_caractere_incerto():
    """`0?:2?` não pode perder o `?` final achando que é marcador de sistema."""
    leitura = ler_horario("0?:2?")

    assert leitura.raw == "0?:2?"
    assert leitura.normalizado == "??:??"


# ------------------------------------------------- o que NÃO é horário


@pytest.mark.parametrize(
    "token",
    [
        "SEG",  # dia da semana, na mesma faixa de coluna
        "NATAL",  # feriado escrito no lugar das batidas
        "ATESTADO",
        "08:34:23",  # carimbo do rodapé
        "1:2",
        "",
        "1.234,56",  # valor monetário
    ],
)
def test_texto_que_nao_e_horario_nao_vira_batida(token):
    """Não marcar `?` em algo que nem é horário — seria ruído puro."""
    assert ler_horario(token) is None


# ------------------------------------------------------------ valor monetário


@pytest.mark.parametrize(
    "token", ["2.389,77", "-433,20", "0,00", "1.100,00", "953,36"]
)
def test_valor_monetario_limpo_nao_recebe_marcacao(token):
    leitura = ler_valor_monetario(token)

    assert leitura is not None
    assert leitura.raw == token
    assert leitura.incerto is False
    assert isinstance(leitura.raw, str)


def test_valor_monetario_com_digito_ilegivel():
    """Exemplo literal do README oficial: `2.3?9,77`."""
    leitura = ler_valor_monetario("2.3?9,77")

    assert leitura.raw == "2.3?9,77"
    assert leitura.incerto is True


def test_letra_no_lugar_de_digito_em_valor_e_marcada():
    leitura = ler_valor_monetario("2.3O9,77")

    assert leitura.raw == "2.3?9,77"
    assert leitura.incerto is True


@pytest.mark.parametrize(
    "token",
    [
        "SETEMBRO/2019",  # competência por extenso
        "1/1",  # numeração de via
        "09/09/2019",  # data
        "10:07:11",  # horário do carimbo
        "abc,de",  # texto com vírgula
    ],
)
def test_texto_que_nao_e_valor_monetario_e_recusado(token):
    """Marcar `?` em qualquer coisa com vírgula seria ruído."""
    assert ler_valor_monetario(token) is None
