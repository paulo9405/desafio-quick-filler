"""Parser do holerite "Recibo de Pagamento" — `payroll-04`. Lido via OCR.

LAYOUT

    Recibo de Pagamento
    Referencia          Folha
    SETEMBRO/2019       MENSAL

    ┌ Proventos ──────────────┬ Descontos ─────────────────┐
    │ Descrição  Qtde  Valor  │ Descrição   Qtde   Valor   │
    │ SALARIO          953,36 │ INSS MES           200,43  │
    └─────────────────────────┴────────────────────────────┘
    TOTAL DE PROVENTOS 2.227,04   TOTAL DE DESCONTOS 211,43
    LÍQUIDO A RECEBER  2.015,61

    Salário Base | Sal. Contrib. INSS | Base Cálc. FGTS | FGTS Mês | ...
      1.300,00   |      2.227,04      |      0,00       |  178,16  | ...

PARTICULARIDADES

1. DUAS VIAS IDÊNTICAS por página — via da empresa e via do empregado, com o
   mesmo conteúdo. Sai UMA entrada por página; ver decisão em docs/PROCESSO.md.

2. Competência por extenso (`SETEMBRO/2019`), não numérica.

3. Duas tabelas lado a lado, cada uma com suas colunas `Descrição/Qtde/Valor`.
   O cabeçalho traz os três títulos repetidos, e a detecção de coluna os casa
   em ordem.

4. As bases do rodapé vêm em DUAS LINHAS: uma de rótulos e outra de valores,
   alinhados por posição horizontal. Não há como ler por coluna de cabeçalho —
   o pareamento é feito por proximidade de x.

5. Sem código de verba: `code` é sempre string vazia.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.columns import ColumnLayout, detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line, Word
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_valor_monetario

COLUNAS = ("Descrição", "Qtde", "Valor", "Descrição", "Qtde", "Valor")

# Os pares (coluna de descrição, coluna de valor) das duas tabelas.
# A detecção devolve os títulos repetidos na ordem em que aparecem, então as
# faixas são distinguidas pelo índice.
INDICE_DESCRICAO_PROVENTOS, INDICE_VALOR_PROVENTOS = 0, 2
INDICE_DESCRICAO_DESCONTOS, INDICE_VALOR_DESCONTOS = 3, 5

PADRAO_VALOR = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")

# Similaridade mínima para reconhecer um nome de mês danificado pelo OCR.
# Mesmo limiar usado para títulos de coluna, pela mesma razão: o OCR corrompe
# vocabulário conhecido, e exigir igualdade perderia a competência inteira.
LIMIAR_MES = 0.75

MESES = {
    "janeiro": "01", "fevereiro": "02", "marco": "03", "abril": "04",
    "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
    "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12",
}

# Rótulos do bloco de totais, cada um numa linha própria com o seu valor.
# São reconhecidos por prefixo porque o OCR come o primeiro caractere de alguns
# ("OTAL DE PROVENTOS" no lugar de "TOTAL DE PROVENTOS").
TOTAIS = (
    ("total de proventos", "TOTAL DE PROVENTOS"),
    ("total de descontos", "TOTAL DE DESCONTOS"),
    ("liquido a receber", "LÍQUIDO A RECEBER"),
)


def _partir_mes_e_ano(texto: str) -> Tuple[str, str]:
    """`SETEMBRO/2019` → `("SETEMBRO", "2019")`; `NOVEMBRO` → `("NOVEMBRO", "")`."""
    nome, _, resto = texto.partition("/")
    ano = resto if resto.isdigit() and len(resto) == 4 else ""
    return nome, ano


def _mes_por_similaridade(nome: str) -> Optional[str]:
    """Devolve `"09"` para `SETEMBRO` e para variantes danificadas pelo OCR.

    Escolhe o mês MAIS parecido acima do limiar, e não o primeiro — assim uma
    leitura ruim não casa com um mês qualquer só por chegar antes na lista.
    """
    alvo = normalizar(nome)
    if len(alvo) < 4:
        return None

    melhor_mes, melhor_score = None, 0.0
    for candidato, numero in MESES.items():
        score = SequenceMatcher(None, alvo, candidato).ratio()
        if score > melhor_score:
            melhor_mes, melhor_score = numero, score

    return melhor_mes if melhor_score >= LIMIAR_MES else None


class ReciboPagamentoParser(LayoutParser):
    tipo = "holerite"
    nome = "recibo_pagamento"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0
        if not any(detect_columns(pagina, COLUNAS) is not None for pagina in pages):
            return 0.0
        titulo = any(
            "recibo de pagamento" in normalizar(pagina.text()) for pagina in pages
        )
        return 1.0 if titulo else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        return {"pages": [self._parse_page(pagina) for pagina in pages]}

    def _parse_page(self, page: ExtractedPage) -> Dict[str, Any]:
        mes, ano = self._ler_competencia(page)
        layout = detect_columns(page, COLUNAS)

        if layout is None:
            return {
                "page": page.page, "year": ano, "month": mes,
                "fields": [], "bases": [],
            }

        linhas = self._linhas_da_primeira_via(page, layout)

        return {
            "page": page.page,
            "year": ano,
            "month": mes,
            "fields": self._ler_verbas(linhas, layout),
            "bases": self._ler_bases(linhas),
        }

    @staticmethod
    def _linhas_da_primeira_via(page: ExtractedPage, layout: ColumnLayout) -> List[Line]:
        """Corta a página na segunda via.

        Cada página traz o mesmo recibo duas vezes — via da empresa e via do
        empregado. Sem o corte, toda verba e toda base sairiam duplicadas.

        A fronteira é o segundo título `Recibo de Pagamento`.
        """
        abaixo = [l for l in page.lines() if l.top > layout.header_top]

        for linha in abaixo:
            if "recibo de pagamento" in normalizar(linha.text):
                return [l for l in abaixo if l.top < linha.top]

        return abaixo

    # -------------------------------------------------------------- verbas

    def _ler_verbas(
        self, linhas: List[Line], layout: ColumnLayout
    ) -> List[Dict[str, str]]:
        """Lê as duas tabelas lado a lado, proventos antes de descontos.

        Para quando encontra o bloco de totais: dali para baixo é seção de
        bases, e uma verba nunca aparece depois dela.
        """
        verbas: List[Dict[str, str]] = []
        colunas = layout.columns

        for linha in linhas:
            if self._identificar_total(linha) is not None:
                break

            for indice_descricao, indice_valor in (
                (INDICE_DESCRICAO_PROVENTOS, INDICE_VALOR_PROVENTOS),
                (INDICE_DESCRICAO_DESCONTOS, INDICE_VALOR_DESCONTOS),
            ):
                if indice_valor >= len(colunas):
                    continue

                label = self._texto_da_faixa(linha, colunas[indice_descricao])
                valor = self._texto_da_faixa(linha, colunas[indice_valor])
                referencia = self._texto_da_faixa(
                    linha, colunas[indice_descricao + 1]
                )

                # A coluna `Qtde` é de quantidade. Quando o que cai nela não é
                # número, é transbordo do label — `DESC ASS MEDICA AMIL` é
                # largo o bastante para a última palavra entrar na faixa
                # seguinte. Devolver "AMIL" como `reference` seria errado nos
                # dois campos ao mesmo tempo.
                if referencia and not any(c.isdigit() for c in referencia):
                    label = f"{label} {referencia}".strip()
                    referencia = ""

                if not label or not PADRAO_VALOR.match(valor):
                    continue

                leitura = ler_valor_monetario(valor)
                verbas.append(
                    {
                        # Este documento não imprime código de verba.
                        "code": "",
                        "label": label,
                        "reference": referencia,
                        "value": leitura.raw if leitura else valor,
                    }
                )

        return verbas

    @staticmethod
    def _texto_da_faixa(linha: Line, coluna) -> str:
        return " ".join(w.text for w in linha.words_between(coluna.x0, coluna.x1))

    # --------------------------------------------------------------- bases

    def _ler_bases(self, linhas: List[Line]) -> List[Dict[str, str]]:
        bases: List[Dict[str, str]] = []

        for indice, linha in enumerate(linhas):
            rotulo = self._identificar_total(linha)
            if rotulo is not None:
                bases.extend(self._ler_linha_de_totais(linha, rotulo))
                continue

            # A última faixa do documento: uma linha de rótulos seguida de uma
            # linha só com valores.
            if self._parece_linha_de_valores(linha) and indice > 0:
                bases.extend(
                    self._parear_rotulos_e_valores(linhas[indice - 1], linha)
                )

        return bases

    @staticmethod
    def _identificar_total(linha: Line) -> Optional[str]:
        """Reconhece `TOTAL DE PROVENTOS` etc. tolerando o corte do 1º caractere.

        O OCR deste documento come a primeira letra de alguns rótulos —
        `OTAL DE PROVENTOS`. Comparar pelo fim do rótulo evita perder a base.
        """
        texto = normalizar(linha.text)
        for chave, rotulo in TOTAIS:
            if chave in texto or chave[1:] in texto:
                return rotulo
        return None

    def _ler_linha_de_totais(self, linha: Line, rotulo: str) -> List[Dict[str, str]]:
        """Uma linha pode trazer dois totais (proventos e descontos)."""
        valores = [w.text for w in linha.words if PADRAO_VALOR.match(w.text)]
        texto = normalizar(linha.text)

        rotulos: List[str] = []
        for chave, nome in TOTAIS:
            if chave in texto or chave[1:] in texto:
                rotulos.append(nome)

        return [
            {"label": nome, "value": self._marcar(valor)}
            for nome, valor in zip(rotulos, valores)
        ]

    @staticmethod
    def _parece_linha_de_valores(linha: Line) -> bool:
        """Linha composta essencialmente de valores monetários."""
        valores = [w for w in linha.words if PADRAO_VALOR.match(w.text)]
        return len(valores) >= 3 and len(valores) >= len(linha.words) - 2

    def _parear_rotulos_e_valores(
        self, linha_rotulos: Line, linha_valores: Line
    ) -> List[Dict[str, str]]:
        """Casa cada valor com o rótulo que está acima dele.

        As bases do rodapé não têm cabeçalho de coluna: são duas linhas
        empilhadas. O pareamento é por posição horizontal — cada valor pertence
        ao grupo de rótulo cujo centro está mais próximo.
        """
        grupos = self._agrupar_em_celulas(linha_rotulos.words)
        if not grupos:
            return []

        bases: List[Dict[str, str]] = []
        for palavra in linha_valores.words:
            if not PADRAO_VALOR.match(palavra.text):
                continue
            rotulo = min(
                grupos,
                key=lambda g: abs(((g[0].x0 + g[-1].x1) / 2) - palavra.center_x),
            )
            texto_rotulo = " ".join(w.text for w in rotulo).strip()
            if texto_rotulo:
                bases.append(
                    {"label": texto_rotulo, "value": self._marcar(palavra.text)}
                )

        return bases

    @staticmethod
    def _agrupar_em_celulas(palavras: List[Word]) -> List[List[Word]]:
        """Agrupa palavras vizinhas em células, cortando nos vãos maiores.

        O corte usa a largura média de um caractere da própria linha, para não
        depender de um número fixo de pontos.
        """
        if not palavras:
            return []

        ordenadas = sorted(palavras, key=lambda w: w.x0)
        larguras = [w.x1 - w.x0 for w in ordenadas if w.x1 > w.x0]
        media = sum(larguras) / len(larguras) if larguras else 10.0
        limite = max(media * 0.8, 8.0)

        grupos: List[List[Word]] = [[ordenadas[0]]]
        for palavra in ordenadas[1:]:
            if palavra.x0 - grupos[-1][-1].x1 > limite:
                grupos.append([palavra])
            else:
                grupos[-1].append(palavra)

        return grupos

    @staticmethod
    def _marcar(valor: str) -> str:
        leitura = ler_valor_monetario(valor)
        return leitura.raw if leitura else valor

    # --------------------------------------------------------- competência

    @staticmethod
    def _ler_competencia(page: ExtractedPage) -> Tuple[str, str]:
        """`SETEMBRO/2019` → `("09", "2019")`.

        O OCR danifica os nomes de mês deste documento de forma consistente —
        medido nas 5 páginas: `OUTUBRO` sai `PUTUBRO`, `DEZEMBRO` sai
        `PEEMBRO`, e `NOVEMBRO` vem numa linha e o ano na seguinte.

        Por isso a comparação é por similaridade, com o mesmo limiar já usado
        para títulos de coluna, e o ano é procurado à frente do nome do mês.

        Devolve strings vazias quando nada casa — nunca um mês chutado. Uma
        competência ilegível não quebra a cadeia do aviso de mês sequencial;
        quem trata isso é `warnings_service`.
        """
        palavras = [w.text for linha in page.lines() for w in linha.words]

        for indice, texto in enumerate(palavras):
            nome, ano_junto = _partir_mes_e_ano(texto)
            mes = _mes_por_similaridade(nome)
            if mes is None:
                continue

            if ano_junto:
                return mes, ano_junto

            # `NOVEMBRO` e `2016` podem cair em linhas diferentes.
            for seguinte in palavras[indice + 1 : indice + 4]:
                candidato = seguinte.strip("/")
                if candidato.isdigit() and len(candidato) == 4:
                    return mes, candidato

            return mes, ""

        return "", ""
