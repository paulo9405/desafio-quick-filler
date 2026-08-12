"""Parser da FICHA FINANCEIRA — `payroll-01`. Texto nativo.

LAYOUT

    FICHA FINANCEIRA - PERIODO: 2017/04 a 2025/03
    R E N D I ME N TO S    D E S C O N T O S    R E S U L T A D O S
    Folha Normal
    Mês:  abr-17
    REMUNERAÇÃOMES     969,73 │ 290 VA Funcionario  0  30,67 │ BASEDECALCULODOINSS 1.260,65
    91Hr Adic Pericul  146,67  290,92 │ 511 INSS Normal 0 100,85 │ VALORDOFGTS 100,85
    TOT.RENDIMENTOS  1.620,65 │ TOTALDESCONTOS 228,10 │ SALARIOLIQUIDONOMES 1.392,55
    Folha Normal
    Mês:  mai-17
    ...

VÁRIAS COMPETÊNCIAS POR PÁGINA

Cada bloco `Folha Normal / Mês: abr-17` é uma competência. Todas as entradas da
mesma página física compartilham o mesmo `page` — é literalmente o que o README
descreve para a ficha financeira.

TRÊS GRUPOS DE COLUNA, SEM CABEÇALHO UTILIZÁVEL

O título dos grupos é impresso letra a letra (`R E N D I ME N TO S`), então não
há título de coluna para casar. E ele só aparece na PÁGINA 1 — as demais
continuam a tabela sem repetir o cabeçalho.

Duas abordagens foram medidas e descartadas antes da atual:

- **Faixa a partir da linha de títulos.** Os títulos são centralizados sobre
  grupos largos, e a fronteira resultante caía dentro do valor do desconto:
  `30,67` ia para o grupo RESULTADOS e contaminava o rótulo da base.
  Além disso não funcionaria nas páginas 2 a 5.

- **Agrupar por vão horizontal.** Medido no documento, os vãos DENTRO de um
  grupo (29 pt entre rótulo e referência, 64 pt entre rótulo e referência do
  desconto) são MAIORES que os vãos ENTRE grupos (16 pt e 10 pt). Cortar pelo
  vão junta e separa nos lugares errados.

A divisão usada é ESTRUTURAL e feita linha a linha:

    grupo 2 (DESCONTOS)  começa no primeiro token à direita da coluna de
                         código, cuja posição sai da mediana dos códigos de
                         três dígitos do próprio documento;
    grupo 3 (RESULTADOS) começa no primeiro rótulo alfabético que aparece
                         DEPOIS do valor monetário do grupo 2.

Isso não depende de cabeçalho, funciona em todas as páginas, e acompanha a
posição real dos dados.

CLASSIFICAÇÃO

    RENDIMENTOS + DESCONTOS → `fields`   (verbas)
    RESULTADOS              → `bases`
    TOT.RENDIMENTOS e TOTALDESCONTOS → `bases`, mesmo estando fisicamente
                                       dentro das colunas de verba

LIMITAÇÃO CONHECIDA: LABELS COM ESPAÇOS COLAPSADOS

Este PDF perde os espaços de alguns rótulos já na extração:
`REMUNERAÇÃOMES`, `BASEDECALCULODOINSS`, `TOTALDESCONTOS`. Não é erro de OCR —
o documento é texto nativo, e as palavras vêm coladas do próprio PDF.

Como o label vira coluna de planilha, o cabeçalho sai com essa grafia. Separar
por heurística exigiria um dicionário de termos, que quebraria no primeiro
documento diferente. Preservar o que foi lido é a opção honesta.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.columns import normalizar
from app.extraction.extracted_page import ExtractedPage, Line, Word
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_valor_monetario

PADRAO_VALOR = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
PADRAO_REFERENCIA = re.compile(r"^\d+(?:[.,]\d+)?$")
PADRAO_CODIGO_COLADO = re.compile(r"^(\d{1,3})([A-Za-zÀ-ÿ].*)$")
PADRAO_MES = re.compile(r"([a-zç]{3})\s*[-/]\s*(\d{2,4})", re.IGNORECASE)

TITULO = "fichafinanceira"
MARCADOR_DE_BLOCO = "mes:"
MARCADOR_DE_GRUPOS = "resultados"

MESES = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
    "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12",
}

# Rótulos que são totais, mesmo aparecendo dentro das colunas de verba.
PREFIXOS_DE_TOTAL = ("tot.", "total")


class FichaFinanceiraParser(LayoutParser):
    tipo = "holerite"
    nome = "ficha_financeira"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0
        texto = " ".join(normalizar(p.text()) for p in pages)
        if TITULO not in texto.replace(" ", ""):
            return 0.0
        return 1.0 if MARCADOR_DE_BLOCO in texto else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        # A coluna de código é calculada uma vez, sobre o documento inteiro:
        # só a página 1 traz a linha de títulos, e as demais continuam a tabela.
        inicio_descontos = self._detectar_coluna_de_codigo(pages)

        saida: List[Dict[str, Any]] = []
        for pagina in pages:
            saida.extend(self._parse_page(pagina, inicio_descontos))
        return {"pages": saida}

    def _parse_page(
        self, page: ExtractedPage, inicio_descontos: Optional[float]
    ) -> List[Dict[str, Any]]:
        blocos = self._dividir_em_blocos(page.lines())

        if not blocos or inicio_descontos is None:
            return [
                {
                    "page": page.page, "year": "", "month": "",
                    "fields": [], "bases": [],
                }
            ]

        entradas: List[Dict[str, Any]] = []
        for linhas, mes, ano in blocos:
            verbas, bases = self._ler_bloco(linhas, inicio_descontos)
            entradas.append(
                {
                    "page": page.page,  # competências da mesma página a compartilham
                    "year": ano,
                    "month": mes,
                    "fields": verbas,
                    "bases": bases,
                }
            )

        return entradas

    # ------------------------------------------------------- grupos de coluna

    @staticmethod
    def _detectar_coluna_de_codigo(pages: List[ExtractedPage]) -> Optional[float]:
        """Onde começa a coluna de código dos DESCONTOS.

        Sai da mediana da posição dos códigos de três dígitos do próprio
        documento — nada é gravado no código. Uma margem à esquerda absorve a
        variação de alinhamento entre linhas.
        """
        posicoes = [
            palavra.x0
            for pagina in pages
            for linha in pagina.lines()
            for palavra in linha.words
            if re.fullmatch(r"\d{3}", palavra.text)
        ]
        if len(posicoes) < 3:
            return None

        posicoes.sort()
        return posicoes[len(posicoes) // 2] - 5.0

    # -------------------------------------------------------------- blocos

    def _dividir_em_blocos(
        self, linhas: List[Line]
    ) -> List[Tuple[List[Line], str, str]]:
        inicios = [
            indice
            for indice, linha in enumerate(linhas)
            if normalizar(linha.text).startswith(MARCADOR_DE_BLOCO)
        ]

        blocos: List[Tuple[List[Line], str, str]] = []
        for posicao, inicio in enumerate(inicios):
            fim = inicios[posicao + 1] if posicao + 1 < len(inicios) else len(linhas)
            mes, ano = self._ler_competencia(linhas[inicio])
            # A linha `Folha Normal` do bloco seguinte não entra neste.
            corpo = [
                l
                for l in linhas[inicio + 1 : fim]
                if not normalizar(l.text).startswith("folha")
            ]
            blocos.append((corpo, mes, ano))

        return blocos

    # ------------------------------------------------------ leitura do bloco

    def _ler_bloco(
        self, linhas: List[Line], inicio_descontos: float
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        verbas: List[Dict[str, str]] = []
        bases: List[Dict[str, str]] = []

        for linha in linhas:
            rendimento, desconto, resultado = self._dividir_linha(
                linha, inicio_descontos
            )

            for segmento in (rendimento, desconto):
                registro = self._ler_registro(segmento)
                if registro is None:
                    continue
                if self._e_total(registro["label"]):
                    bases.append(
                        {"label": registro["label"], "value": registro["value"]}
                    )
                else:
                    verbas.append(registro)

            base = self._ler_registro(resultado)
            if base is not None:
                bases.append({"label": base["label"], "value": base["value"]})

        return verbas, bases

    @staticmethod
    def _dividir_linha(
        linha: Line, inicio_descontos: float
    ) -> Tuple[List[Word], List[Word], List[Word]]:
        """Divide a linha nos três grupos, por estrutura.

        O corte entre RENDIMENTOS e DESCONTOS é a coluna de código. O corte
        entre DESCONTOS e RESULTADOS é o primeiro rótulo alfabético que aparece
        DEPOIS do valor monetário do desconto — é assim que `30,67` fica no
        desconto e `BASEDECALCULODOINSS` abre o resultado.
        """
        palavras = sorted(linha.words, key=lambda w: w.x0)

        rendimento = [w for w in palavras if w.x0 < inicio_descontos]
        restante = [w for w in palavras if w.x0 >= inicio_descontos]

        posicao_do_valor = None
        for indice, palavra in enumerate(restante):
            if PADRAO_VALOR.match(palavra.text):
                posicao_do_valor = indice
                break

        if posicao_do_valor is None:
            return rendimento, restante, []

        corte = len(restante)
        for indice in range(posicao_do_valor + 1, len(restante)):
            texto = restante[indice].text
            if texto[:1].isalpha():
                corte = indice
                break

        return rendimento, restante[:corte], restante[corte:]

    def _ler_registro(self, palavras_do_grupo: List[Word]) -> Optional[Dict[str, str]]:
        """Lê `[código] rótulo [referência] valor` dentro de um grupo."""
        palavras = [w.text for w in palavras_do_grupo]
        if not palavras:
            return None

        monetarios = [
            indice for indice, t in enumerate(palavras) if PADRAO_VALOR.match(t)
        ]
        if not monetarios:
            return None

        indice_valor = monetarios[-1]
        code, miolo = self._separar_codigo(palavras[:indice_valor])

        referencia = ""
        if miolo and PADRAO_REFERENCIA.match(miolo[-1]):
            referencia = miolo[-1]
            miolo = miolo[:-1]

        label = " ".join(miolo).strip()
        if not label:
            return None

        leitura = ler_valor_monetario(palavras[indice_valor])
        return {
            "code": code,
            "label": label,
            "reference": referencia,
            "value": leitura.raw if leitura else palavras[indice_valor],
        }

    @staticmethod
    def _separar_codigo(palavras: List[str]) -> Tuple[str, List[str]]:
        """Separa o código do rótulo, inclusive quando vêm colados.

        O documento imprime `290 VA Funcionario` e também `40Reembolso VR` —
        nos dois casos o número é o código da verba.
        """
        if not palavras:
            return "", []

        primeira = palavras[0]
        if primeira.isdigit():
            return primeira, palavras[1:]

        casado = PADRAO_CODIGO_COLADO.match(primeira)
        if casado:
            return casado.group(1), [casado.group(2)] + palavras[1:]

        return "", palavras

    @staticmethod
    def _e_total(label: str) -> bool:
        limpo = normalizar(label).replace(" ", "")
        return any(limpo.startswith(p) for p in PREFIXOS_DE_TOTAL)

    # --------------------------------------------------------- competência

    @staticmethod
    def _ler_competencia(linha: Line) -> Tuple[str, str]:
        """`Mês: abr-17` → `("04", "2017")`.

        O ano vem com dois dígitos. A ficha cobre 2017 a 2025, então `17` é
        2017 — a expansão usa o século 2000, que é o único compatível com o
        período impresso no cabeçalho do documento.
        """
        casado = PADRAO_MES.search(linha.text)
        if not casado:
            return "", ""

        mes = MESES.get(normalizar(casado.group(1)))
        if mes is None:
            return "", ""

        ano = casado.group(2)
        if len(ano) == 2:
            ano = f"20{ano}"

        return mes, ano
