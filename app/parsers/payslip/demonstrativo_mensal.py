"""Parser do holerite "Demonstrativo de Pagamento Mensal" — `payroll-03`.

LAYOUT

    Período : 10/2019          Data Pagto: 31.10.2019      Pág: 1
    Salário Base :  1.678,61   Grupo : F
    Cod. Descrição                 Unidade     Proventos   Descontos
    0105 Dias Trabalhados            30,00      1.678,61
    /314 Contr. INSS Remuneração      9,00                    177,03
    Total                                       1.967,07      859,46
    Líqüido                                                 1.107,61
    Base I.N.S.S. :  1.967,07  F.G.T.S. do Mês   :   157,37
    Base I.R.R.F. :  1.790,04  Base I.R.R.F. 13o.:
    Dep. I.R.R.F. :      0,00  Base FGTS:          1.967,07

Uma competência por página. O valor da verba aparece em `Proventos` OU em
`Descontos` — nunca nos dois.

A DECISÃO CENTRAL: `fields` × `bases`

O README é explícito: `fields` são SOMENTE as verbas da tabela principal;
`bases` são SOMENTE as bases e totais da seção separada. Errar isso "contamina
a planilha inteira", porque cada label de `fields` vira uma coluna.

Aqui a fronteira é estrutural e não depende de lista de nomes: a tabela de
verbas termina na linha `Total`, e tudo dali para baixo é base.

TRÊS ARMADILHAS DESTE DOCUMENTO

1. O cabeçalho do funcionário usa o MESMO formato das bases
   (`Salário Base : 1.678,61`, `Grupo : F`). Só a posição — acima da tabela —
   distingue. Por isso as bases são lidas apenas abaixo da linha `Total`.

2. O rodapé de assinatura também termina em `:`
   (`Assinadoeletronicamentepor:`). Uma linha só produz bases se ao menos um
   par dela tiver valor monetário — o rodapé não tem, e é descartado inteiro.

3. `Pág: 1` é impresso em TODAS as páginas. O `page` vem do índice real do PDF.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.extraction.columns import ColumnLayout, detect_columns, normalizar
from app.extraction.extracted_page import ExtractedPage, Line
from app.parsers.base import LayoutParser
from app.parsers.uncertainty import ler_valor_monetario


def _marcar_valor(texto: str) -> str:
    """Aplica a marcação de incerteza a um valor monetário.

    Devolve o texto original quando ele não tem forma de valor — preservar o
    que foi lido é sempre preferível a descartar.

    Neste documento, que tem camada de texto, a marcação nunca dispara. Ela
    existe porque o mesmo caminho será usado por holerites lidos via OCR.
    """
    leitura = ler_valor_monetario(texto)
    return leitura.raw if leitura is not None else texto

COLUNAS = ("Cod.", "Descrição", "Unidade", "Proventos", "Descontos")

# Valor monetário no formato brasileiro: `1.678,61`, `0,00`, `-433,20`.
# Estrito de propósito: é o que separa uma base de verdade do rodapé de
# assinatura, que também termina em `:`.
PADRAO_VALOR = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")

# `Período : 10/2019`
PADRAO_COMPETENCIA = re.compile(r"(\d{2})\s*/\s*(\d{4})")

ROTULO_TOTAL = "total"
ROTULO_LIQUIDO = "liquido"


class DemonstrativoMensalParser(LayoutParser):
    tipo = "holerite"
    nome = "demonstrativo_mensal"

    # ------------------------------------------------------------- detecção

    def matches(self, pages: List[ExtractedPage]) -> float:
        if not pages:
            return 0.0

        tem_cabecalho = any(
            detect_columns(pagina, COLUNAS) is not None for pagina in pages
        )
        if not tem_cabecalho:
            return 0.0

        # O título é impresso letra a letra ("D E M O N S T R A T I V O"),
        # então a impressão digital usa termos com espaçamento normal.
        assinatura = any(
            "periodo" in normalizar(pagina.text()) for pagina in pages
        )
        return 1.0 if assinatura else 0.7

    # ---------------------------------------------------------------- parse

    def parse(self, pages: List[ExtractedPage]) -> Dict[str, Any]:
        return {"pages": [self._parse_page(pagina) for pagina in pages]}

    def _parse_page(self, page: ExtractedPage) -> Dict[str, Any]:
        mes, ano = self._ler_competencia(page)
        layout = detect_columns(page, COLUNAS)

        if layout is None:
            # Página sem tabela continua na saída, vazia. A Fase 2 marca isso
            # como "página vazia"; sumir com ela seria perder linha.
            return {
                "page": page.page,
                "year": ano,
                "month": mes,
                "fields": [],
                "bases": [],
            }

        linhas = [linha for linha in page.lines() if linha.top > layout.header_top]
        linhas_de_verba, linhas_de_base = self._separar_secoes(linhas, layout)

        return {
            "page": page.page,
            "year": ano,
            "month": mes,
            "fields": [
                campo
                for linha in linhas_de_verba
                if (campo := self._ler_verba(linha, layout)) is not None
            ],
            "bases": self._ler_bases(linhas_de_base, layout),
        }

    # -------------------------------------------------------------- seções

    def _separar_secoes(
        self, linhas: List[Line], layout: ColumnLayout
    ) -> Tuple[List[Line], List[Line]]:
        """Divide na linha `Total`, que fecha a tabela de verbas.

        A fronteira é estrutural, e não uma lista de nomes de base. Um holerite
        com uma base que não previmos continua sendo classificado certo.
        """
        for indice, linha in enumerate(linhas):
            primeira_celula = normalizar(layout.cell_text(linha, "Cod."))
            if primeira_celula.startswith(ROTULO_TOTAL):
                return linhas[:indice], linhas[indice:]

        # Sem linha `Total`: tudo o que tem valor é verba, e não há bases.
        return linhas, []

    # -------------------------------------------------------------- verbas

    def _ler_verba(
        self, linha: Line, layout: ColumnLayout
    ) -> Optional[Dict[str, str]]:
        """Uma verba da tabela principal.

        `value` sai de `Proventos` ou de `Descontos` — o que estiver preenchido.
        O sinal não é invertido nem acrescentado: guardamos o que está impresso.
        """
        label = layout.cell_text(linha, "Descrição").strip()
        proventos = layout.cell_text(linha, "Proventos").strip()
        descontos = layout.cell_text(linha, "Descontos").strip()

        valor = proventos or descontos
        if not label or not valor:
            return None

        return {
            # `code` e `reference` são string vazia quando ausentes — nunca None.
            "code": layout.cell_text(linha, "Cod.").strip(),
            "label": label,
            "reference": layout.cell_text(linha, "Unidade").strip(),
            "value": _marcar_valor(valor),
        }

    # --------------------------------------------------------------- bases

    def _ler_bases(
        self, linhas: List[Line], layout: ColumnLayout
    ) -> List[Dict[str, str]]:
        bases: List[Dict[str, str]] = []

        for linha in linhas:
            rotulo = normalizar(layout.cell_text(linha, "Cod."))

            if rotulo.startswith(ROTULO_TOTAL):
                bases.extend(self._ler_linha_total(linha, layout))
            elif rotulo.startswith(ROTULO_LIQUIDO):
                bases.extend(self._ler_linha_liquido(linha, layout))
            else:
                bases.extend(self._ler_pares_rotulo_valor(linha))

        return bases

    def _ler_linha_total(
        self, linha: Line, layout: ColumnLayout
    ) -> List[Dict[str, str]]:
        """A linha `Total` carrega DOIS valores, um por coluna.

        O documento imprime o rótulo `Total` uma vez só, sob duas colunas
        (`Proventos` e `Descontos`). Emitir duas bases chamadas apenas "Total"
        seria ambíguo — o consumidor não saberia qual é qual.

        Decisão: compor o label com o título da coluna, que o próprio documento
        imprime. Nada é inventado, e o vocabulário resultante coincide com o do
        exemplo oficial do README ("Total Vencimentos", "Total Descontos").
        Registrada como decisão P2 em docs/PROCESSO.md.
        """
        bases: List[Dict[str, str]] = []
        for coluna in ("Proventos", "Descontos"):
            valor = layout.cell_text(linha, coluna).strip()
            if PADRAO_VALOR.match(valor):
                bases.append({"label": f"Total {coluna}", "value": valor})
        return bases

    def _ler_linha_liquido(
        self, linha: Line, layout: ColumnLayout
    ) -> List[Dict[str, str]]:
        """`Líqüido` tem um único valor, mas ele não respeita a coluna.

        No documento o número fica entre `Proventos` e `Descontos`. Como a
        linha tem um valor só, pega-se o valor monetário que existir nela, sem
        depender da faixa.
        """
        for palavra in linha.words:
            if PADRAO_VALOR.match(palavra.text):
                rotulo = layout.cell_text(linha, "Cod.").strip()
                return [{"label": rotulo, "value": palavra.text}]
        return []

    @staticmethod
    def _ler_pares_rotulo_valor(linha: Line) -> List[Dict[str, str]]:
        """Lê pares `Rótulo : valor`, que aparecem dois por linha.

        Regra que evita falso positivo: a linha só produz bases se ao menos um
        par dela tiver valor monetário. É o que descarta o rodapé de assinatura,
        que também termina em `:` mas não tem valor.

        O `:` pode vir solto (`Base I.N.S.S. :`) ou colado no último token
        (`Base FGTS:`, `Base I.R.R.F. 13o.:`) — os dois casos existem na mesma
        página.
        """
        encontrados: List[Dict[str, str]] = []
        rotulo_atual: List[str] = []
        indice = 0
        palavras = linha.words

        while indice < len(palavras):
            texto = palavras[indice].text

            if texto == ":" or texto.endswith(":"):
                if texto != ":":
                    rotulo_atual.append(texto[:-1])

                rotulo = " ".join(rotulo_atual).strip()
                rotulo_atual = []
                indice += 1

                valor = ""
                if indice < len(palavras) and PADRAO_VALOR.match(
                    palavras[indice].text
                ):
                    valor = palavras[indice].text
                    indice += 1

                if rotulo:
                    encontrados.append({"label": rotulo, "value": valor})
                continue

            rotulo_atual.append(texto)
            indice += 1

        # Nenhum valor monetário na linha inteira: não é seção de bases.
        if not any(par["value"] for par in encontrados):
            return []

        return encontrados

    # --------------------------------------------------------- competência

    @staticmethod
    def _ler_competencia(page: ExtractedPage) -> Tuple[str, str]:
        """Lê `Período : 10/2019`.

        Devolve strings vazias quando não consegue ler — nunca um mês
        inventado. Mês fora de 1..12 é erro de leitura, não competência.
        """
        for linha in page.lines():
            if "periodo" not in normalizar(linha.text):
                continue
            casado = PADRAO_COMPETENCIA.search(linha.text)
            if not casado:
                return "", ""
            mes, ano = casado.group(1), casado.group(2)
            if not 1 <= int(mes) <= 12:
                return "", ""
            return mes, ano
        return "", ""
